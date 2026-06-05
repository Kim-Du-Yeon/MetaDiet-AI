"""
graph.py

전체 흐름:
  load_state → supervisor → [agent] → save_chat → END

HITL 흐름 (interrupt_before=["confirm"]):
  diet_logger → confirm [interrupt_before] → save_chat → END
  다음 요청 → supervisor (pending 감지) → confirm [interrupt] → 대기
  resume → aupdate_state(message) + ainvoke(None) → confirm 실행

meal_plan 검증 루프:
  meal_plan → validator → (통과) → confirm [interrupt_before] → save_chat
                        → (실패) → meal_plan (MAX 3회)
"""
from contextlib import asynccontextmanager
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from app.schemas.models import AgentState
from app.agents.supervisor.node import supervisor_node, route_to_agent
from app.agents.diet_logger.node import diet_logger_node
from app.agents.confirm.node import confirm_node
from app.agents.strategy.node import strategy_node
from app.agents.inbody.node import inbody_node
from app.agents.reporter.node import reporter_node
from app.agents.meal_plan.node import meal_plan_node
from app.agents.edit.node import edit_node
from app.agents.validator.node import validator_node, route_after_validator
from app.core.config import get_settings
from datetime import date

_diet_agent_graph = None


def get_graph():
    if _diet_agent_graph is None:
        raise RuntimeError("Graph 미초기화. lifespan 이전 호출.")
    return _diet_agent_graph


async def load_state_node(state: AgentState) -> dict:
    from app.db.supabase_client import get_supabase
    sb     = get_supabase()
    user_id = state["user_id"]
    today   = date.today().isoformat()
    try:
        meal_rows = sb.table("meal_logs").select("calories,protein_g,carbs_g,fat_g").eq("user_id", user_id).eq("log_date", today).execute().data
    except:
        meal_rows = []
    try:
        strategy_rows = sb.table("diet_strategies").select("daily_calories,protein_g,carbs_g,fat_g,strategy_note").eq("user_id", user_id).eq("is_active", True).limit(1).execute().data
    except:
        strategy_rows = []
    strategy = strategy_rows[0] if strategy_rows else {}
    try:
        inbody_rows = sb.table("inbody_logs").select("measured_date,weight_kg,skeletal_muscle_kg,body_fat_pct").eq("user_id", user_id).order("measured_date", desc=True).limit(1).execute().data
    except:
        inbody_rows = []
    latest_inbody = inbody_rows[0] if inbody_rows else None
    days_since    = 999
    if latest_inbody:
        days_since = (date.today() - date.fromisoformat(latest_inbody["measured_date"])).days
    return {
        "today_calories":    round(sum(r.get("calories",0)  for r in meal_rows), 1),
        "today_protein":     round(sum(r.get("protein_g",0) for r in meal_rows), 1),
        "today_carbs":       round(sum(r.get("carbs_g",0)   for r in meal_rows), 1),
        "today_fat":         round(sum(r.get("fat_g",0)     for r in meal_rows), 1),
        "today_date":        today,
        "target_calories":   strategy.get("daily_calories", 2000),
        "target_protein":    strategy.get("protein_g", 130),
        "target_carbs":      strategy.get("carbs_g", 200),
        "target_fat":        strategy.get("fat_g", 55),
        "strategy_note":     strategy.get("strategy_note", ""),
        "latest_inbody":     latest_inbody,
        "days_since_inbody": days_since,
        "validation_attempts": 0, "validation_passed": None,
        "validation_feedback": "", "can_improve": None,
    }


async def save_chat_node(state: AgentState) -> dict:
    from app.db.supabase_client import get_supabase
    sb = get_supabase()
    try:
        sb.table("chat_history").insert([
            {"user_id": state["user_id"], "role": "user",      "content": state["message"]},
            {"user_id": state["user_id"], "role": "assistant",  "content": state["response"],
             "agent_type": state.get("agent_used", "unknown")},
        ]).execute()
    except Exception as e:
        print(f"=== save_chat 오류: {e} ===")
    return {}


