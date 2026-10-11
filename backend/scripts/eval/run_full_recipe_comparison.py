"""Two bounded full-corpus recipes, local exact vector indexes; never changes production.

Stages are resumable. Parse workers are isolated; failed batches get one split retry.
Gold is development-only, query translations and embeddings shared across recipes.
"""
import argparse
import hashlib
import json
import math
import re
import sys
import os
import subprocess
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from importlib.metadata import version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from app.rag.chunking import ChunkConfig, chunk_blocks, expand_context
from scripts.eval.compare_rag_recipes import parse_worker

RECIPES = (("docling", "page"), ("pdfplumber", "section"))


def persistent_worker(job):
    from app.rag.ingestion import SourceDocument, parse_document
    source = SourceDocument(**{**job["source"], "path": Path(job["source"]["path"])})
    name, output = job["parser"], Path(job["output"])
    for pages in job["batches"]:
        row_path = output / "batches" / name / f"{source.path.stem}-{pages[0]:04d}.json"
        if row_path.exists():
            cached = json.loads(row_path.read_text(encoding="utf8"))
            if cached["status"] == "completed":
                cached_pages = []
                for part in cached["parts"]:
                    artifact = Path(part["artifact"])
                    manifest = json.loads((artifact / "manifest.json").read_text(encoding="utf8"))
                    validate_parse_manifest(manifest, job["source_sha"], manifest["selected_pages"], name, job["parser_version"])
                    if name == "docling":
                        validate_cached_docling_pages(artifact, manifest["selected_pages"])
                    cached_pages.extend(manifest["selected_pages"])
                if sorted(cached_pages) != pages or len(set(cached_pages)) != len(cached_pages):
                    raise ValueError("Cached page coverage mismatch")
                continue
        attempts = []
        def convert(selected):
            started = time.perf_counter()
            try:
                artifact = parse_document(source, output / "persistent-parses", parser=name, pages=selected, docling_backend="pdfium")
                part = {"status": "completed", "artifact": str(artifact), "pages": selected, "elapsed_seconds": time.perf_counter() - started}
            except Exception as exc:
                part = {"status": "failed", "pages": selected, "error_type": type(exc).__name__, "elapsed_seconds": time.perf_counter() - started}
            attempts.append(part)
            return part
        first = convert(pages)
        parts = [first]
        if first["status"] != "completed" and len(pages) > 1:
            mid = len(pages) // 2
            parts = [convert(pages[:mid]), convert(pages[mid:])]
        dump(row_path, {"parser": name, "source_file": source.path.name, "pages": pages,
                       "status": "completed" if all(p["status"] == "completed" for p in parts) else "failed", "parts": parts, "attempts": attempts})
        print(f"persistent {name} {source.path.name} {pages[0]}-{pages[-1]} {parts[-1]['status']}", flush=True)


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf8")
    temporary.replace(path)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized(text):
    # Parsers can render the same numeric range with an en dash or hyphen.
    # Preserve signs; never erase punctuation to make a numeric match.
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"(?<=\d)\s*\u2013\s*(?=\d)", "-", text)
    return re.sub(r"\s+", "", text).casefold()


def validate_gold(cases):
    if not cases or len({c["id"] for c in cases}) != len(cases) or any(
        c.get("review_status") != "reviewed" or c.get("split") != "development" for c in cases
    ):
        raise ValueError("Requires unique reviewed development cases; heldout is sealed")


def validate_batches(rows, page_count):
    pages = [p for r in rows if r["status"] == "completed" for p in r["pages"]]
    if len(pages) != len(set(pages)) or set(pages) != set(range(1, page_count + 1)):
        raise ValueError("Incomplete or duplicated parser page coverage")


def validate_embedding_identity(marker, model, dimension):
    if dimension != 3072 or marker.get("model") != model or marker.get("dimension") != dimension:
        raise ValueError("Embedding model/dimension mismatch")


