"""Resume-safe Ragas scoring: preserve each metric, retry only failed items once."""
import argparse
import asyncio
import hashlib
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "artifacts/ragas-runtime"))

FINAL_METRIC_NAMES = ("faithfulness", "context_recall", "factual_correctness")


def file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_final_inputs(dataset_path, answers_path, capture_report_path):
    dataset = json.loads(Path(dataset_path).read_text(encoding="utf-8"))
    answers = json.loads(Path(answers_path).read_text(encoding="utf-8"))
    capture = json.loads(Path(capture_report_path).read_text(encoding="utf-8"))
    dataset_sha = file_sha256(dataset_path)
    answers_sha = file_sha256(answers_path)
    if capture.get("dataset_sha256") != dataset_sha:
        raise ValueError("Capture dataset SHA mismatch")
    if capture.get("answers_sha256") != answers_sha:
        raise ValueError("Capture answers SHA mismatch")
    if capture.get("status") != "completed" or capture.get("failed") != 0:
        raise ValueError("Final capture is incomplete")
    cases = {case["id"]: case for case in dataset}
    if set(cases) != {row.get("id") for row in answers} or capture.get("cases") != list(cases):
        raise ValueError("Dataset, capture, and answer case IDs mismatch")
    for row in answers:
        case = cases[row["id"]]
        if row.get("question") != case.get("question") or row.get("reference") != case.get("gold_answer"):
            raise ValueError(f"Answer reference mismatch: {row['id']}")
        if row.get("identity") != capture.get("identity"):
            raise ValueError(f"Answer capture identity mismatch: {row['id']}")
    return {"dataset_sha256": dataset_sha, "answers_sha256": answers_sha,
            "capture_identity": capture["identity"]}


def validate_adjudication(path, provenance, answers):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    for field in ("dataset_sha256", "answers_sha256"):
        if data.get(field) != provenance[field]:
            raise ValueError(f"Adjudication {field.replace('_', ' ')} mismatch")
    if data.get("capture_identity") != provenance["capture_identity"]:
        raise ValueError("Adjudication capture identity mismatch")
    if {item.get("id") for item in data.get("cases", [])} != {row["id"] for row in answers}:
        raise ValueError("Adjudication case IDs mismatch")


def validate_score_scope(scope, dataset_sha256):
    if scope == "final-post-selection" and not dataset_sha256:
        raise ValueError("Final scoring requires the sealed dataset SHA")


def validate_reference_overlay(overlay, rows, dataset_sha256):
    if overlay.get("base_dataset_sha256") != dataset_sha256:
        raise ValueError("Reference overlay dataset identity mismatch")
    references = overlay.get("references", {})
    if set(references) != {row["id"] for row in rows}:
        raise ValueError("Reference overlay case IDs mismatch")
    if any(not isinstance(value, str) or not value.strip() for value in references.values()):
        raise ValueError("Reference overlay contains an empty reference")
    return references


def score_trace_options(identity, case_id, metric, scope):
    return {"metadata": {"evaluation_id": identity, "case_id": case_id,
                         "metric": metric, "evaluation_scope": scope}}


def build_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--answers", type=Path, required=True)
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--scope", choices=("development", "final-post-selection"),
                        default="development")
    parser.add_argument("--dataset-sha256")
    parser.add_argument("--dataset", type=Path)
    parser.add_argument("--capture-report", type=Path)
    parser.add_argument("--adjudication", type=Path)
    parser.add_argument("--reference-overlay", type=Path)
    parser.add_argument("--metric-language")
    return parser