def build_meal_planner_subgraph():
    """
    meal_plan ↔ validator 상호검증 피드백 루프를 독립 서브그래프로 캡슐화.

    설계 의도:
      - 부모 그래프와 AgentState를 '공유'하므로 state 채널이 그대로 전파됨
        (pending_meals·response·validation_*·rag_context 자동 반영)
      - 체크포인터는 부모 것을 상속 → 여기선 compile()에 넘기지 않음
      - validator 통과(route_after_validator='confirm') → 서브그래프 END →
        부모가 confirm으로 이어받아 interrupt_before HITL이 정상 작동
      - route_after_validator를 그대로 재사용(반환 'confirm'을 내부에서 END로 매핑)
        → validator 코드 무수정, 기존 루프 로직 100% 보존

    효과: '식단 생성+검증'을 한 모듈로 분화 → 부모 그래프는 라우팅에만 집중.
    """
    sub = StateGraph(AgentState)
    sub.add_node("meal_plan", meal_plan_node)
    sub.add_node("validator", validator_node)
    sub.set_entry_point("meal_plan")
    sub.add_edge("meal_plan", "validator")
    sub.add_conditional_edges(
        "validator", route_after_validator,
        {"meal_plan": "meal_plan", "confirm": END},   # 통과 시 서브그래프 종료
    )
    return sub.compile()


def build_graph(checkpointer=None):
    graph = StateGraph(AgentState)

    graph.add_node("load_state",  load_state_node)
    graph.add_node("supervisor",  supervisor_node)
    graph.add_node("diet_logger", diet_logger_node)   # 파싱+영양계산 전담
    graph.add_node("confirm",     confirm_node)        # HITL 전담 (interrupt_before 대상)
    graph.add_node("strategy",    strategy_node)
    graph.add_node("inbody",      inbody_node)
    graph.add_node("reporter",    reporter_node)
    # meal_plan↔validator 피드백 루프를 서브그래프 노드 1개로 캡슐화
    graph.add_node("meal_planner", build_meal_planner_subgraph())
    graph.add_node("edit",        edit_node)
    graph.add_node("save_chat",   save_chat_node)

    graph.set_entry_point("load_state")
    graph.add_edge("load_state", "supervisor")

    # supervisor → agent 라우팅
    # route_to_agent: pending_meals 있으면 confirm으로 강제 라우팅
    graph.add_conditional_edges(
        "supervisor",
        route_to_agent,
        {
            "diet_logger": "diet_logger",
            "confirm":     "confirm",
            "strategy":    "strategy",
            "inbody":      "inbody",
            "reporter":    "reporter",
            "meal_plan":   "meal_planner",   # intent 'meal_plan' → 서브그래프 노드
            "edit":        "edit",
        }
    )

    # diet_logger → confirm (interrupt_before=["confirm"]로 여기서 대기)
    # confirm이 저장/수정/취소 처리 후 save_chat
    graph.add_edge("diet_logger", "confirm")
    # confirm 후 조건부 라우팅:
    # modify → awaiting_confirmation=True → 다시 confirm (interrupt_before에 걸림)
    # confirm/cancel → save_chat → END
    def route_after_confirm(state):
        if state.get("awaiting_confirmation") and state.get("pending_meals"):
            return "confirm"
        return "save_chat"

    graph.add_conditional_edges("confirm", route_after_confirm,
                                {"confirm": "confirm", "save_chat": "save_chat"})

    # meal_planner 서브그래프(meal_plan↔validator 루프) 완료 후 → confirm(HITL interrupt)
    graph.add_edge("meal_planner", "confirm")

    for node in ["strategy", "inbody", "reporter", "edit"]:
        graph.add_edge(node, "save_chat")
    graph.add_edge("save_chat", END)

    # interrupt_before=["confirm"]:
    #   diet_logger 완료 + save_chat 후 다음 요청에서
    #   supervisor → confirm 라우팅 시 confirm 진입 전 자동 대기
    #   routes: aupdate_state({"message": user_input}) + ainvoke(None) 으로 재개
    return graph.compile(checkpointer=checkpointer, interrupt_before=["confirm"])


@asynccontextmanager
async def lifespan(app):
    global _diet_agent_graph
    settings = get_settings()
    db_url   = settings.supabase_db_url
    if not db_url:
        raise RuntimeError("SUPABASE_DB_URL 미설정")
    print("=== [lifespan] AsyncPostgresSaver 초기화 중... ===")
    async with AsyncPostgresSaver.from_conn_string(db_url) as checkpointer:
        await checkpointer.setup()
        print("=== [lifespan] 체크포인터 테이블 준비 완료 ===")
        _diet_agent_graph = build_graph(checkpointer=checkpointer)
        print("=== [lifespan] Diet Agent 그래프 빌드 완료 ===")
        yield
    _diet_agent_graph = None
    print("=== [lifespan] 그래프 해제 완료 ===")