"""Publish measured public artifacts as explicitly labelled LangSmith replays."""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def verify_run_count(client, name, expected):
    for attempt in range(8):
        runs = list(client.list_runs(project_name=name, is_root=True))
        if len(runs) == expected:
            return len(runs)
        if attempt < 7:
            time.sleep(1)
    raise RuntimeError("Remote experiment run count mismatch after bounded index wait")


def main():
    from app.core.config import get_settings
    from langsmith import Client
    from langsmith.evaluation import evaluate
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    dataset_hash = hashlib.sha256(args.dataset.read_bytes()).hexdigest()
    cases = json.loads(args.dataset.read_text(encoding="utf8"))
    report_path = args.directory / "report.json"
    report = json.loads(report_path.read_text(encoding="utf8"))
    if report["dataset_sha256"] != dataset_hash or any(case["review_status"] != "reviewed" or case["split"] != "development" for case in cases):
        raise ValueError("Public reviewed development dataset fingerprint required")
    settings = get_settings()
    client = Client(api_key=settings.langsmith_api_key, api_url=settings.langsmith_endpoint)
    name = "metadiet-rerank-core40-" + dataset_hash[:12]
    inputs = lambda case: {"case_id": case["id"], "question": case["question"]}
    reference = lambda case: {"answer": case["gold_answer"], "acceptable_evidence": case["acceptable_evidence"]}
    if client.has_dataset(dataset_name=name):
        dataset = client.read_dataset(dataset_name=name)
    else:
        dataset = client.create_dataset(dataset_name=name, description="Reviewed public source-text facts; development only; no patient data or clinical-policy approval")
        client.create_examples(dataset_id=dataset.id, examples=[{"inputs": inputs(case), "outputs": reference(case),
            "metadata": {"case_group": case["case_group"], "language": case["language"], "split": "development"}} for case in cases])
    examples = list(client.list_examples(dataset_id=dataset.id))
    by_id = {case["id"]: case for case in cases}
    if len(examples) != len(cases) or {example.inputs["case_id"] for example in examples} != set(by_id):
        raise ValueError("Remote dataset incomplete")
    for example in examples:
        case = by_id[example.inputs["case_id"]]
        if example.inputs != inputs(case) or example.outputs != reference(case):
            raise ValueError("Remote dataset content mismatch")
    publication_path = args.directory / "langsmith-replays.json"
    artifact_hash = hashlib.sha256(report_path.read_bytes()).hexdigest()
    saved = json.loads(publication_path.read_text(encoding="utf8")) if publication_path.exists() else None
    if saved and (saved["dataset"] != name or saved.get("report_sha256") != artifact_hash):
        raise ValueError("Publication resume fingerprint mismatch")
    published = saved["experiments"] if saved else []
    for variant in report["summaries"]:
        previous = next((item for item in published if item["variant"] == variant), None)
        if previous:
            previous["verified_root_runs"] = verify_run_count(client, previous["experiment_name"], len(cases))
            continue
        rows = {row["id"]: row for row in report["cases"] if row["variant"] == variant and row["repeat"] == 0}
        if set(rows) != set(by_id) or any(row["status"] != "completed" for row in rows.values()):
            raise ValueError("Incomplete measured variant")
        def replay(value):
            return rows[value["case_id"]]
        def scores(run, example):
            return {"results": [{"key": key, "score": float(run.outputs[key])} for key in ("page_hit", "excerpt_hit", "mrr", "ndcg")]}
        result = evaluate(replay, data=examples, client=client, evaluators=[scores], max_concurrency=2,
            experiment_prefix="frozen-rerank-" + variant,
            description="Offline artifact replay. Output seconds measures ONLY reranking; trace duration is replay time. No generation or end-to-end latency claim.",
            metadata={"execution_type": "offline_artifact_replay", "dataset_sha256": dataset_hash,
                "report_sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
                "candidate_sha256": hashlib.sha256((args.directory / "candidates.json").read_bytes()).hexdigest(),
                "scope": report["scope"], "variant": variant})
        client.flush()
        record = {"variant": variant, "experiment_name": result.experiment_name, "verified_root_runs": None}
        published.append(record)
        publication_path.write_text(json.dumps({"dataset": name, "report_sha256": artifact_hash, "experiments": published}, indent=2), encoding="utf8")
        record["verified_root_runs"] = verify_run_count(client, result.experiment_name, len(cases))
        publication_path.write_text(json.dumps({"dataset": name, "report_sha256": artifact_hash, "experiments": published}, indent=2), encoding="utf8")
    print(json.dumps(published), flush=True)


if __name__ == "__main__":
    main()