def validate_parse_manifest(manifest, source_sha, pages, parser, parser_version):
    config = manifest.get("effective_config", {})
    if (manifest.get("sha256") != source_sha or manifest.get("selected_pages") != pages
        or manifest.get("parser") != parser or manifest.get("parser_version") != parser_version
        or config.get("ocr") is not False
        or (parser == "docling" and config.get("docling_backend") != "pdfium")):
        raise ValueError("Cached parse source/page/runtime/config mismatch")


def validate_cached_docling_pages(artifact, pages):
    canonical = json.loads((artifact / "document.json").read_text(encoding="utf8"))
    actual = [int(page) for document in canonical["documents"] for page in document["pages"]]
    if sorted(actual) != pages or len(set(actual)) != len(actual):
        raise ValueError("Cached Docling actual conversion coverage is incomplete")


def pack_context(items, max_chars):
    text, delivered = "", []
    for item in items:
        meta = item["metadata"]
        header = f"[출처: {meta['source_file']}, p.{','.join(map(str, meta['pdf_pages']))}]\n"
        separator = "\n\n" if text else ""
        remaining = max_chars - len(text) - len(separator) - len(header)
        if remaining < 1:
            break
        part = item["text"][:remaining]
        text += separator + header + part
        delivered.append({**item, "text": part, "context_truncated": len(part) < len(item["text"])})
    return text, delivered


def evidence_metrics(items, case):
    allowed = {(e["source"], p) for e in case.get("acceptable_evidence", []) for p in e["pdf_pages"]}
    if not allowed:
        allowed = {(case["gold_source"], case["gold_page"])}
    rank, excerpt = None, False
    for index, item in enumerate(items, 1):
        meta = item["metadata"]
        matching = any((meta["source_file"], p) in allowed for p in meta["pdf_pages"])
        excerpt |= matching and normalized(case["gold_excerpt"]) in normalized(item["text"])
        if matching and rank is None:
            rank = index
    return {"page_hit": rank is not None, "excerpt_hit": bool(excerpt), "mrr": 1 / rank if rank else 0}


