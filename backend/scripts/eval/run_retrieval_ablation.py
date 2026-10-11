"""Live active-index retrieval ablation; public reviewed questions, no user records."""
import argparse
import asyncio
import hashlib
import json
import math
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def ranking_metrics(documents, case):
    allowed = {(entry["source"], page) for entry in case.get("acceptable_evidence", [])
               for page in entry["pdf_pages"]}
    if not allowed:
        allowed = {(case["gold_source"], case["gold_page"])}
    seen, relevant = set(), []
    for document in documents:
        metadata = document.metadata
        identity = (metadata.get("source_file"), int(float(metadata.get("page", -1))))
        if identity not in seen:
            seen.add(identity)
            relevant.append(identity in allowed)
    rank = next((i + 1 for i, hit in enumerate(relevant) if hit), None)
    dcg = sum(1 / math.log2(i + 2) for i, hit in enumerate(relevant) if hit)
    ideal = sum(1 / math.log2(i + 2) for i in range(min(len(allowed), len(relevant))))
    return {"source_hit": any(source in {s for s, _ in allowed} for source, _ in seen),
            "page_hit": rank is not None, "mrr": 1 / rank if rank else 0,
            "ndcg": dcg / ideal if ideal else 0}


async def run(args):
    from app.core.config import get_settings
    from app.rag import retriever
    from langsmith import Client, tracing_context, traceable
    settings = get_settings()
    cases = json.loads(args.dataset.read_text(encoding="utf-8"))
    if not cases or any(case.get("review_status") != "reviewed" for case in cases):
        raise ValueError("Requires nonempty reviewed gold")
    args.output.mkdir(parents=True, exist_ok=False)
    client = Client(api_key=settings.langsmith_api_key, api_url=settings.langsmith_endpoint)
    translations = {}
    translate = retriever._translate_to_english
    # Freeze the actual translation for each question across the three modes.
    async def fixed_translate(query):
        return translations[query]
    report = {"scope": "active recursive baseline; retrieval only; four-source gold",
        "dataset_sha256": hashlib.sha256(args.dataset.read_bytes()).hexdigest(),
        "namespace": settings.pinecone_namespace, "embedding_model": settings.embedding_model,
        "embedding_dimension": settings.embedding_dimension, "k": args.k,
        "ranking_unit": "deduplicated source/PDF page; acceptable evidence pages, canonical page fallback", "cases": []}
    semaphore = asyncio.Semaphore(3)
    @traceable(name="retrieval-ablation")
    async def one(case, mode, hybrid, rerank):
        async with semaphore:
            started = time.perf_counter()
            try:
                result = await asyncio.wait_for(retriever.retrieve(case["question"], k=args.k,
                    use_hybrid=hybrid, use_rerank=rerank, strict_components=True), 120)
                return {"id": case["id"], "mode": mode, "language": case.get("language"),
                    "split": case.get("split"), "status": "completed", **ranking_metrics(result["docs"], case),
                    "grounded": result["grounded"], "seconds": time.perf_counter() - started,
                    "context": result["context"], "metadata": [doc.metadata for doc in result["docs"]]}
            except Exception as exc:
                return {"id": case["id"], "mode": mode, "status": "failed", "error_type": type(exc).__name__}
    with tracing_context(client=client, project_name=settings.langsmith_project,
                         enabled=settings.langsmith_tracing.lower() == "true"):
        if await asyncio.to_thread(retriever._get_bm25) is None:
            raise RuntimeError("Hybrid experiment requires BM25; fallback is not a valid ablation")
        if await asyncio.to_thread(retriever._get_reranker) is None:
            raise RuntimeError("Full experiment requires reranker; fallback is not a valid ablation")
        report["components_verified"] = {"bm25": True, "reranker": settings.rag_rerank_model}
        for case in cases:
            translations[case["question"]] = await translate(case["question"])
        report["frozen_translations"] = translations
        retriever._translate_to_english = fixed_translate
        try:
            for mode, hybrid, rerank in (("dense", False, False), ("hybrid", True, False), ("full", True, True)):
                rows = await asyncio.gather(*(one(case, mode, hybrid, rerank) for case in cases))
                report["cases"].extend(rows)
                (args.output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                complete = [row for row in rows if row["status"] == "completed"]
                print(json.dumps({"mode": mode, "completed": len(complete), "failed": len(rows) - len(complete),
                    **{metric: sum(row[metric] for row in complete) / len(complete) if complete else None
                       for metric in ("source_hit", "page_hit", "mrr", "ndcg", "seconds")}}), flush=True)
        finally:
            retriever._translate_to_english = translate
    client.flush()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--k", type=int, default=4)
    args = parser.parse_args()
    if args.k < 1:
        parser.error("k must be positive")
    asyncio.run(run(args))
