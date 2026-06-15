"""
scripts/eval/run_ragas_eval.py

ragas 기반 RAG 평가 러너 (gold_dataset.json 전용).

기존 run_eval.py의 커스텀 LLM judge 방식을 보완하기 위해
ragas 표준 지표(faithfulness, context_recall)로 동일 파이프라인을 재평가한다.

지표:
  faithfulness    : 생성 답변의 주장이 retrieved context로 뒷받침되는 비율
  context_recall  : gold_answer의 주장이 retrieved context에 포함된 비율

실행 예:
  python scripts/eval/run_ragas_eval.py --limit 3
  python scripts/eval/run_ragas_eval.py --mode hybrid --k 4
  python scripts/eval/run_ragas_eval.py --dataset gold_dataset.json
"""
import sys, os, json, asyncio, argparse, math
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
from langchain_openai import ChatOpenAI
from ragas import EvaluationDataset, evaluate
from ragas.metrics import faithfulness, context_recall
from ragas.llms import LangchainLLMWrapper
from app.core.config import get_settings
from app.rag.retriever import retrieve
from app.rag.qa import answer_from_knowledge

# SingleTurnSample 위치는 ragas 버전에 따라 다름
try:
    from ragas import SingleTurnSample
except ImportError:
    from ragas.dataset_schema import SingleTurnSample

REPORT_PATH = Path(__file__).parent / "ragas_report.json"

MODES = {
    "dense":  (False, False),
    "hybrid": (True,  False),
    "full":   (True,  True),
}


def _mean_metric(value) -> float | None:
    """ragas result[metric]이 list 또는 scalar 어느 형태든 평균 float으로 변환.

    ragas 0.2.x는 버전에 따라 단일 float 또는 list[float]를 반환한다.
    None / NaN은 제외하고 평균을 계산한다.
    """
    if value is None:
        return None
    if isinstance(value, list):
        nums = [
            v for v in value
            if v is not None and isinstance(v, (int, float)) and not math.isnan(v)
        ]
        return round(sum(nums) / len(nums), 4) if nums else None
    try:
        v = float(value)
        return None if math.isnan(v) else round(v, 4)
    except (TypeError, ValueError):
        return None


def _sample_score(row, key: str) -> float:
    """DataFrame row에서 per-sample 점수를 안전하게 추출한다."""
    val = row.get(key)
    if val is None:
        return 0.0
    try:
        v = float(val)
        return 0.0 if math.isnan(v) else round(v, 4)
    except (TypeError, ValueError):
        return 0.0


@traceable(
    name="ragas-eval",
    run_type="chain",
    project_name=os.getenv("LANGSMITH_PROJECT", "diet-agent"),
    tags=["eval", "ragas"],
)
async def build_samples(data: list, k: int, use_hybrid: bool, use_rerank: bool) -> list:
    """retrieve() + answer_from_knowledge()로 ragas SingleTurnSample 리스트 생성.

    주의: answer_from_knowledge()는 내부적으로 full mode retrieve를 사용한다.
    retrieved_contexts는 --mode 인자에 따른 retrieve() 결과를 사용한다.
    """
    samples = []
    for i, item in enumerate(data, 1):
        q = item["question"]
        r = await retrieve(q, k=k, use_hybrid=use_hybrid, use_rerank=use_rerank)
        ans = await answer_from_knowledge(q, k=k)
        samples.append(SingleTurnSample(
            user_input=q,
            retrieved_contexts=[d.page_content for d in r["docs"]],
            response=ans["answer"],
            reference=item["gold_answer"],
        ))
        print(f"[{i:2}/{len(data)}] docs={len(r['docs'])} score={r['max_score']:.3f} "
              f"grounded={int(ans['grounded'])} | {q[:42]}")
    return samples


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="ragas 기반 RAG 평가")
    ap.add_argument("--dataset", type=str, default="gold_dataset.json",
                    help="평가 데이터셋 파일명 (scripts/eval/ 기준)")
    ap.add_argument("--k",       type=int, default=4,
                    help="retrieve top-k (기본값 4)")
    ap.add_argument("--mode",    type=str, default="full", choices=list(MODES),
                    help="검색 모드: dense / hybrid / full (기본값 full)")
    ap.add_argument("--limit",   type=int, default=None,
                    help="평가 샘플 수 제한 (테스트용, 예: --limit 3)")
    args = ap.parse_args()

    DATA_PATH = Path(__file__).parent / args.dataset
    if not DATA_PATH.exists():
        print(f"데이터셋 없음: {DATA_PATH}")
        sys.exit(1)

    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    if args.limit:
        data = data[: args.limit]

    use_hybrid, use_rerank = MODES[args.mode]
    print(f"=== ragas 평가: {len(data)}샘플, k={args.k}, mode={args.mode} "
          f"(hybrid={use_hybrid}, rerank={use_rerank}) ===\n")

    _tracing = os.getenv("LANGSMITH_TRACING", "true").lower() == "true"

    # Phase 1: async — retrieve + answer_from_knowledge 수집
    try:
        with tracing_context(enabled=_tracing):
            samples = asyncio.run(build_samples(data, args.k, use_hybrid, use_rerank))
    finally:
        if _tracing:
            Client().flush()

    # Phase 2: ragas 평가 — 동기 호출 (자체 이벤트 루프 사용, asyncio.run 중첩 방지)
    judge_llm = LangchainLLMWrapper(
        ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0,
            openai_api_key=get_settings().openai_api_key,
        )
    )

    print("\n=== ragas 지표 계산 중 (faithfulness / context_recall) ===")
    result = evaluate(
        EvaluationDataset(samples=samples),
        metrics=[faithfulness, context_recall],
        llm=judge_llm,
    )

    # Phase 3: 결과 추출 — list / scalar 모두 처리
    faith_score  = _mean_metric(result["faithfulness"])
    recall_score = _mean_metric(result["context_recall"])

    summary = {
        "dataset":        args.dataset,
        "mode":           args.mode,
        "k":              args.k,
        "n":              len(samples),
        "faithfulness":   faith_score,
        "context_recall": recall_score,
    }

    print("\n=== ragas 요약 ===")
    for key, val in summary.items():
        print(f"  {key:16} : {val}")

    # per-sample 점수
    rows = []
    try:
        df = result.to_pandas()
        for i, (_, row) in enumerate(df.iterrows()):
            rows.append({
                "question":       samples[i].user_input[:60],
                "faithfulness":   _sample_score(row, "faithfulness"),
                "context_recall": _sample_score(row, "context_recall"),
            })
        print("\n=== per-sample 점수 ===")
        for row in rows:
            print(f"  faith={row['faithfulness']:.3f}  "
                  f"recall={row['context_recall']:.3f}  | {row['question']}")
    except Exception as e:
        print(f"(per-sample 출력 생략: {e})")

    # 리포트 누적 저장 (before/after 비교 가능)
    history = []
    if REPORT_PATH.exists():
        history = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    history.append({"summary": summary, "rows": rows})
    REPORT_PATH.write_text(
        json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n리포트 저장: {REPORT_PATH} (누적 {len(history)}회)")
