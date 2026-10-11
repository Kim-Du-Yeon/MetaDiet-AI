"""Gemini generation and independent Ragas judging of exact frozen contexts."""
import argparse
import asyncio
import hashlib
import json
import math
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "artifacts/ragas-runtime"))
from app.core.config import get_settings
from app.core.llm import get_evaluation_model
from app.rag.qa import QA_PROMPT, answer_from_knowledge, NO_EVIDENCE
from app.rag.region_guidance import get_region_guidance
from langchain_core.documents import Document
from langsmith import Client, tracing_context
from ragas import EvaluationDataset, SingleTurnSample, evaluate
from ragas.metrics import faithfulness, context_recall
from ragas.llms import LangchainLLMWrapper
from ragas.run_config import RunConfig


async def generate(rows, cases, variant):
    semaphore = asyncio.Semaphore(3)
    async def one(row):
        async with semaphore:
            case = cases[row["id"]]
            docs = [Document(page_content=doc["text"], metadata=doc["metadata"]) for doc in row["documents"]]
            result = await asyncio.wait_for(answer_from_knowledge(case["question"], user_region="INTL",
                retrieval_result={"docs": docs, "context": row["context"], "grounded": bool(row["context"]), "max_score": 0},
                config={"metadata": {"case_id": row["id"], "experiment": "frozen-rerank-answer", "variant": variant}}), 90)
            return {"id": row["id"], "language": case["language"], "case_group": case["case_group"],
                "question": case["question"], "reference": case["gold_answer"],
                "context": row["context"], "response": result["answer"], "token_usage": result.get("token_usage")}
    return await asyncio.gather(*(one(row) for row in rows))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--variant", choices=("none", "minilm", "multibert", "jev"), required=True)
    parser.add_argument("--max-workers", type=int, choices=(1, 2, 3), default=3)
    args = parser.parse_args()
    settings = get_settings()
    cases = {case["id"]: case for case in json.loads(args.dataset.read_text(encoding="utf8"))}
    rows = [json.loads(path.read_text(encoding="utf8")) for path in sorted(args.directory.glob(args.variant + "-0-*.json"))]
    if len(rows) != len(cases) or any(row["status"] != "completed" for row in rows):
        raise ValueError("All frozen retrieval cases must have completed")
    identity = hashlib.sha256((json.dumps(rows, sort_keys=True) + str(QA_PROMPT)
        + get_region_guidance("INTL") + settings.gemini_model + settings.gemini_eval_model
        + hashlib.sha256(args.dataset.read_bytes()).hexdigest()).encode()).hexdigest()[:16]
    destination = args.directory / f"answers-{args.variant}-{identity}.json"
    attempt = uuid4().hex[:8]
    report_path = args.directory / f"quality-{args.variant}-{identity}-{attempt}.json"
    report = {"scope": "development, exact frozen context, Ragas faithfulness/context recall; not final adoption",
        "generation_model": settings.gemini_model, "judge_model": settings.gemini_eval_model,
        "identity": identity, "attempt": attempt, "variant": args.variant, "n": len(rows),
        "max_workers": args.max_workers, "grounding_policy": "all saved contexts eligible to isolate ranking"}
    client = Client(api_key=settings.langsmith_api_key, api_url=settings.langsmith_endpoint)
    with tracing_context(client=client, project_name=settings.langsmith_project,
                         enabled=settings.langsmith_tracing.lower() == "true"):
        try:
            answers = json.loads(destination.read_text(encoding="utf8")) if destination.exists() else asyncio.run(generate(rows, cases, args.variant))
            destination.write_text(json.dumps(answers, ensure_ascii=False, indent=2), encoding="utf8")
            samples = [SingleTurnSample(user_input=row["question"], retrieved_contexts=[row["context"]],
                response=row["response"], reference=row["reference"]) for row in answers]
            results = evaluate(EvaluationDataset(samples=samples), metrics=[faithfulness, context_recall],
                llm=LangchainLLMWrapper(get_evaluation_model()), raise_exceptions=True,
                run_config=RunConfig(max_workers=args.max_workers, max_retries=0, timeout=90))
            scores = results.to_pandas()
            scores.to_json(args.directory / f"scores-{args.variant}-{identity}-{attempt}.json", orient="records", force_ascii=False)
            report["status"] = "completed"
            report["abstained"] = sum(row["response"] == NO_EVIDENCE for row in answers)
            for metric in ("faithfulness", "context_recall"):
                valid = [float(value) for value in scores[metric] if isinstance(value, (int, float)) and math.isfinite(value)]
                report[metric] = sum(valid) / len(valid) if valid else None
                report[metric + "_valid"] = len(valid)
        except Exception as exc:
            detail = str(exc).casefold()
            report.update(status="failed", error_type=type(exc).__name__,
                http_status=getattr(exc, "code", None) if isinstance(getattr(exc, "code", None), int) else None,
                error_category="timeout" if "timeout" in detail or "timed out" in detail else "provider_error")
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
        print(json.dumps(report), flush=True)
    client.flush()
    if report["status"] != "completed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