def parse_stage(args):
    from pypdf import PdfReader
    entries = json.loads(args.manifest.read_text(encoding="utf8"))
    counts = {e["path"]: len(PdfReader(args.manifest.parent / e["path"]).pages) for e in entries}
    runtime = ROOT / "artifacts/parser-runtime"
    sys.path.insert(0, str(runtime))
    versions = {package: version(package) for package in ("docling", "docling-core", "pdfplumber", "pypdf", "pypdfium2", "torch", "transformers")}
    sys.path.remove(str(runtime))
    identity = {"manifest": sha(args.manifest), "sources": {e["path"]: sha(args.manifest.parent / e["path"]) for e in entries},
                "code": {str(p.relative_to(ROOT)): sha(p) for p in [Path(__file__), ROOT / "app/rag/chunking.py", ROOT / "app/rag/ingestion.py", ROOT / "scripts/eval/compare_rag_recipes.py"]},
                "batch_pages": args.batch_pages, "recipes": RECIPES, "docling_backend": "pdfium", "ocr": False, "runtime_versions": versions}
    identity_path = args.output / "parse-identity.json"
    # JSON round-trip ensures tuples compare equally on resume.
    identity = json.loads(json.dumps(identity))
    if identity_path.exists() and json.loads(identity_path.read_text(encoding="utf8")) != identity:
        raise ValueError("Parse identity changed; use a new output directory")
    dump(identity_path, identity)
    tasks = [(name, e, list(range(start, min(start + args.batch_pages, counts[e["path"]] + 1))))
             for name, _ in RECIPES for e in entries for start in range(1, counts[e["path"]] + 1, args.batch_pages)]

    def run(task):
        name, entry, pages = task
        job_path = args.output / "batches" / name / f"{Path(entry['path']).stem}-{pages[0]:04d}.json"
        if job_path.exists():
            previous = json.loads(job_path.read_text(encoding="utf8"))
            if previous["status"] == "completed" and all(Path(r["artifact"]).exists() for r in previous["parts"]):
                cached_pages = []
                for part in previous["parts"]:
                    artifact = Path(part["artifact"])
                    manifest = json.loads((artifact / "manifest.json").read_text(encoding="utf8"))
                    validate_parse_manifest(manifest, identity["sources"][entry["path"]], manifest["selected_pages"], name, versions[name])
                    if name == "docling":
                        validate_cached_docling_pages(artifact, manifest["selected_pages"])
                    cached_pages.extend(manifest["selected_pages"])
                if sorted(cached_pages) != pages or len(cached_pages) != len(set(cached_pages)):
                    raise ValueError("Cached batch pages differ")
                return previous
        source = {**entry, "path": str((args.manifest.parent / entry["path"]).resolve())}
        folder = args.output / "workers" / name / f"{Path(entry['path']).stem}-{pages[0]:04d}"
        first = parse_worker(source, name, pages, folder, args.timeout, "pdfium")
        parts = [first]
        attempts = [{k: v for k, v in first.items() if k not in {"blocks", "manifest"}}]
        if first["status"] != "completed" and len(pages) > 1:
            midpoint = len(pages) // 2
            parts = [parse_worker(source, name, sub, folder / f"retry-{i}", args.timeout, "pdfium")
                     for i, sub in enumerate((pages[:midpoint], pages[midpoint:]))]
            attempts.extend({k: v for k, v in p.items() if k not in {"blocks", "manifest"}} for p in parts)
        row = {"parser": name, "source_file": entry["path"], "pages": pages,
               "status": "completed" if all(p["status"] == "completed" for p in parts) else "failed",
               "parts": [{k: v for k, v in p.items() if k not in {"blocks", "manifest"}} for p in parts], "attempts": attempts}
        dump(job_path, row)
        print(f"parse {name} {entry['path']} {pages[0]}-{pages[-1]} {row['status']}", flush=True)
        return row

    if args.persistent:
        def document_job(name, entry):
            filename = args.output / "persistent-jobs" / f"{name}-{Path(entry['path']).stem}.json"
            source = {**entry, "path": str((args.manifest.parent / entry["path"]).resolve())}
            batches = [pages for parser, candidate, pages in tasks if parser == name and candidate["path"] == entry["path"]]
            dump(filename, {"source": source, "parser": name, "source_sha": identity["sources"][entry["path"]],
                            "parser_version": versions[name], "output": str(args.output), "batches": batches})
            env = {**os.environ, "PYTHONPATH": str(runtime) + os.pathsep + str(ROOT), "HF_HOME": str(ROOT / "artifacts/model-cache"),
                   "OMP_NUM_THREADS": "2", "TOKENIZERS_PARALLELISM": "false", "PYTHONIOENCODING": "utf-8"}
            log = filename.with_suffix(".log")
            with log.open("w", encoding="utf8") as stream:
                try:
                    result = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--worker-job", str(filename)],
                                            env=env, stdout=stream, stderr=stream, timeout=1800)
                    code = result.returncode
                except subprocess.TimeoutExpired:
                    code = "timeout"
            print(f"document worker {name} {entry['path']} exit={code}", flush=True)
            if code != 0:
                raise RuntimeError(f"Document worker failed: {name}/{entry['path']} ({code})")
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(document_job, name, entry) for name, _ in RECIPES for entry in entries]
            for future in as_completed(futures):
                future.result()
        rows = [json.loads(p.read_text(encoding="utf8")) for p in (args.output / "batches").rglob("*.json")]
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            rows = [future.result() for future in as_completed([pool.submit(run, t) for t in tasks])]
    summary = {"scope": "full selected ten PDFs", "pages": sum(counts.values()), "documents": len(entries), "recipes": []}
    for name, strategy in RECIPES:
        bundle = {"search_chunks": [], "parents": {}}
        structural = []
        for entry in entries:
            selected = sorted([r for r in rows if r["parser"] == name and r["source_file"] == entry["path"]], key=lambda r: r["pages"][0])
            validate_batches(selected, counts[entry["path"]])
            blocks = []
            parser_versions = set()
            for row in selected:
                for part in row["parts"]:
                    artifact = Path(part["artifact"])
                    parser_versions.add(json.loads((artifact / "manifest.json").read_text(encoding="utf8"))["parser_version"])
                    for block in json.loads((artifact / "blocks.json").read_text(encoding="utf8"))["blocks"]:
                        # Docling item references restart per batch; qualify with page range.
                        blocks.append({**block, "id": f"batch-{row['pages'][0]}:{artifact.parent.name}:{block['id']}"})
            metadata = {**entry, "source_file": entry["path"], "sha256": identity["sources"][entry["path"]], "parser": name}
            result = chunk_blocks(blocks, metadata, ChunkConfig(strategy=strategy))
            bundle["search_chunks"].extend(result["search_chunks"])
            bundle["parents"].update(result["parents"])
            dump(args.output / "blocks" / name / (entry["path"] + ".json"), {"blocks": blocks})
            structural.append({"source": entry["path"], "pages": counts[entry["path"]], "text_pages": len({b["pdf_page"] for b in blocks if b["text"].strip()}),
                "tables": sum(b["kind"] == "table" for b in blocks), "images": sum(b["kind"] == "image" for b in blocks), "versions": sorted(parser_versions)})
        path = args.output / f"{name}-{strategy}.json"
        dump(path, bundle)
        summary["recipes"].append({"parser": name, "chunking": strategy, "bundle": str(path), "search_chunks": len(bundle["search_chunks"]),
            "chars": sum(len(c["text"]) for c in bundle["search_chunks"]), "max_chars": max(len(c["text"]) for c in bundle["search_chunks"]),
            "parse_seconds": sum(a.get("elapsed_seconds", 0) for r in rows if r["parser"] == name for a in r["attempts"]),
            "failed_attempts": sum(a["status"] != "completed" for r in rows if r["parser"] == name for a in r["attempts"]), "structure": structural})
    dump(args.output / "parse-report.json", summary)


