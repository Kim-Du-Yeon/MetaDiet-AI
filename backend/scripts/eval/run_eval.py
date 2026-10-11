"""
scripts/eval/run_eval.py

RAG 파이프라인 정량 평가 러너. 개선 전/후를 같은 데이터셋으로 비교한다.

측정 지표 (= 네가 물은 '판단 근거'):
  [청킹/검색이 잘 됐나]
    - page_hit   : 정답 페이지가 검색 top-k에 들어온 비율 (retrieval recall)
    - source_hit : 정답 문서가 top-k에 들어온 비율 (느슨한 기준)
    - avg_score  : 평균 최고 relevance score
  [답변이 잘 됐나]
    - grounded_rate  : 근거 기반으로 답한 비율
    - citation_rate  : 답변에 [출처] 인용을 단 비율 (할루시네이션 방지 지표)
    - faithfulness   : 답변 주장이 근거에 의해 뒷받침되는 비율 (LLM 판정)

결과: 콘솔 표 + eval_report.json 저장. LangSmith 업로드는 best-effort.

실행:
  python scripts/eval/run_eval.py --k 4 --label baseline
"""
import sys, os, json, asyncio, argparse, re
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from pathlib import Path
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BACKEND_DIR / ".env")
os.environ.setdefault("LANGCHAIN_TRACING_V2", os.getenv("LANGSMITH_TRACING",  "true"))
os.environ.setdefault("LANGCHAIN_API_KEY",     os.getenv("LANGSMITH_API_KEY",  ""))
os.environ.setdefault("LANGCHAIN_PROJECT",     os.getenv("LANGSMITH_PROJECT",  "diet-agent"))
os.environ.setdefault("LANGCHAIN_ENDPOINT",    os.getenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com"))

from langsmith import traceable, tracing_context, Client
from app.core.llm import get_chat_model
from app.core.config import get_settings
from app.rag.retriever import retrieve
from app.rag.qa import answer_from_knowledge, NO_EVIDENCE

REPORT_PATH = Path(__file__).parent / "eval_report.json"

judge = get_chat_model(temperature=0, role="eval")


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s)).strip().lower()


def _page_eq(a, b) -> bool:
    """페이지 비교(40.0 vs 40, '40' 등 타입 차이 정규화)."""
    try:
        return int(float(a)) == int(float(b))
    except (ValueError, TypeError):
        return str(a) == str(b)


