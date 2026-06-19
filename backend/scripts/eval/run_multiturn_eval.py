"""
scripts/eval/run_multiturn_eval.py

멀티턴 그래프 시나리오 평가기 — HITL interrupt/resume, confirm-modify 루프 탈출,
이상 입력 후 복구를 ASGITransport(in-process, 실제 서버 불필요)로 검증한다.

실제 호출 최소화 정책:
  - 체크포인터: 실제 Postgres 대신 MemorySaver로 그래프 재빌드(lifespan 불필요)
  - Supabase 비즈니스 데이터: app.db.supabase_client.get_supabase를 패치해서
    이후 import되는 모든 모듈(main.py/agent_tools.py/goal_manager 등)의
    module-level `sb = get_supabase()`까지 한 번에 가짜로 대체
  - Pinecone 벡터스토어: 빈 결과로 폴백(grounded=False, 정상 동작 경로)
  - LLM(gpt-4o-mini)만 실제로 호출 — 라우팅/분류/루프의 실제 동작을 검증하려면
    이 판단만큼은 mock할 수 없음(가짜 응답을 쓰면 "시스템이 맞게 판단하는지"를
    더 이상 검증하지 못하게 됨). 비용은 gpt-4o-mini 기준 미미함.

실행:
  D:\\AX\\diet_agent\\backend\\venv\\Scripts\\python.exe scripts/eval/run_multiturn_eval.py
"""
import sys, os, json, asyncio, time
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from pathlib import Path
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BACKEND_DIR / ".env")
os.environ.setdefault("LANGCHAIN_TRACING_V2", os.getenv("LANGSMITH_TRACING",  "true"))
os.environ.setdefault("LANGCHAIN_API_KEY",     os.getenv("LANGSMITH_API_KEY",  ""))
os.environ.setdefault("LANGCHAIN_PROJECT",     os.getenv("LANGSMITH_PROJECT",  "diet-agent"))
os.environ.setdefault("LANGCHAIN_ENDPOINT",    os.getenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com"))

import httpx
from langsmith import traceable, tracing_context, Client
from langgraph.checkpoint.memory import MemorySaver


# tests/conftest.py의 FakeSupabase와 동일한 설계지만 별도 정의가 필요하다 —
# conftest.py 자체가 최상단에서 `from app.api.routes.main import app`를 실행해서,
# 거기서 FakeSupabase만 import해도 agent_tools.py/analytics.py 등 app 전체가
# (특히 analytics.py는 try/except 없이) "진짜" get_supabase()로 먼저 로드돼버린다.
# 패치를 app import보다 먼저 적용하려면 이 파일 안에 가볍게 다시 정의해야 한다.
class FakeResult:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, data):
        self._data = data

    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def order(self, *a, **k): return self
    def gte(self, *a, **k): return self
    def lte(self, *a, **k): return self
    def insert(self, *a, **k): return self
    def update(self, *a, **k): return self
    def delete(self, *a, **k): return self

    def execute(self):
        return FakeResult(self._data)


class FakeSupabase:
    def __init__(self, tables: dict | None = None):
        self.tables = tables or {}

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(self.tables.get(name, []))


# app 모듈들이 import되기 전에 패치해야 각자의 module-level `sb = get_supabase()`도 가짜를 받음
import app.db.supabase_client as supabase_client_module
_FAKE_SB = FakeSupabase()
supabase_client_module.get_supabase = lambda: _FAKE_SB

from app.api.routes.main import app
from app.core.auth import get_current_auth_id, get_current_user
import app.agents.graph as graph_module
import app.rag.retriever as retriever_module

REPORT_PATH = Path(__file__).parent / "multiturn_report.json"
MAX_TURNS = 10
TEST_USER = "multiturn-eval-user"


def _use_memory_checkpointer():
    """실제 Postgres 체크포인터 대신 MemorySaver로 그래프 재빌드(lifespan 불필요)."""
    graph_module._diet_agent_graph = graph_module.build_graph(checkpointer=MemorySaver())


def _mock_rag():
    """Pinecone/임베딩 호출 없이 빈 결과 -> grounded=False 폴백(정상 동작 경로)."""
    class _EmptyStore:
        def similarity_search_with_relevance_scores(self, query, k=20):
            return []
        def similarity_search(self, query, k=20):
            return []
    retriever_module.get_vector_store = lambda: _EmptyStore()
    retriever_module._get_bm25 = lambda: None
    retriever_module._get_reranker = lambda: None


def _parse_sse(text: str) -> dict:
    done, had_error = None, False
    for line in text.split("\n"):
        if not line.startswith("data: "):
            continue
        evt = json.loads(line[len("data: "):])
        if evt["type"] == "error":
            had_error = True
        if evt["type"] == "done":
            done = evt
    return {"done": done, "had_error": had_error}


def _make_stepper(client: httpx.AsyncClient, thread_id: str):
    """이전 턴이 interrupted였으면 /chat/resume, 아니면 /chat으로 보낸다."""
    state = {"interrupted": False}

    async def step(message: str) -> dict:
        if state["interrupted"]:
            resp = await client.post("/chat/resume", json={"thread_id": thread_id, "message": message})
        else:
            resp = await client.post("/chat", json={"message": message, "thread_id": thread_id})
        result = _parse_sse(resp.text)
        done = result["done"] or {}
        state["interrupted"] = bool(done.get("interrupted"))
        return {
            "message": message, "agent_used": done.get("agent_used"),
            "interrupted": state["interrupted"], "pending_meals": bool(done.get("pending_meals")),
            "had_error": result["had_error"],
        }
    return step