def embed_stage(args):
    import numpy as np
    from app.core.config import get_settings
    from app.core.embeddings import GeminiEmbeddings
    settings = get_settings()
    if settings.embedding_dimension != 3072:
        raise ValueError("This stage fixes 3072 dimensions")
    embeddings = GeminiEmbeddings()
    for name, strategy in eligible_recipes(args.output):
        path = args.output / f"{name}-{strategy}.json"
        bundle = json.loads(path.read_text(encoding="utf8"))
        vectors = args.output / f"{name}-{strategy}.npy"
        fingerprint = {"bundle": sha(path), "model": settings.embedding_model, "dimension": 3072, "embedding_code": sha(ROOT / "app/core/embeddings.py")}
        marker = vectors.with_suffix(".identity.json")
        if vectors.exists() and marker.exists() and json.loads(marker.read_text(encoding="utf8")) == fingerprint:
            continue
        chunks = bundle["search_chunks"]
        rows = []
        started = time.perf_counter()
        for start in range(0, len(chunks), 32):
            rows.extend(embeddings.embed_documents([c["text"] for c in chunks[start:start + 32]]))
            print(f"embed {name}-{strategy} {min(start + 32, len(chunks))}/{len(chunks)}", flush=True)
        np.save(vectors, np.asarray(rows, dtype=np.float32))
        dump(marker, fingerprint)
        dump(vectors.with_suffix(".stats.json"), {"seconds": time.perf_counter() - started, "vectors": len(rows), "bytes": vectors.stat().st_size,
             "cache_reused": "per-content shared cache; call count not inferred from rows"})


