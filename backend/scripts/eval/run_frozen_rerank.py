"""Bounded development-only reranking comparison with identical saved candidates."""
import argparse
import asyncio
import hashlib
import json
import logging
from importlib.metadata import version
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from langchain_core.documents import Document
from scripts.eval.run_retrieval_ablation import ranking_metrics


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf8")


def validate_frozen_dataset(frozen, dataset):
    if frozen["dataset_sha256"] != hashlib.sha256(dataset.read_bytes()).hexdigest():
        raise ValueError("Frozen dataset fingerprint mismatch")
    cases = json.loads(dataset.read_text(encoding="utf8"))
    ids = [case["id"] for case in cases]
    frozen_ids = [case["id"] for case in frozen["cases"]]
    if (not cases or len(set(ids)) != len(ids) or len(frozen_ids) != len(ids) or set(frozen_ids) != set(ids)
            or any(case.get("split") != "development" or case.get("review_status") != "reviewed" for case in cases)):
        raise ValueError("Frozen dataset requires exactly the reviewed development cases")


def cached_row(path, signature):
    row = json.loads(path.read_text(encoding="utf8"))
    if row.get("cache_signature") != signature:
        raise ValueError("Cached ranking configuration differs; use a new output directory")
    return row


def ranking_signature(frozen_path, variant, model):
    files = [Path(__file__), ROOT / "app/core/jev.py", ROOT / "app/rag/jev_reranker.py", ROOT / "app/rag/retriever.py"]
    configuration = {"candidates_sha256": hashlib.sha256(frozen_path.read_bytes()).hexdigest(),
        "variant": variant, "model": model, "return_k": 4, "context_chars": 6000,
        "code_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in files},
        "dependencies": {name: version(name) for name in ("flashrank", "onnxruntime", "httpx")}}
    return hashlib.sha256(json.dumps(configuration, sort_keys=True).encode()).hexdigest()


def evidence_present(documents, case):
    """Literal excerpt diagnostic, not answer accuracy or semantic evidence recall."""
    normalize = lambda text: "".join(text.split()).casefold()
    return any(normalize(case["gold_excerpt"]) in normalize(doc.page_content)
               and doc.metadata.get("source_file") == case["gold_source"] for doc in documents)


