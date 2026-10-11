"""Controlled local parser x chunking matrix; never activates production indexes.

Optional reviewed retrieval gold: id/question/gold_source/gold_page (PDF 1-based),
gold_excerpt/gold_answer/review_status. Results export the exact contexts for Ragas.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from app.rag.chunking import ChunkConfig, chunk_blocks, expand_context


def parse_worker(source, parser, pages, output, timeout, docling_backend="docling_parse"):
    env = dict(os.environ)
    runtime = ROOT / "artifacts/parser-runtime"
    env["PYTHONPATH"] = str(runtime) + os.pathsep + str(ROOT)
    env["HF_HOME"] = str(ROOT / "artifacts/model-cache")
    env["OMP_NUM_THREADS"] = "2"
    env["TOKENIZERS_PARALLELISM"] = "false"
    job = output / "jobs" / f"{hashlib.sha256(str(source).encode()).hexdigest()[:12]}-{parser}.json"
    job.parent.mkdir(parents=True, exist_ok=True)
    job.write_text(json.dumps({"source": source, "pages": pages, "parser": parser, "docling_backend": docling_backend, "output": str(output / "parses")}, ensure_ascii=False), encoding="utf-8")
    start = time.perf_counter()
    try:
        process = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--worker", str(job)],
                                 env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "elapsed_seconds": time.perf_counter() - start}
    log = output / "jobs" / f"{job.stem}.log"
    log.write_text(process.stdout + process.stderr, encoding="utf-8")
    native_failure = "fatal exception: access violation" in (process.stdout + process.stderr).lower()
    if process.returncode or native_failure:
        return {"status": "failed", "exit_code": process.returncode, "failure_type": "native_exception" if native_failure else "worker_error",
                "log": str(log), "elapsed_seconds": time.perf_counter() - start}
    result_path = Path(process.stdout.strip().splitlines()[-1])
    blocks = json.loads((result_path / "blocks.json").read_text(encoding="utf-8"))["blocks"]
    manifest = json.loads((result_path / "manifest.json").read_text(encoding="utf-8"))
    if any(block["pdf_page"] not in pages for block in blocks):
        return {"status": "failed", "failure_type": "page_alignment", "log": str(log), "elapsed_seconds": time.perf_counter() - start}
    return {"status": "completed", "artifact": str(result_path), "manifest": manifest, "blocks": blocks,
            "elapsed_seconds": time.perf_counter() - start}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", type=Path)
    parser.add_argument("--manifest", type=Path, default=ROOT.parent / "docs/nutrition/corpus_manifest.json")
    parser.add_argument("--pages", type=Path, default=ROOT.parent / "docs/rag_experiments/parser_pages.json")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/rag-matrix")
    parser.add_argument("--parsers", nargs="+", choices=["pypdf", "pdfplumber", "docling"], default=["pypdf", "pdfplumber", "docling"])
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--docling-backend", choices=["docling_parse", "pdfium"], default="docling_parse")
    parser.add_argument("--dataset", type=Path)
    parser.add_argument("--reuse-report", type=Path, help="Rebuild bundles from existing parse artifacts without rerunning parsers")
    parser.add_argument("--k", type=int, default=4)
    parser.add_argument("--max-context-chars", type=int, default=6000)
    args = parser.parse_args()
    if args.worker:
        from app.rag.ingestion import SourceDocument, parse_document
        job = json.loads(args.worker.read_text(encoding="utf-8"))
        job["source"]["path"] = Path(job["source"]["path"])
        print(parse_document(SourceDocument(**job["source"]), Path(job["output"]), parser=job["parser"], pages=job["pages"], docling_backend=job.get("docling_backend", "docling_parse")))
        return
    if args.k < 1 or args.timeout < 1:
        parser.error("k and timeout must be positive")
    sources = json.loads(args.manifest.read_text(encoding="utf-8"))
    selections = json.loads(args.pages.read_text(encoding="utf-8"))
    if set(selections) != {s["path"] for s in sources}:
        parser.error("Page selection must cover exactly the manifest corpus")
    gold = json.loads(args.dataset.read_text(encoding="utf-8")) if args.dataset else []
    if any(g.get("review_status") != "reviewed" for g in gold):
        parser.error("Quality evaluation requires reviewed gold; draft examples cannot produce final scores")
    args.output.mkdir(parents=True, exist_ok=True)
    reused = json.loads(args.reuse_report.read_text(encoding="utf-8")) if args.reuse_report else None
    if reused and reused["manifest_sha256"] != hashlib.sha256(args.manifest.read_bytes()).hexdigest():
        parser.error("Cannot reuse artifacts from a different corpus manifest")
    report = {"scope": "selected-page pilot", "corpus_documents": len(sources), "selected_pages": sum(len(p) for p in selections.values()),
        "manifest_sha256": hashlib.sha256(args.manifest.read_bytes()).hexdigest(), "gold_count": len(gold),
        "quality_status": "not_evaluated_without_reviewed_gold" if not gold else "reviewed_gold", "parsers": [], "recipes": []}
    for name in args.parsers:
        bundles = {strategy: {"search_chunks": [], "parents": {}} for strategy in ("page", "parent_child", "section")}
        completed = 0
        for entry in sources:
            source = {**entry, "path": str((args.manifest.parent / entry["path"]).resolve())}
            if reused:
                previous = next(row for row in reused["parsers"] if row["parser"] == name and row["source_file"] == entry["path"])
                result = {**previous}
                if result["status"] == "completed":
                    artifact = Path(result["artifact"])
                    result["blocks"] = json.loads((artifact / "blocks.json").read_text(encoding="utf-8"))["blocks"]
                    result["manifest"] = json.loads((artifact / "manifest.json").read_text(encoding="utf-8"))
                    if result["manifest"]["selected_pages"] != selections[entry["path"]]:
                        parser.error("Cannot reuse a different page selection")
            else:
                result = parse_worker(source, name, selections[entry["path"]], args.output, args.timeout, args.docling_backend)
            summary = {"parser": name, "source_file": entry["path"], **{k: v for k, v in result.items() if k not in {"blocks", "manifest"}}}
            if result["status"] == "completed":
                completed += 1
                blocks = result["blocks"]
                summary.update(text_chars=sum(len(b["text"]) for b in blocks), tables=sum(b["kind"] == "table" for b in blocks),
                    pictures=sum(b["kind"] == "image" for b in blocks), text_pages=len({b["pdf_page"] for b in blocks if b["text"].strip()}),
                    parser_version=result["manifest"]["parser_version"], quality_review_status="unreviewed")
                for strategy in bundles:
                    bundle = chunk_blocks(blocks, {**entry, "source_file": entry["path"], "sha256": result["manifest"]["sha256"], "parser": name}, ChunkConfig(strategy=strategy))
                    bundles[strategy]["search_chunks"].extend(bundle["search_chunks"])
                    bundles[strategy]["parents"].update(bundle["parents"])
            report["parsers"].append(summary)
            (args.output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"{name}: {entry['path']} {result['status']}", flush=True)
        for strategy, bundle in bundles.items():
            path = args.output / f"{name}-{strategy}.json"
            path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
            row = {"parser": name, "chunking": strategy, "search_chunks": len(bundle["search_chunks"]),
                "parents": len(bundle["parents"]), "complete_corpus": completed == len(sources), "bundle": str(path)}
            if gold and row["complete_corpus"]:
                row.update(evaluate_sparse(bundle, gold, args.k, args.output / f"{name}-{strategy}-contexts.json", args.max_context_chars))
            report["recipes"].append(row)
        (args.output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(args.output / "report.json")


def evaluate_sparse(bundle, gold, k, output, max_context_chars=6000):
    from rank_bm25 import BM25Okapi
    from app.rag.retriever import kiwi_tokenize
    import numpy as np
    chunks = bundle["search_chunks"]
    if not chunks:
        raise ValueError("No searchable chunks")
    bm25 = BM25Okapi([kiwi_tokenize(c["text"]) for c in chunks])
    samples = []
    for case in gold:
        started = time.perf_counter()
        scores = bm25.get_scores(kiwi_tokenize(case["question"]))
        hits = [chunks[i]["id"] for i in np.argsort(-scores, kind="stable")[:k] if scores[i] > 0]
        contexts = expand_context(bundle, hits)
        remaining = max_context_chars
        limited = []
        for context in contexts:
            if remaining <= 0:
                break
            text = context["text"][:remaining]
            limited.append({**context, "text": text, "context_truncated": len(text) < len(context["text"])})
            remaining -= len(text)
        contexts = limited
        relevant = [c for c in contexts if c["metadata"]["source_file"] == case["gold_source"]]
        samples.append({**case, "retrieved_contexts": [c["text"] for c in contexts], "context_metadata": [c["metadata"] for c in contexts],
            "source_hit": bool(relevant), "page_hit": any(case["gold_page"] in c["metadata"]["pdf_pages"] for c in relevant),
            "excerpt_hit": any(" ".join(case["gold_excerpt"].split()) in " ".join(c["text"].split()) for c in relevant),
            "context_chars": sum(len(c["text"]) for c in contexts), "retrieval_seconds": time.perf_counter() - started})
    output.write_text(json.dumps(samples, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"retrieval": "bm25_pilot_only", "k": k, "max_context_chars": max_context_chars, **{metric: sum(s[metric] for s in samples) / len(samples)
            for metric in ("source_hit", "page_hit", "excerpt_hit", "context_chars", "retrieval_seconds")}, "samples": str(output)}


if __name__ == "__main__":
    main()