async def run(args):
    provenance = None
    if args.scope == "final-post-selection":
        if not args.dataset or not args.capture_report:
            raise ValueError("Final scoring requires --dataset and --capture-report")
        provenance = validate_final_inputs(args.dataset, args.answers, args.capture_report)
        if args.dataset_sha256 and args.dataset_sha256 != provenance["dataset_sha256"]:
            raise ValueError("Provided dataset SHA does not match the dataset file")
        args.dataset_sha256 = provenance["dataset_sha256"]
        if args.adjudication:
            rows_for_review = json.loads(args.answers.read_text(encoding="utf-8"))
            validate_adjudication(args.adjudication, provenance, rows_for_review)
    validate_score_scope(args.scope, args.dataset_sha256)
    from app.core.config import get_settings
    from app.core.llm import get_evaluation_model
    from langsmith import Client, tracing_context, traceable
    from ragas import SingleTurnSample
    from ragas.metrics import Faithfulness, FactualCorrectness, LLMContextRecall
    from ragas.llms import LangchainLLMWrapper
    from ragas.run_config import RunConfig

    settings = get_settings()
    overlay_bytes = args.reference_overlay.read_bytes() if args.reference_overlay else b""
    identity = hashlib.sha256(args.answers.read_bytes() + settings.gemini_eval_model.encode()
                              + args.scope.encode() + (args.dataset_sha256 or "").encode()
                              + overlay_bytes + (args.metric_language or "").encode()
                              + b"ragas-0.2.15-single-turn-v4").hexdigest()[:16]
    destination = args.answers.parent / ("metrics-" + args.answers.stem + "-" + identity)
    destination.mkdir(exist_ok=True)
    rows = json.loads(args.answers.read_text(encoding="utf8"))
    if args.reference_overlay:
        overlay = json.loads(args.reference_overlay.read_text(encoding="utf8"))
        references = validate_reference_overlay(overlay, rows, args.dataset_sha256)
        rows = [{**row, "reference": references[row["id"]]} for row in rows]
    llm = LangchainLLMWrapper(get_evaluation_model(), run_config=RunConfig(max_retries=0, timeout=90))
    metrics = [Faithfulness(llm=llm), LLMContextRecall(llm=llm), FactualCorrectness(llm=llm)]
    if args.metric_language:
        for metric in metrics:
            prompts = await metric.adapt_prompts(args.metric_language, llm, adapt_instruction=True)
            metric.set_prompts(**prompts)
    semaphore = asyncio.Semaphore(2)
    @traceable(name="ragas-saved-answer-metric")
    async def one(row, metric):
        path = destination / (hashlib.sha256(row["id"].encode()).hexdigest()[:16] + "-" + metric.name + ".json")
        attempts = json.loads(path.read_text(encoding="utf8"))["attempts"] if path.exists() else []
        if attempts and (attempts[-1]["status"] != "failed" or not args.retry_failed or len(attempts) >= 2):
            return {"id": row["id"], "metric": metric.name, "attempts": attempts}
        async with semaphore:
            sample = SingleTurnSample(user_input=row["question"], retrieved_contexts=[row["context"]],
                                      response=row["response"], reference=row["reference"])
            try:
                value = await metric.single_turn_ascore(sample, timeout=180)
                result = {"status": "completed" if math.isfinite(value) else "not_scoreable",
                          "score": float(value) if math.isfinite(value) else None}
            except Exception as exc:
                result = {"status": "failed", "error_type": type(exc).__name__,
                    "http_status": getattr(exc, "code", None) if isinstance(getattr(exc, "code", None), int) else None}
            attempts.append(result)
            output = {"id": row["id"], "metric": metric.name, "attempts": attempts}
            path.write_text(json.dumps(output, indent=2), encoding="utf8")
            print(row["id"], metric.name, result["status"], flush=True)
            return output
    client = Client(api_key=settings.langsmith_api_key, api_url=settings.langsmith_endpoint)
    with tracing_context(client=client, project_name=settings.langsmith_project,
                         enabled=settings.langsmith_tracing.lower() == "true",
                         metadata={"evaluation_id": identity, "evaluation_scope": args.scope,
                                   "dataset_sha256": args.dataset_sha256}):
        results = await asyncio.gather(*(one(
            row,
            metric,
            langsmith_extra=score_trace_options(identity, row["id"], metric.name, args.scope),
        ) for row in rows for metric in metrics))
    report = {"identity": identity, "answers_sha256": hashlib.sha256(args.answers.read_bytes()).hexdigest(),
        "scope": args.scope, "dataset_sha256": args.dataset_sha256,
        "method": "per-metric preserved results; compare paired valid cases only",
        "metric_language": args.metric_language,
        "reference_overlay_sha256": hashlib.sha256(overlay_bytes).hexdigest() if overlay_bytes else None,
        "judge_model": settings.gemini_eval_model, "judge_timeout_seconds": settings.eval_model_timeout_seconds,
        "metric_timeout_seconds": 180, "max_attempts": 2, "n": len(rows), "metrics": {}, "results": results}
    for metric in metrics:
        selected = [r["attempts"][-1] for r in results if r["metric"] == metric.name]
        valid = [r["score"] for r in selected if r["status"] == "completed"]
        report["metrics"][metric.name] = {"mean": sum(valid) / len(valid) if valid else None,
            "valid": len(valid), "total": len(rows), "failed": sum(r["status"] == "failed" for r in selected),
            "not_scoreable": sum(r["status"] == "not_scoreable" for r in selected)}
    (destination / "report.json").write_text(json.dumps(report, indent=2), encoding="utf8")
    client.flush()
    print(json.dumps({"directory": str(destination), "metrics": report["metrics"]}), flush=True)


if __name__ == "__main__":
    asyncio.run(run(build_parser().parse_args()))