async def run(args):
    from app.core.config import get_settings
    from app.rag import retriever
    from app.rag.jev_reranker import rerank as jev_rerank
    from app.core.jev import JevClient
    from app.agents.runtime import ExecutionBudget
    from flashrank import Ranker, RerankRequest
    settings = get_settings()
    cases = json.loads(args.dataset.read_text(encoding="utf8"))
    if any(case["split"] != "development" or case["review_status"] != "reviewed" for case in cases):
        raise ValueError("Only reviewed development cases may be tuned")
    args.output.mkdir(parents=True, exist_ok=True)
    fingerprint = hashlib.sha256(args.dataset.read_bytes()).hexdigest()
    frozen_path = args.output / "candidates.json"
    if frozen_path.exists():
        frozen = json.loads(frozen_path.read_text(encoding="utf8"))
        if frozen["dataset_sha256"] != fingerprint:
            raise ValueError("Cannot reuse candidates from a different dataset")
    else:
        prior = json.loads(args.translations.read_text(encoding="utf8"))["frozen_translations"]
        store = await asyncio.to_thread(retriever.get_vector_store)
        if await asyncio.to_thread(retriever._get_bm25) is None:
            raise RuntimeError("BM25 required; no silent fallback")
        frozen = {"dataset_sha256": fingerprint, "namespace": settings.pinecone_namespace,
                  "embedding_model": settings.embedding_model, "embedding_dimension": settings.embedding_dimension,
                  "candidate_k": 20, "return_k": 4, "context_chars": 6000, "cases": []}
        for case in cases:
            query = case["question"]
            translated = prior[query]
            dense, _ = await asyncio.to_thread(retriever._dense_search, store, translated, 20)
            sparse = await asyncio.to_thread(retriever._sparse_search, translated, strict=True)
            candidates = retriever._rrf(dense, sparse)[:20]
            if query != translated:
                original, _ = await asyncio.to_thread(retriever._dense_search, store, query, 20)
                sparse_original = await asyncio.to_thread(retriever._sparse_search, query, strict=True)
                candidates = retriever._rrf(candidates, retriever._rrf(original, sparse_original)[:20])[:20]
            frozen["cases"].append({"id": case["id"], "translated": translated,
                "documents": [{"text": doc.page_content, "metadata": doc.metadata} for doc in candidates]})
            print("captured " + case["id"], flush=True)
        dump(frozen_path, frozen)
    validate_frozen_dataset(frozen, args.dataset)
    by_id = {case["id"]: case for case in cases}
    logging.getLogger("httpx").setLevel(logging.WARNING)
    variants = [("none", None), ("minilm", "ms-marco-MiniLM-L-12-v2"),
                ("multibert", "ms-marco-MultiBERT-L-12"), ("jev", settings.jev_model)]
    variants = [(name, model) for name, model in variants if name in args.variants]
    rows = []
    client = JevClient()
    for name, model in variants:
        if name == "jev" and not settings.typesafe_api_key:
            continue
        signature = ranking_signature(frozen_path, name, model)
        ranker = Ranker(model_name=model, cache_dir=str(ROOT / "artifacts/flashrank-models")) if name in ("minilm", "multibert") else None
        for repeat in range(args.repeats if name == "jev" else 1):
            for item in frozen["cases"]:
                destination = args.output / f'{name}-{repeat}-{item["id"]}.json'
                if destination.exists():
                    rows.append(cached_row(destination, signature))
                    continue
                case = by_id[item["id"]]
                docs = [Document(page_content=d["text"], metadata=d["metadata"]) for d in item["documents"]]
                started = time.perf_counter()
                row = {"cache_signature": signature, "id": case["id"], "case_group": case["case_group"], "language": case["language"],
                       "variant": name, "model": model, "repeat": repeat,
                       "candidate_page_hit": ranking_metrics(docs, case)["page_hit"],
                       "candidate_excerpt_hit": evidence_present(docs, case)}
                try:
                    events, fallback = [], None
                    if name == "jev":
                        result = await jev_rerank(item["translated"], docs, client=client,
                            budget=ExecutionBudget(max_model_calls=20, timeout_seconds=60), k=4)
                        selected, events, fallback = result["docs"], result["events"], result["fallback_reason"]
                    elif ranker:
                        scores = await asyncio.to_thread(ranker.rerank, RerankRequest(query=item["translated"],
                            passages=[{"id": i, "text": doc.page_content} for i, doc in enumerate(docs)]))
                        selected = [docs[value["id"]] for value in scores[:4]]
                    else:
                        selected = docs[:4]
                    row.update(status="completed", seconds=time.perf_counter() - started,
                        fallback_reason=fallback, events=events, **ranking_metrics(selected, case),
                        excerpt_hit=evidence_present(selected, case),
                        context=retriever.format_docs(selected, max_docs=4)[:6000],
                        documents=[{"text": doc.page_content, "metadata": doc.metadata} for doc in selected])
                except Exception as exc:
                    row.update(status="failed", error_type=type(exc).__name__, seconds=time.perf_counter() - started)
                dump(destination, row)
                rows.append(row)
                print(json.dumps({key: row.get(key) for key in ("variant", "repeat", "id", "page_hit", "excerpt_hit", "fallback_reason", "status")}), flush=True)
    summaries = {}
    for name, _ in variants:
        subset = [row for row in rows if row["variant"] == name]
        completed = [row for row in subset if row["status"] == "completed"]
        summaries[name] = {"completed": len(completed), "failed": len(subset) - len(completed),
            "fallbacks": sum(bool(row.get("fallback_reason")) for row in completed),
            **{metric: sum(row[metric] for row in completed) / len(completed) if completed else None
               for metric in ("page_hit", "mrr", "ndcg", "excerpt_hit", "seconds")}}
    dump(args.output / "report.json", {"scope": "development retrieval-only; no answer-quality or deployment claim",
         "dataset_sha256": fingerprint, "frozen_provenance": {key: frozen[key] for key in
             ("namespace", "embedding_model", "embedding_dimension", "candidate_k", "return_k", "context_chars")},
         "summaries": summaries, "cases": rows})
    print(json.dumps(summaries), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--translations", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, choices=(1, 3), default=1)
    parser.add_argument("--variants", nargs="+", choices=("none", "minilm", "multibert", "jev"),
                        default=["none", "minilm", "multibert", "jev"])
    asyncio.run(run(parser.parse_args()))