def evaluate_stage(args):
    import numpy as np
    from rank_bm25 import BM25Okapi
    from app.core.embeddings import GeminiEmbeddings
    from app.core.config import get_settings
    from app.rag.retriever import kiwi_tokenize
    cases = json.loads(args.dataset.read_text(encoding="utf8"))
    validate_gold(cases)
    translations = json.loads(args.translations.read_text(encoding="utf8"))["frozen_translations"]
    queries = sorted({q for c in cases for q in (c["question"], translations[c["question"]])})
    embedding = GeminiEmbeddings()
    settings = get_settings()
    validate_embedding_identity({"model": settings.embedding_model, "dimension": settings.embedding_dimension}, settings.embedding_model, settings.embedding_dimension)
    # Query cache uses the exact query instruction, not document embeddings.
    query_path = args.output / "queries.json"
    identity = {"queries": queries, "dataset": sha(args.dataset), "embedding_code": sha(ROOT / "app/core/embeddings.py"), "dimension": 3072, "model": settings.embedding_model}
    if query_path.exists():
        saved = json.loads(query_path.read_text(encoding="utf8"))
        if saved["identity"] != identity:
            raise ValueError("Query cache identity differs")
        vectors = saved["vectors"]
    else:
        vectors = {}
    for q in queries:
        if q not in vectors:
            vectors[q] = embedding.embed_query(q)
            dump(query_path, {"identity": identity, "vectors": vectors})
    report = {"dataset_sha256": sha(args.dataset), "embedding_model": settings.embedding_model, "dimension": 3072, "candidate_k": 20,
              "return_k": 4, "context_chars": 6000, "index": "local exact cosine; no Pinecone network latency", "recipes": []}
    for name, strategy in eligible_recipes(args.output):
        bundle_path = args.output / f"{name}-{strategy}.json"
        bundle = json.loads(bundle_path.read_text(encoding="utf8"))
        chunks = bundle["search_chunks"]
        matrix = np.load(bundle_path.with_suffix(".npy"))
        marker = json.loads(bundle_path.with_suffix(".identity.json").read_text(encoding="utf8"))
        validate_embedding_identity(marker, settings.embedding_model, settings.embedding_dimension)
        if marker["bundle"] != sha(bundle_path) or marker["embedding_code"] != identity["embedding_code"] or matrix.shape != (len(chunks), 3072):
            raise ValueError("Vector provenance/shape mismatch")
        bm25 = BM25Okapi([kiwi_tokenize(c["text"]) for c in chunks])
        def candidates(q, hybrid):
            dense = np.argsort(-(matrix @ np.asarray(vectors[q], dtype=np.float32)), kind="stable")[:20].tolist()
            if not hybrid:
                return dense
            sparse_scores = bm25.get_scores(kiwi_tokenize(q))
            sparse = [int(i) for i in np.argsort(-sparse_scores, kind="stable")[:20] if sparse_scores[i] > 0]
            scores = {}
            for order in (dense, sparse):
                for rank, i in enumerate(order, 1):
                    scores[i] = scores.get(i, 0) + 1 / (60 + rank)
            return sorted(scores, key=lambda i: -scores[i])[:20]
        samples = []
        for mode in ("dense", "hybrid"):
            for case in cases:
                started = time.perf_counter()
                original, translated = case["question"], translations[case["question"]]
                order = candidates(translated, mode == "hybrid")
                if original != translated:
                    scores = {}
                    for ids in (order, candidates(original, mode == "hybrid")):
                        for rank, i in enumerate(ids, 1):
                            scores[i] = scores.get(i, 0) + 1 / (60 + rank)
                    order = sorted(scores, key=lambda i: -scores[i])[:20]
                context, delivered = pack_context(expand_context(bundle, [chunks[i]["id"] for i in order[:4]]), 6000)
                samples.append({**case, "mode": mode, **evidence_metrics(delivered, case), "actual_prompt_context": context,
                    "retrieved_contexts": [c["text"] for c in delivered], "context_metadata": [c["metadata"] for c in delivered],
                    "context_chars": len(context), "truncated": sum(c["context_truncated"] for c in delivered), "seconds": time.perf_counter() - started})
        contexts = args.output / f"{name}-{strategy}-contexts.json"
        dump(contexts, samples)
        for mode in ("dense", "hybrid"):
            selected = [s for s in samples if s["mode"] == mode]
            summary = {"recipe": f"{name}-{strategy}", "mode": mode, "n": len(selected), "bundle_sha256": sha(bundle_path), "samples": str(contexts),
                       **{m: sum(s[m] for s in selected) / len(selected) for m in ("page_hit", "excerpt_hit", "mrr", "context_chars", "seconds", "truncated")}}
            report["recipes"].append(summary)
            print(json.dumps(summary, ensure_ascii=False), flush=True)
    dump(args.output / "retrieval-report.json", report)


