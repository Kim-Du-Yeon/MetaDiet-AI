"""Publish measured offline retrieval artifacts; replay timings are NOT API latency."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main():
    from app.core.config import get_settings
    from langsmith import Client
    from langsmith.evaluation import evaluate
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    report_bytes = args.report.read_bytes()
    report = json.loads(report_bytes)
    cases = json.loads(args.dataset.read_text(encoding="utf-8"))
    dataset_hash = hashlib.sha256(args.dataset.read_bytes()).hexdigest()
    if report["dataset_sha256"] != dataset_hash:
        raise ValueError("Dataset does not match measured report")
    if any(case.get("review_status") != "reviewed" for case in cases):
        raise ValueError("Only reviewed public gold may be uploaded")
    settings = get_settings()
    client = Client(api_key=settings.langsmith_api_key, api_url=settings.langsmith_endpoint)
    name = "metadiet-public-core40-" + dataset_hash[:12]
    if client.has_dataset(dataset_name=name):
        dataset = client.read_dataset(dataset_name=name)
    else:
        dataset = client.create_dataset(dataset_name=name,
            description="Source-text-reviewed public nutrition questions. No patient records. Clinical policy approval excluded.")
        client.create_examples(dataset_id=dataset.id, examples=[{
            "inputs": {"case_id": case["id"], "question": case["question"]},
            "outputs": {"source": case["gold_source"], "pdf_page": case["gold_page"], "answer": case["gold_answer"]},
            "metadata": {"language": case.get("language"), "split": case.get("split"), "case_group": case.get("case_group")},
        } for case in cases])
    examples = list(client.list_examples(dataset_id=dataset.id))
    if {example.inputs["case_id"] for example in examples} != {case["id"] for case in cases}:
        raise ValueError("Published dataset is incomplete; refusing partial experiment")
    by_id = {case["id"]: case for case in cases}
    for example in examples:
        case = by_id[example.inputs["case_id"]]
        if example.inputs != {"case_id": case["id"], "question": case["question"]} or example.outputs != {
            "source": case["gold_source"], "pdf_page": case["gold_page"], "answer": case["gold_answer"]}:
            raise ValueError("Remote dataset content differs from measured gold; refusing replay")
    published = []
    for mode in ("dense", "hybrid", "full"):
        rows = {row["id"]: row for row in report["cases"] if row["mode"] == mode}
        if set(rows) != {case["id"] for case in cases}:
            raise ValueError("Incomplete measured mode")
        def replay(inputs):
            row = rows[inputs["case_id"]]
            if row["status"] != "completed":
                raise RuntimeError("Recorded retrieval failed: " + row["error_type"])
            return row
        def scores(run, example):
            if not run.outputs:
                return {"key": "evaluation_available", "score": 0}
            return {"results": [{"key": key, "score": float(run.outputs[key])}
                for key in ("source_hit", "page_hit", "mrr", "ndcg")]}
        results = evaluate(replay, data=examples, evaluators=[scores], client=client,
            max_concurrency=2, experiment_prefix="measured-retrieval-" + mode,
            description="Offline replay of actual API retrieval. Run duration is replay time; outputs.seconds is measured retrieval latency.",
            metadata={"artifact_sha256": hashlib.sha256(report_bytes).hexdigest(), "dataset_sha256": dataset_hash,
                "namespace": report["namespace"], "embedding_model": report["embedding_model"],
                "embedding_dimension": report["embedding_dimension"], "mode": mode, "scope": report["scope"],
                "execution_type": "offline_artifact_replay"})
        published.append({"mode": mode, "experiment_name": results.experiment_name})
    client.flush()
    destination = args.report.with_name("langsmith-experiments.json")
    destination.write_text(json.dumps({"dataset": name, "experiments": published}, indent=2), encoding="utf-8")
    print("Published public dataset and three measured-artifact experiments")


if __name__ == "__main__":
    main()
