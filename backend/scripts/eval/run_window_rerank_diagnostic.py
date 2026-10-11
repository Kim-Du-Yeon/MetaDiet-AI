"""One bounded truncation diagnostic: score 400-char children, return original parents."""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from flashrank import Ranker, RerankRequest
from langchain_core.documents import Document
from scripts.eval.run_retrieval_ablation import ranking_metrics
from scripts.eval.run_frozen_rerank import evidence_present, validate_frozen_dataset


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    args = parser.parse_args()
    cases = {row["id"]: row for row in json.loads(args.dataset.read_text(encoding="utf8"))}
    frozen = json.loads((args.directory / "candidates.json").read_text(encoding="utf8"))
    validate_frozen_dataset(frozen, args.dataset)
    ranker = Ranker(model_name="ms-marco-MiniLM-L-12-v2", cache_dir=str(ROOT / "artifacts/flashrank-models"))
    rows = []
    for item in frozen["cases"]:
        case = cases[item["id"]]
        docs = [Document(page_content=d["text"], metadata=d["metadata"]) for d in item["documents"]]
        passages, parents = [], {}
        for index, doc in enumerate(docs):
            for start in range(0, len(doc.page_content), 350):
                child = len(passages)
                parents[child] = index
                passages.append({"id": child, "text": doc.page_content[start:start + 400]})
                if start + 400 >= len(doc.page_content):
                    break
        started = time.perf_counter()
        ranked = ranker.rerank(RerankRequest(query=item["translated"], passages=passages))
        scores = {}
        for result in ranked:
            parent = parents[result["id"]]
            scores[parent] = max(scores.get(parent, 0), float(result["score"]))
        order = sorted(range(len(docs)), key=lambda i: -scores.get(i, 0))
        selected = [docs[i] for i in order[:4]]
        rows.append({"id": case["id"], "case_group": case["case_group"], "seconds": time.perf_counter() - started,
            **ranking_metrics(selected, case), "excerpt_hit": evidence_present(selected, case),
            "child_pairs": len(passages), "documents": [{"text": d.page_content, "metadata": d.metadata} for d in selected]})
        print("window diagnostic " + case["id"], flush=True)
    summary = {metric: sum(row[metric] for row in rows) / len(rows) for metric in ("page_hit", "excerpt_hit", "mrr", "seconds")}
    output = {"scope": "development truncation diagnostic, same 20 parent candidates; not an embedding/chunking recipe comparison",
        "model": "ms-marco-MiniLM-L-12-v2", "child_chars": 400, "overlap": 50, "aggregation": "max child relevance",
        "dataset_sha256": frozen["dataset_sha256"], "summary": summary, "cases": rows}
    (args.directory / "window-diagnostic.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