@traceable(name="multiturn-eval-scenario-a", run_type="chain")
async def scenario_a(client) -> dict:
    """정상 멀티턴: 식단 기록 -> confirm 대기 -> 확정."""
    thread_id = f"scenario_a_{int(time.time())}"
    step = _make_stepper(client, thread_id)
    turns = [await step("닭가슴살 200g 먹었어"), await step("응 맞아")]

    passed = (
        turns[0]["interrupted"] and turns[0]["pending_meals"]
        and not turns[1]["interrupted"] and not turns[1]["pending_meals"]
        and not any(t["had_error"] for t in turns)
    )
    return {"name": "A_normal_multiturn", "thread_id": thread_id, "turns": turns,
            "passed": passed, "turn_count": len(turns), "loop_detected": False,
            "error": any(t["had_error"] for t in turns)}


@traceable(name="multiturn-eval-scenario-b", run_type="chain")
async def scenario_b(client) -> dict:
    """confirm-modify 루프 탈출: 기록 -> 수정 요청(재제안) -> 취소(최대 MAX_TURNS회 재시도)."""
    thread_id = f"scenario_b_{int(time.time())}"
    step = _make_stepper(client, thread_id)
    turns = [await step("닭가슴살 200g 먹었어"), await step("닭가슴살 대신 고등어로 바꿔줘")]

    loop_detected = False
    while turns[-1]["interrupted"] and turns[-1]["pending_meals"] and not turns[-1]["had_error"]:
        if len(turns) >= MAX_TURNS:
            loop_detected = True
            break
        turns.append(await step("취소"))

    passed = (
        not loop_detected and not any(t["had_error"] for t in turns)
        and not turns[-1]["pending_meals"] and not turns[-1]["interrupted"]
    )
    return {"name": "B_confirm_modify_loop_exit", "thread_id": thread_id, "turns": turns,
            "passed": passed, "turn_count": len(turns), "loop_detected": loop_detected,
            "error": any(t["had_error"] for t in turns)}


@traceable(name="multiturn-eval-scenario-c", run_type="chain")
async def scenario_c(client) -> dict:
    """에러 후 복구: 빈 메시지/이상 입력 -> 에러 없이 응답 -> 정상 메시지가 다시 잘 라우팅되는지."""
    thread_id = f"scenario_c_{int(time.time())}"
    step = _make_stepper(client, thread_id)
    turns = [await step(""), await step("오늘 칼로리 얼마나 남았어?")]

    passed = not any(t["had_error"] for t in turns) and bool(turns[1]["agent_used"])
    return {"name": "C_error_recovery", "thread_id": thread_id, "turns": turns,
            "passed": passed, "turn_count": len(turns), "loop_detected": False,
            "error": any(t["had_error"] for t in turns)}


async def _find_trace(client_ls: Client, thread_id: str, retries: int = 3) -> bool:
    """LangSmith에 thread_id가 metadata로 찍힌 run이 있는지 확인 + 노드(run) 경로 출력."""
    project = os.getenv("LANGSMITH_PROJECT", "diet-agent")
    for _ in range(retries):
        try:
            runs = list(client_ls.list_runs(project_name=project, limit=100))
        except Exception as e:
            print(f"=== LangSmith 조회 실패: {e} ===")
            return False
        matched = [r for r in runs if (r.extra or {}).get("metadata", {}).get("thread_id") == thread_id]
        if matched:
            print(f"  thread_id={thread_id} -> {len(matched)}개 run:")
            for r in sorted(matched, key=lambda x: x.start_time):
                print(f"    - {r.name} ({r.run_type})")
            return True
        await asyncio.sleep(3)
    return False


async def main():
    _use_memory_checkpointer()
    _mock_rag()
    app.dependency_overrides[get_current_user] = lambda: TEST_USER
    app.dependency_overrides[get_current_auth_id] = lambda: TEST_USER

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=60) as client:
        results = [await scenario_a(client), await scenario_b(client), await scenario_c(client)]

    print("\n=== 시나리오 결과 ===")
    for r in results:
        mark = "✅" if r["passed"] else "❌"
        print(f"  {mark} {r['name']} | turns={r['turn_count']} | loop={r['loop_detected']} | error={r['error']}")

    n = len(results)
    summary = {
        "n": n,
        "completion_rate": round(sum(r["passed"] for r in results) / n, 3),
        "error_rate": round(sum(r["error"] for r in results) / n, 3),
        "trace_found": {},
    }

    _tracing = os.getenv("LANGSMITH_TRACING", "true").lower() == "true"
    if _tracing:
        Client().flush()
        print("\n=== LangSmith trace 조회 (thread_id 전파 검증) ===")
        ls_client = Client()
        for r in results:
            # main.py가 만드는 실제 thread_id는 f"{user_id}_{thread_id}" 합성값
            full_tid = f"{TEST_USER}_{r['thread_id']}"
            summary["trace_found"][r["name"]] = await _find_trace(ls_client, full_tid)

    print("\n=== 요약 ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    REPORT_PATH.write_text(
        json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8")
    print(f"\n리포트 저장: {REPORT_PATH}")


if __name__ == "__main__":
    _tracing = os.getenv("LANGSMITH_TRACING", "true").lower() == "true"
    try:
        with tracing_context(enabled=_tracing):
            asyncio.run(main())
    finally:
        if _tracing:
            Client().flush()
