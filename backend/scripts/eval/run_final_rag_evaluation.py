"""Capture a sealed post-selection RAG evaluation with strict provenance.

This runner evaluates the already-selected production candidate only:
PyPDF/recursive chunks, Gemini 3072 embeddings, hybrid retrieval, no reranker.
It never changes the production index and never tunes from final-set results.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import pickle
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _normalized(text: str) -> str:
    return "".join(str(text).split()).casefold().replace("–", "-").replace("~", "-")


def validate_final_dataset(
    cases: list[dict[str, Any]],
    *,
    prior_cases: list[dict[str, Any]],
    source_dir: Path,
    verify_sources: bool = True,
) -> None:
    if not cases or len({case.get("id") for case in cases}) != len(cases):
        raise ValueError("Final dataset requires non-empty unique case IDs")
    required = {
        "id", "case_group", "question", "language", "split", "gold_source",
        "gold_page", "gold_excerpt", "gold_answer", "document_sha256",
        "review_status", "reviewer", "review_scope", "acceptable_evidence",
        "applicability", "expected_action",
    }
    for case in cases:
        missing = required - set(case)
        if missing:
            raise ValueError(f"Final case {case.get('id')} missing fields: {sorted(missing)}")
        if case["split"] != "final" or case["review_status"] != "reviewed":
            raise ValueError("Final cases must be source-reviewed and split=final")
    prior_groups = {case.get("case_group") for case in prior_cases}
    overlap = sorted({case["case_group"] for case in cases} & prior_groups)
    if overlap:
        raise ValueError(f"Final fact-group overlap with prior evaluation: {overlap}")
    languages = {}
    for case in cases:
        languages.setdefault(case["case_group"], set()).add(case["language"])
    invalid = sorted(group for group, values in languages.items() if values != {"en", "ko"})
    if invalid:
        raise ValueError(f"Each final fact group requires an en/ko language pair: {invalid}")
    if verify_sources:
        for source, expected in {(c["gold_source"], c["document_sha256"]) for c in cases}:
            path = source_dir / source
            if not path.is_file() or _sha(path) != expected:
                raise ValueError(f"Source SHA mismatch: {source}")


def evidence_diagnostics(case: dict[str, Any], documents: list[dict[str, Any]]) -> dict[str, bool]:
    source_page_hit = False
    excerpt_hit = False
    for acceptable in case["acceptable_evidence"]:
        source = acceptable["source"]
        pages = {int(page) for page in acceptable["pdf_pages"]}
        excerpt = _normalized(acceptable["core_excerpt"])
        for document in documents:
            metadata = document.get("metadata", {})
            document_source = metadata.get("source_file") or Path(str(metadata.get("source", ""))).name
            page = metadata.get("page_number", metadata.get("page"))
            if document_source != source:
                continue
            try:
                page_matches = int(page) in pages
            except (TypeError, ValueError):
                page_matches = False
            source_page_hit = source_page_hit or page_matches
            excerpt_hit = excerpt_hit or (page_matches and excerpt in _normalized(document.get("text", "")))
    return {"source_page_hit": source_page_hit, "excerpt_hit": excerpt_hit}


def frozen_identity(dataset: Path, recipe: dict[str, Any]) -> str:
    payload = _sha(dataset) + json.dumps(recipe, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def validate_active_recipe(
    runtime: dict[str, Any], activation: dict[str, Any], chunk_metadata: dict[str, Any]
) -> None:
    expected_runtime = {
        "pinecone_namespace": activation.get("namespace"),
        "embedding_model": activation.get("embedding_model"),
        "embedding_dimension": activation.get("embedding_dimension"),
        "rag_candidate_k": 20,
    }
    for key, expected in expected_runtime.items():
        if runtime.get(key) != expected:
            label = "candidate_k" if key == "rag_candidate_k" else key
            raise ValueError(f"Final recipe {label} mismatch: {runtime.get(key)!r} != {expected!r}")
    expected_chunk = {
        "parser": "pypdf", "chunking": "recursive",
        "embedding_model": activation.get("embedding_model"),
        "embedding_dimension": activation.get("embedding_dimension"),
    }
    for key, expected in expected_chunk.items():
        if chunk_metadata.get(key) != expected:
            raise ValueError(f"Activated chunk {key} mismatch: {chunk_metadata.get(key)!r} != {expected!r}")


def validate_cached_case(row: dict[str, Any], case: dict[str, Any], identity: str) -> bool:
    expected = {
        "identity": identity, "id": case["id"], "case_group": case["case_group"],
        "language": case["language"], "question": case["question"],
        "reference": case["gold_answer"],
    }
    for key, value in expected.items():
        if row.get(key) != value:
            raise ValueError(f"Cached {key} mismatch: {case['id']}")
    if row.get("status") != "completed":
        return False
    required = {"context", "response", "documents", "latency_seconds", "grounded",
                "source_page_hit", "excerpt_hit", "attempts"}
    missing = required - set(row)
    if missing:
        raise ValueError(f"Cached completed result missing fields: {sorted(missing)}")
    return True


def _dump(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _prior_cases(paths: list[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        rows.extend(json.loads(path.read_text(encoding="utf-8")))
    return rows


async def capture(args: argparse.Namespace) -> dict[str, Any]:
    from app.core.config import get_settings
    from app.rag.qa import answer_from_knowledge
    from app.rag.retriever import retrieve
    from langsmith import Client, traceable, tracing_context

    settings = get_settings()
    cases = json.loads(args.dataset.read_text(encoding="utf-8"))
    validate_final_dataset(
        cases,
        prior_cases=_prior_cases(args.prior_datasets),
        source_dir=args.source_dir,
    )
    activation_path = Path(settings.get_chunks_path()).with_name("activation.json")
    if not activation_path.is_file():
        raise ValueError("Final evaluation requires an activated RAG build")
    activation = json.loads(activation_path.read_text(encoding="utf-8"))
    with Path(settings.get_chunks_path()).open("rb") as stream:
        activated_chunks = pickle.load(stream)
    if not activated_chunks:
        raise ValueError("Activated chunk corpus is empty")
    runtime = {key: getattr(settings, key) for key in (
        "pinecone_namespace", "embedding_model", "embedding_dimension", "rag_candidate_k")}
    for chunk in activated_chunks:
        validate_active_recipe(runtime, activation, chunk.metadata)
    recipe = {
        "parser": "pypdf",
        "chunking": "recursive",
        "embedding_model": settings.embedding_model,
        "embedding_dimension": settings.embedding_dimension,
        "namespace": settings.pinecone_namespace,
        "search": "hybrid",
        "reranker": "none",
        "candidate_k": settings.rag_candidate_k,
        "return_k": 4,
        "context_chars": 6000,
        "generation_model": settings.gemini_model,
    }
    if settings.embedding_dimension != 3072:
        raise ValueError("Final recipe is frozen to Gemini 3072-dimensional embeddings")
    identity = frozen_identity(args.dataset, recipe)
    output = args.output / identity
    output.mkdir(parents=True, exist_ok=True)
    manifest = {
        "scope": "sealed post-selection evaluation; new fact groups, not blinded human adjudication",
        "identity": identity,
        "dataset_sha256": _sha(args.dataset),
        "prior_dataset_sha256": {str(path): _sha(path) for path in args.prior_datasets},
        "recipe": recipe,
        "cases": [case["id"] for case in cases],
    }
    manifest_path = output / "manifest.json"
    if manifest_path.exists() and json.loads(manifest_path.read_text(encoding="utf-8")) != manifest:
        raise ValueError("Existing final-evaluation manifest differs")
    _dump(manifest_path, manifest)

    client = Client(api_key=settings.langsmith_api_key, api_url=settings.langsmith_endpoint)

    @traceable(name="final-rag-case", run_type="chain")
    async def one(case: dict[str, Any]) -> dict[str, Any]:
        started = time.perf_counter()
        retrieval = await asyncio.wait_for(
            retrieve(case["question"], k=4, use_hybrid=True, use_rerank=False),
            timeout=args.timeout,
        )
        answer = await asyncio.wait_for(
            answer_from_knowledge(
                case["question"],
                k=4,
                user_region=case.get("region", "KR"),
                retrieval_result=retrieval,
                config={"metadata": {"evaluation_id": identity, "case_id": case["id"]}},
            ),
            timeout=args.timeout,
        )
        docs = [
            {"text": doc.page_content, "metadata": doc.metadata}
            for doc in retrieval.get("docs", [])
        ]
        return {
            "id": case["id"],
            "case_group": case["case_group"],
            "language": case["language"],
            "question": case["question"],
            "reference": case["gold_answer"],
            "context": answer.get("context", retrieval.get("context", "")),
            "response": answer["answer"],
            "grounded": bool(answer.get("grounded")),
            "documents": docs,
            "token_usage": answer.get("token_usage"),
            "latency_seconds": time.perf_counter() - started,
            **evidence_diagnostics(case, docs),
        }

    tracing = str(settings.langsmith_tracing).lower() == "true"
    with tracing_context(
        client=client,
        project_name=settings.langsmith_project,
        enabled=tracing,
        metadata={"evaluation_id": identity, "dataset_sha256": manifest["dataset_sha256"],
                  "evaluation_scope": "final-rag-post-selection"},
    ):
        for index, case in enumerate(cases, 1):
            destination = output / f"case-{case['id']}.json"
            prior_attempts: list[dict[str, Any]] = []
            if destination.exists():
                cached = json.loads(destination.read_text(encoding="utf-8"))
                if validate_cached_case(cached, case, identity):
                    print(f"[{index}/{len(cases)}] cached {case['id']}", flush=True)
                    continue
                prior_attempts = list(cached.get("attempts", []))
            attempts = prior_attempts
            while len(attempts) < args.max_total_attempts:
                attempt = len(attempts)
                try:
                    row = await one(
                        case,
                        langsmith_extra={"metadata": {"evaluation_id": identity,
                            "case_id": case["id"], "split": "final", "attempt": attempt + 1}},
                    )
                    attempts.append({"status": "completed"})
                    row.update(identity=identity, status="completed", attempts=attempts)
                    _dump(destination, row)
                    print(f"[{index}/{len(cases)}] completed {case['id']}", flush=True)
                    break
                except Exception as exc:
                    attempts.append({"status": "failed", "error_type": type(exc).__name__,
                                     "message": str(exc)[:500]})
                    if len(attempts) >= args.max_total_attempts:
                        _dump(destination, {"identity": identity, "id": case["id"],
                                            "case_group": case["case_group"],
                                            "language": case["language"],
                                            "question": case["question"],
                                            "reference": case["gold_answer"],
                                            "status": "failed", "attempts": attempts})
                        print(f"[{index}/{len(cases)}] failed {case['id']}: {type(exc).__name__}", flush=True)
    if tracing:
        client.flush()

    rows = [json.loads((output / f"case-{case['id']}.json").read_text(encoding="utf-8")) for case in cases]
    completed = [row for row in rows if row["status"] == "completed"]
    latencies = sorted(row["latency_seconds"] for row in completed)
    percentile = lambda q: latencies[min(len(latencies) - 1, math.ceil(q * len(latencies)) - 1)] if latencies else None
    report = {
        **manifest,
        "status": "completed" if len(completed) == len(rows) else "failed",
        "completed": len(completed),
        "failed": len(rows) - len(completed),
        "source_page_recall_at_4": sum(row["source_page_hit"] for row in completed) / len(completed) if completed else None,
        "literal_excerpt_recall_at_4": sum(row["excerpt_hit"] for row in completed) / len(completed) if completed else None,
        "grounded_rate": sum(row["grounded"] for row in completed) / len(completed) if completed else None,
        "latency_p50_seconds": percentile(0.50),
        "latency_p95_seconds": percentile(0.95),
        "languages": dict(Counter(row["language"] for row in completed)),
    }
    answers_path = output / "answers.json"
    _dump(answers_path, completed)
    report["answers_sha256"] = _sha(answers_path)
    _dump(output / "capture-report.json", report)
    print(json.dumps({"directory": str(output), **{key: report[key] for key in (
        "status", "completed", "failed", "source_page_recall_at_4",
        "literal_excerpt_recall_at_4", "grounded_rate", "latency_p95_seconds")}}, ensure_ascii=False), flush=True)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--prior-datasets", type=Path, nargs="+", required=True)
    parser.add_argument("--source-dir", type=Path, default=REPO_ROOT / "docs/nutrition")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--max-total-attempts", type=int, default=3)
    return parser


if __name__ == "__main__":
    report = asyncio.run(capture(build_parser().parse_args()))
    if report["status"] != "completed":
        raise SystemExit(1)