def eligible_recipes(output, include_controls=True):
    report = json.loads((output / "parse-report.json").read_text(encoding="utf8"))
    return [(row["parser"], row["chunking"]) for row in report["recipes"] if row.get("status", "completed") == "completed" and (include_controls or not row.get("control"))]


def validate_baseline_documents(documents, sources, model, dimension):
    seen = set()
    for doc in documents:
        meta = doc.metadata
        source = meta.get("source_file")
        if (source not in sources or meta.get("document_sha256") != sources[source]
            or meta.get("embedding_model") != model or meta.get("embedding_dimension") != dimension
            or not isinstance(meta.get("pdf_page"), int) or meta["pdf_page"] < 1):
            raise ValueError("Baseline corpus/model/page mismatch")
        seen.add(source)
    if seen != set(sources):
        raise ValueError("Baseline does not cover selected corpus")


def export_baseline_stage(args):
    import pickle
    import numpy as np
    from app.core.config import get_settings
    settings = get_settings()
    validate_embedding_identity({"model": settings.embedding_model, "dimension": settings.embedding_dimension}, settings.embedding_model, settings.embedding_dimension)
    source_path = Path(settings.get_chunks_path())
    documents = pickle.loads(source_path.read_bytes())  # trusted local build artifact only
    identity = json.loads((args.output / "parse-identity.json").read_text(encoding="utf8"))
    validate_baseline_documents(documents, identity["sources"], settings.embedding_model, 3072)
    bundle, vectors = {"search_chunks": [], "parents": {}}, []
    for i, doc in enumerate(documents):
        formatted = "title: none | text: " + doc.page_content
        key = hashlib.sha256(f"{settings.embedding_model}:3072:{formatted}".encode()).hexdigest()
        path = ROOT / "artifacts/embedding-cache" / (key + ".json")
        values = json.loads(path.read_text(encoding="utf8"))
        if len(values) != 3072 or not all(math.isfinite(v) for v in values) or abs(sum(v * v for v in values) - 1) > 0.001:
            raise ValueError("Invalid cached baseline vector")
        meta = {k: v for k, v in doc.metadata.items() if k != "text"}
        meta["pdf_pages"] = [meta["pdf_page"]]
        bundle["search_chunks"].append({"id": hashlib.sha256((str(i) + doc.page_content).encode()).hexdigest(), "text": doc.page_content, "metadata": meta})
        vectors.append(values)
    destination = args.output / "pypdf-recursive.json"
    dump(destination, bundle)
    np.save(destination.with_suffix(".npy"), np.asarray(vectors, dtype=np.float32))
    dump(destination.with_suffix(".identity.json"), {"bundle": sha(destination), "model": settings.embedding_model, "dimension": 3072,
          "embedding_code": sha(ROOT / "app/core/embeddings.py")})
    dump(destination.with_suffix(".stats.json"), {"vectors": len(vectors), "bytes": destination.with_suffix(".npy").stat().st_size,
          "api_calls": 0, "source_build_sha256": sha(source_path)})
    report_path = args.output / "parse-report.json"
    report = json.loads(report_path.read_text(encoding="utf8"))
    if not any(r["parser"] == "pypdf" for r in report["recipes"]):
        report["recipes"].append({"parser": "pypdf", "chunking": "recursive", "status": "completed", "control": True, "search_chunks": len(vectors),
             "bundle": str(destination), "note": "Existing active build replayed from same-model cache; no new parser candidate or API embedding"})
    dump(report_path, report)
    print(f"Exported baseline {len(vectors)} cached vectors, 0 API calls", flush=True)


