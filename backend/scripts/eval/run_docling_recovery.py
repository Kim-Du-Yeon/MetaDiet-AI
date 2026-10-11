"""Isolated, logged Docling recovery trials; no credentials or production writes."""
import argparse
import hashlib
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf8")
    temporary.replace(path)


def valid_cached_range(marker, job, pages):
    from scripts.eval.run_full_recipe_comparison import validate_cached_docling_pages
    try:
        saved = json.loads(marker.read_text(encoding="utf8"))
        if saved.get("identity") != job["identity"] or saved.get("status") != "completed":
            return False
        validate_recovery_artifact(saved, pages)
        return True
    except (OSError, ValueError, KeyError, TypeError):
        return False


def validate_recovery_artifact(row, pages):
    from scripts.eval.run_full_recipe_comparison import validate_cached_docling_pages
    artifact = Path(row["artifact"])
    manifest = json.loads((artifact / "manifest.json").read_text(encoding="utf8"))
    identity = row["identity"]
    config = manifest["effective_config"]
    if (manifest["sha256"] != identity["source_sha256"]
        or manifest["ingestion_code_sha256"] != identity["ingestion_code"]
        or manifest["parser"] != "docling"
        or manifest["parser_version"] != identity["runtime_versions"]["docling"]
        or manifest["selected_pages"] != sorted(pages)
        or config["docling_backend"] != identity["backend"]
        or any(config["docling_config"].get(k) != v for k, v in identity["config"].items())):
        raise ValueError("Recovery artifact source/code/parser/config/page mismatch")
    validate_cached_docling_pages(artifact, sorted(pages))


def worker(job):
    import faulthandler
    faulthandler.enable(all_threads=False)
    # CPython 3.13 asynchronous frame dumping can itself crash in dump_frame.
    # Do not walk concurrently executing foreign/model threads on a native fault.
    # Retain the current thread diagnostic and the parent process timeout.
    from app.rag.ingestion import SourceDocument, DoclingConfig, parse_document
    import torch
    from importlib.metadata import version
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("docling.pipeline.standard_pdf_pipeline").setLevel(logging.DEBUG)
    threads = job["config"]["num_threads"]
    torch.set_num_threads(threads)
    torch.set_num_interop_threads(1)
    print(json.dumps({"torch": torch.__version__, "cuda_available": torch.cuda.is_available(), "cpu_count": os.cpu_count(),
                      "docling": version("docling"), "torch_threads": torch.get_num_threads(), "config": job["config"]}), flush=True)
    source = SourceDocument(**{**job["source"], "path": Path(job["source"]["path"])})
    for pages in job["ranges"]:
        marker = Path(job["output"]) / "results" / f"{source.path.stem}-{pages[0]:04d}-{pages[-1]:04d}.json"
        if valid_cached_range(marker, job, pages):
            print(f"cached {pages}", flush=True)
            continue
        started = time.perf_counter()
        row = {"pages": pages, "source": source.path.name, "identity": job["identity"]}
        try:
            artifact = parse_document(source, Path(job["output"]) / "parses", parser="docling", pages=pages,
                docling_backend=job["backend"], docling_config=DoclingConfig(**job["config"]))
            row.update(status="completed", artifact=str(artifact))
        except Exception as exc:
            logging.exception("Docling trial failed source=%s pages=%s", source.path.name, pages)
            row.update(status="failed", error_type=type(exc).__name__, error=str(exc))
        row["seconds"] = time.perf_counter() - started
        dump(marker, row)
        print(json.dumps(row), flush=True)
        if row["status"] != "completed":
            # A timed-out model thread may still run; do not reuse this process.
            return 1
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", type=Path, required=True)
    ap.add_argument("--worker", action="store_true")
    args = ap.parse_args()
    job = json.loads(args.job.read_text(encoding="utf8"))
    if args.worker:
        return worker(job)
    output = Path(job["output"])
    output.mkdir(parents=True, exist_ok=True)
    # Preserve prior failures and timings when resuming the same output directory.
    import shutil
    import uuid
    previous = output / "history" / uuid.uuid4().hex
    for filename in ("worker.log", "execution.json", "job.json"):
        old = output / filename
        if old.exists():
            previous.mkdir(parents=True, exist_ok=True)
            shutil.copy2(old, previous / filename)
    runtime = ROOT / "artifacts/parser-runtime"
    paths = [str(runtime), str(ROOT)]
    if job.get("gpu_runtime"):
        paths.insert(0, str(ROOT / "artifacts/gpu-runtime"))
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(paths), "PYTHONIOENCODING": "utf-8",
           "HF_HUB_OFFLINE": "1", "HF_HOME": str(ROOT / "artifacts/model-cache"),
           "OMP_NUM_THREADS": str(job["config"]["num_threads"]),
           "MKL_NUM_THREADS": str(job["config"]["num_threads"]), "TOKENIZERS_PARALLELISM": "false"}
    job["identity"] = {"source_sha256": hashlib.sha256(Path(job["source"]["path"]).read_bytes()).hexdigest(),
                       "config": job["config"], "backend": job["backend"], "ranges": job["ranges"],
                       "gpu_runtime": bool(job.get("gpu_runtime")),
                       "ingestion_code": hashlib.sha256((ROOT / "app/rag/ingestion.py").read_bytes()).hexdigest()}
    from importlib.metadata import distributions
    versions = {}
    for path in paths:
        for distribution in distributions(path=[path]):
            name = distribution.metadata['Name'].lower().replace('_', '-')
            if name in {'torch', 'torchvision', 'docling', 'docling-core', 'docling-parse', 'docling-ibm-models', 'transformers', 'pypdfium2'}:
                versions.setdefault(name, distribution.version)
    job['identity']['runtime_versions'] = versions
    saved_job = output / "job.json"
    dump(saved_job, job)
    started = time.perf_counter()
    with (output / "worker.log").open("w", encoding="utf8") as log:
        try:
            result = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--job", str(saved_job), "--worker"],
                                    env=env, stdout=log, stderr=log, timeout=job.get("wall_timeout", 600))
            status, code = "completed" if result.returncode == 0 else "failed", result.returncode
        except subprocess.TimeoutExpired:
            status, code = "wall_timeout", None
    dump(output / "execution.json", {"status": status, "exit_code": code, "seconds": time.perf_counter() - started,
                                    "identity": job["identity"], "log": str(output / "worker.log")})
    print(json.dumps({"output": str(output), "status": status, "seconds": time.perf_counter() - started}), flush=True)
    return 0 if status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
