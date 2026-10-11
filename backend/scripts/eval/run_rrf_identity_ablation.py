"""Compare old/new RRF identities using the exact same component rank lists."""
import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.eval.run_retrieval_ablation import ranking_metrics
from scripts.eval.run_frozen_rerank import evidence_present


def legacy_rrf(first, second):
    scores, docs = {}, {}
    for listing in (first, second):
        for rank, doc in enumerate(listing):
            key = f"{doc.metadata.get('source_file', doc.metadata.get('source', ''))}|{doc.metadata.get('page', '')}|{doc.page_content[:60]}"
            docs[key] = doc
            scores[key] = scores.get(key, 0) + 1 / (61 + rank)
    return [docs[key] for key in sorted(scores, key=scores.get, reverse=True)]


async def run(args):
    from app.rag import retriever
    from app.core.config import get_settings
    settings = get_settings()
    cases = json.loads(args.dataset.read_text(encoding="utf8"))
    if any(case["split"] != "development" for case in cases):
        raise ValueError("Only development cases may be tuned")
    translations = json.loads(args.translations.read_text(encoding="utf8"))["frozen_translations"]
    args.output.mkdir(parents=True, exist_ok=False)
    store = await asyncio.to_thread(retriever.get_vector_store)
    report = {"dataset_sha256": hashlib.sha256(args.dataset.read_bytes()).hexdigest(),
              "namespace": settings.pinecone_namespace, "scope": "RRF identity only, same component lists, no reranker", "cases": []}
    for case in cases:
        original, translated = case["question"], translations[case["question"]]
        dense, _ = await asyncio.to_thread(retriever._dense_search, store, translated, 20)
        sparse = await asyncio.to_thread(retriever._sparse_search, translated, strict=True)
        dense_original, sparse_original = [], []
        if original != translated:
            dense_original, _ = await asyncio.to_thread(retriever._dense_search, store, original, 20)
            sparse_original = await asyncio.to_thread(retriever._sparse_search, original, strict=True)
        serialized = lambda docs: [{"text": doc.page_content, "metadata": doc.metadata} for doc in docs]
        inputs = {"translated": translated, "dense": serialized(dense), "sparse": serialized(sparse),
                  "dense_original": serialized(dense_original), "sparse_original": serialized(sparse_original)}
        (args.output / (case["id"] + "-components.json")).write_text(json.dumps(inputs, ensure_ascii=False), encoding="utf8")
        for name, fuse in (("legacy", legacy_rrf), ("normalized_fulltext", retriever._rrf)):
            candidates = fuse(dense, sparse)[:20]
            if original != translated:
                candidates = fuse(candidates, fuse(dense_original, sparse_original)[:20])[:20]
            selected = candidates[:4]
            report["cases"].append({"id": case["id"], "case_group": case["case_group"], "variant": name,
                **ranking_metrics(selected, case), "excerpt_hit": evidence_present(selected, case),
                "unique_candidates": len({retriever._doc_key(doc) for doc in candidates}),
                "context": retriever.format_docs(selected), "documents": serialized(selected)})
        (args.output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
        print("compared " + case["id"], flush=True)
    print(json.dumps({name: {metric: sum(row[metric] for row in report["cases"] if row["variant"] == name) / len(cases)
        for metric in ("page_hit", "excerpt_hit", "mrr", "unique_candidates")} for name in ("legacy", "normalized_fulltext")}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--translations", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    asyncio.run(run(parser.parse_args()))