def assemble_fallback_stage(args):
    """Explicit feasible fallback after Docling execution failure; no partial full scores."""
    from pypdf import PdfReader
    entries = json.loads(args.manifest.read_text(encoding="utf8"))
    identity = json.loads((args.output / "parse-identity.json").read_text(encoding="utf8"))
    if identity["manifest"] != sha(args.manifest):
        raise ValueError("Corpus manifest changed")
    batches = [json.loads(p.read_text(encoding="utf8")) for p in (args.output / "batches").rglob("*.json")]
    docling = [r for r in batches if r["parser"] == "docling"]
    report = {"scope": "full corpus feasible fallback; Docling rejected after repeated internal timeouts/thread failures",
              "documents": len(entries), "pages": 0, "recipes": [],
              "excluded": [{"parser": "docling", "chunking": "page", "status": "incomplete_rejected",
                            "completed_requested_pages": sum(len(r["pages"]) for r in docling if r["status"] == "completed"),
                            "failed_recorded_batches": sum(r["status"] != "completed" for r in docling),
                            "note": "Pending interrupted batches absent from checkpoint count; consult preserved worker logs for timeout/thread failures"}]}
    bundles = {strategy: {"search_chunks": [], "parents": {}} for strategy in ("page", "section")}
    structure = []
    for entry in entries:
        digest = sha(args.manifest.parent / entry["path"])
        if digest != identity["sources"][entry["path"]]:
            raise ValueError("Corpus source changed")
        count = len(PdfReader(args.manifest.parent / entry["path"]).pages)
        report["pages"] += count
        rows = sorted([r for r in batches if r["parser"] == "pdfplumber" and r["source_file"] == entry["path"]], key=lambda r: r["pages"][0])
        validate_batches(rows, count)
        blocks = []
        for row in rows:
            actual_pages = []
            for part in row["parts"]:
                artifact = Path(part["artifact"])
                manifest = json.loads((artifact / "manifest.json").read_text(encoding="utf8"))
                validate_parse_manifest(manifest, digest, manifest["selected_pages"], "pdfplumber", identity["runtime_versions"]["pdfplumber"])
                actual_pages.extend(manifest["selected_pages"])
                subset = json.loads((artifact / "blocks.json").read_text(encoding="utf8"))["blocks"]
                if {b["pdf_page"] for b in subset} != set(manifest["selected_pages"]):
                    raise ValueError("PDFPlumber block page coverage differs")
                blocks.extend({**b, "id": f"batch-{row['pages'][0]}:{b['id']}"} for b in subset)
            if sorted(actual_pages) != row["pages"]:
                raise ValueError("Part page coverage differs")
        dump(args.output / "blocks/pdfplumber" / (entry["path"] + ".json"), {"blocks": blocks})
        structure.append({"source": entry["path"], "pages": count, "text_pages": len({b["pdf_page"] for b in blocks if b["text"].strip()}),
                          "tables": sum(b["kind"] == "table" for b in blocks), "images": sum(b["kind"] == "image" for b in blocks)})
        for strategy, bundle in bundles.items():
            result = chunk_blocks(blocks, {**entry, "source_file": entry["path"], "sha256": digest, "parser": "pdfplumber"}, ChunkConfig(strategy=strategy))
            bundle["search_chunks"].extend(result["search_chunks"])
            bundle["parents"].update(result["parents"])
    for strategy, bundle in bundles.items():
        destination = args.output / f"pdfplumber-{strategy}.json"
        dump(destination, bundle)
        report["recipes"].append({"parser": "pdfplumber", "chunking": strategy, "status": "completed", "bundle": str(destination),
            "search_chunks": len(bundle["search_chunks"]), "max_chars": max(len(c["text"]) for c in bundle["search_chunks"]),
            "chars": sum(len(c["text"]) for c in bundle["search_chunks"]), "structure": structure,
            "parse_seconds": sum(a["elapsed_seconds"] for r in batches if r["parser"] == "pdfplumber" for a in r["attempts"])})
    dump(args.output / "parse-report.json", report)
    print(json.dumps({"documents": report["documents"], "pages": report["pages"], "recipes": [{k: r[k] for k in ("parser", "chunking", "search_chunks", "max_chars")} for r in report["recipes"]]}), flush=True)