def _excerpt_hit(gold_excerpt: str, docs: list) -> bool:
    """정답 발췌의 일부가 검색 문서에 실제 포함되는지(페이지 경계에 강건한 검색 지표)."""
    g = _norm(gold_excerpt)
    blob = _norm(" ".join(d.page_content for d in docs))
    for start in (0, len(g) // 3, len(g) // 2):
        win = g[start:start + 40]
        if len(win) >= 30 and win in blob:
            return True
    return False


def _is_refusal(answer: str) -> bool:
    return answer.strip().startswith(NO_EVIDENCE)


async def faithfulness_score(question: str, answer: str, context: str) -> int:
    """답변의 모든 사실 주장이 context로 뒷받침되면 1, 아니면 0 (LLM 판정)."""
    if _is_refusal(answer):
        return 1  # 근거 없을 때 솔직히 거절 → faithful 처리
    resp = await judge.ainvoke(
        f"""아래 답변의 사실 주장이 [근거]만으로 모두 뒷받침되는지 판정하세요.
근거에 없는 내용을 지어냈으면 0, 모두 근거에서 확인되면 1.

[질문] {question}
[근거]
{context[:2500]}
[답변] {answer}

숫자 1 또는 0만 출력:"""
    )
    return 1 if "1" in resp.content[:5] else 0


async def eval_one(item: dict, k: int, use_hybrid: bool, use_rerank: bool) -> dict:
    q = item["question"]
    r = await retrieve(q, k=k, use_hybrid=use_hybrid, use_rerank=use_rerank)
    retrieved = [(d.metadata.get("source_file", d.metadata.get("source")),
                  d.metadata.get("page")) for d in r["docs"]]

    source_hit  = any(s == item["gold_source"] for s, _ in retrieved)
    page_hit    = any(s == item["gold_source"] and _page_eq(p, item["gold_page"])
                      for s, p in retrieved)
    excerpt_hit = _excerpt_hit(item.get("gold_excerpt", ""), r["docs"])

    ans = await answer_from_knowledge(q, k=k, retrieval_result=r)
    refused  = _is_refusal(ans["answer"])
    citation = bool(re.search(r"\[출처", ans["answer"]))
    faith    = await faithfulness_score(q, ans["answer"], ans["context"])

    return {
        "question":    q,
        "gold":        f'{item["gold_source"]} p.{item["gold_page"]}',
        "source_hit":  source_hit,
        "page_hit":    page_hit,
        "excerpt_hit": excerpt_hit,
        "max_score":   r["max_score"],
        "grounded":    ans["grounded"],
        "refused":     refused,
        "citation":    citation,
        "faithfulness": faith,
    }


def _rate(rows, key):
    return round(sum(bool(x[key]) for x in rows) / len(rows), 3) if rows else 0.0


MODES = {
    "dense":  (False, False),  # dense-only
    "hybrid": (True,  False),  # dense + BM25(RRF)
    "full":   (True,  True),   # dense + BM25 + 리랭킹
}


@traceable(
    name="rag-eval",
    run_type="chain",
    project_name=os.getenv("LANGSMITH_PROJECT", "diet-agent"),
    tags=["eval", "rag"],
)
async def main(k: int, label: str, mode: str, dataset: str = "qa_dataset.json"):
    DATA_PATH = Path(__file__).parent / dataset
    if not DATA_PATH.exists():
        print(f"데이터셋 없음. 먼저 gen_dataset.py 실행. ({DATA_PATH})")
        return
    use_hybrid, use_rerank = MODES[mode]
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    print(f"=== 평가 시작: {len(data)}문항, k={k}, mode={mode} "
          f"(hybrid={use_hybrid}, rerank={use_rerank}), label={label} ===\n")

    rows = []
    for i, item in enumerate(data, 1):
        row = await eval_one(item, k, use_hybrid, use_rerank)
        rows.append(row)
        print(f"[{i}/{len(data)}] src={int(row['source_hit'])} page={int(row['page_hit'])} "
              f"exc={int(row['excerpt_hit'])} score={row['max_score']:.2f} "
              f"ref={int(row['refused'])} cite={int(row['citation'])} "
              f"faith={row['faithfulness']} | {row['question'][:42]}")

    # answered_faithfulness: 거절을 뺀 '실제 답변'만의 충실도 (지어냄 측정)
    answered = [x for x in rows if not x["refused"]]
    summary = {
        "label":          label,
        "mode":           mode,
        "k":              k,
        "n":              len(rows),
        "page_hit":       _rate(rows, "page_hit"),
        "source_hit":     _rate(rows, "source_hit"),
        "excerpt_hit":    _rate(rows, "excerpt_hit"),
        "avg_score":      round(sum(x["max_score"] for x in rows) / len(rows), 3),
        "refusal_rate":   _rate(rows, "refused"),
        "citation_rate":  _rate(rows, "citation"),
        "faithfulness":   _rate(rows, "faithfulness"),
        "answered_faithfulness": _rate(answered, "faithfulness") if answered else None,
    }

    print("\n=== 요약 ===")
    for kk, vv in summary.items():
        print(f"  {kk:14} : {vv}")

    # 리포트 누적 저장 (label별로 모아 before/after 비교 가능)
    history = []
    if REPORT_PATH.exists():
        history = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    history.append({"summary": summary, "rows": rows})
    REPORT_PATH.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n리포트 저장: {REPORT_PATH} (누적 {len(history)}회)")

    # LangSmith 업로드 (best-effort, 실패해도 로컬 리포트는 유지)
    try:
        from langsmith import Client
        client = Client()
        ds_name = "diet-rag-eval"
        if not client.has_dataset(dataset_name=ds_name):
            ds = client.create_dataset(dataset_name=ds_name)
            client.create_examples(
                inputs=[{"question": d["question"]} for d in data],
                outputs=[{"gold_source": d["gold_source"], "gold_page": d["gold_page"]} for d in data],
                dataset_id=ds.id,
            )
        print(f"LangSmith 데이터셋 '{ds_name}' 준비됨 (실험 비교는 UI에서 확인).")
    except Exception as e:
        print(f"(LangSmith 업로드 생략: {e})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=4)
    ap.add_argument("--label", type=str, default="")
    ap.add_argument("--mode", type=str, default="full", choices=list(MODES))
    ap.add_argument("--dataset", type=str, default="qa_dataset.json")
    args = ap.parse_args()
    _tracing = os.getenv("LANGSMITH_TRACING", "true").lower() == "true"
    try:
        with tracing_context(enabled=_tracing):
            asyncio.run(main(args.k, args.label or args.mode, args.mode, args.dataset))
    finally:
        if _tracing:
            Client().flush()