def parse_fallback_stage(args):
    """Reproducible PDFPlumber-only full run after explicit rejected Docling trial."""
    from pypdf import PdfReader
    runtime = ROOT / "artifacts/parser-runtime"
    sys.path.insert(0, str(runtime))
    parser_version = version("pdfplumber")
    sys.path.remove(str(runtime))
    entries = json.loads(args.manifest.read_text(encoding="utf8"))
    identity = {"manifest": sha(args.manifest), "sources": {e["path"]: sha(args.manifest.parent / e["path"]) for e in entries},
                "runtime_versions": {"pdfplumber": parser_version}, "ingestion_code": sha(ROOT / "app/rag/ingestion.py"),
                "batch_pages": args.batch_pages, "recipes": [["pdfplumber", "page"], ["pdfplumber", "section"]]}
    marker = args.output / "parse-identity.json"
    if marker.exists() and json.loads(marker.read_text(encoding="utf8")) != identity:
        raise ValueError("Fallback parse settings/code changed; use a fresh directory")
    dump(marker, identity)
    def one(entry):
        count = len(PdfReader(args.manifest.parent / entry["path"]).pages)
        job = args.output / "persistent-jobs" / (entry["path"] + ".json")
        dump(job, {"source": {**entry, "path": str((args.manifest.parent / entry["path"]).resolve())}, "parser": "pdfplumber",
                   "source_sha": identity["sources"][entry["path"]], "parser_version": parser_version, "output": str(args.output),
                   "batches": [list(range(p, min(p + args.batch_pages, count + 1))) for p in range(1, count + 1, args.batch_pages)]})
        env = {**os.environ, "PYTHONPATH": str(runtime) + os.pathsep + str(ROOT), "PYTHONIOENCODING": "utf-8"}
        with job.with_suffix(".log").open("w", encoding="utf8") as log:
            result = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--worker-job", str(job)], env=env, stdout=log, stderr=log, timeout=1800)
        if result.returncode:
            raise RuntimeError("PDFPlumber worker failed")
        print(f"fallback parse {entry['path']} completed", flush=True)
    with ThreadPoolExecutor(max_workers=min(args.workers, 2)) as pool:
        for future in as_completed([pool.submit(one, e) for e in entries]):
            future.result()
    assemble_fallback_stage(args)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=["parse", "parse-fallback", "assemble-fallback", "export-baseline", "embed", "evaluate"])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--worker-job", type=Path)
    parser.add_argument("--persistent", action="store_true", help="Reuse Docling weights sequentially inside isolated per-document workers")
    parser.add_argument("--manifest", type=Path, default=ROOT.parent / "docs/nutrition/corpus_manifest.json")
    parser.add_argument("--dataset", type=Path, default=ROOT.parent / "docs/rag_experiments/gold_core40_v2.json")
    parser.add_argument("--translations", type=Path, default=ROOT / "artifacts/retrieval-core40-strict-v2/report.json")
    parser.add_argument("--batch-pages", type=int, default=24)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--workers", type=int, choices=[1, 2, 4], default=4)
    args = parser.parse_args()
    if args.worker_job:
        persistent_worker(json.loads(args.worker_job.read_text(encoding="utf8")))
        return
    if not args.stage or not args.output:
        parser.error("stage and output are required")
    if args.batch_pages < 1 or args.timeout < 1:
        parser.error("batch-pages and timeout must be positive")
    args.output.mkdir(parents=True, exist_ok=True)
    {"parse": parse_stage, "parse-fallback": parse_fallback_stage, "assemble-fallback": assemble_fallback_stage, "export-baseline": export_baseline_stage, "embed": embed_stage, "evaluate": evaluate_stage}[args.stage](args)


if __name__ == "__main__":
    main()
