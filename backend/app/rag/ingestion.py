"""Local parser experiments with traceable artifacts, independent of live indexes."""
import hashlib
import json
import time
import math
import re
import unicodedata
from dataclasses import asdict, dataclass
from importlib.metadata import version
from pathlib import Path
from uuid import uuid4
from functools import lru_cache
from collections import Counter


@dataclass(frozen=True)
class SourceDocument:
    path: Path
    title: str
    source_url: str
    language: str
    edition: str
    population: str
    usage_notes: str


@dataclass(frozen=True)
class DoclingConfig:
    timeout_seconds: float = 120
    num_threads: int = 4
    parser_threads: int | None = None
    device: str = "auto"
    table_structure: bool = True
    table_mode: str = "accurate"
    batch_size: int = 4
    queue_size: int = 100
    picture_images: bool = True

    def __post_init__(self):
        if not math.isfinite(self.timeout_seconds) or not 1 <= self.timeout_seconds <= 1800:
            raise ValueError("Docling timeout must be finite and within 1..1800 seconds")
        if any(isinstance(v, bool) or not isinstance(v, int) or v < 1 for v in (self.num_threads, self.batch_size, self.queue_size)):
            raise ValueError("Docling thread, batch and queue sizes must be positive integers")
        if self.parser_threads is not None and (isinstance(self.parser_threads, bool) or not isinstance(self.parser_threads, int) or self.parser_threads < 1):
            raise ValueError("Native parser threads must be a positive integer")
        if self.table_mode not in {"accurate", "fast"} or self.device not in {"auto", "cpu", "cuda"}:
            raise ValueError("Unknown Docling table mode or device")


def validate_docling_conversion(result, pages: list[int]) -> None:
    status = getattr(result.status, "value", result.status)
    if status != "success":
        raise ValueError(f"Docling conversion incomplete: {status}")
    if set(result.document.pages) != set(pages):
        raise ValueError("Docling converted page coverage differs from requested range")


@lru_cache(maxsize=2)
def _docling_converter(ocr: bool, backend_name: str, config: DoclingConfig):
    """Reuse model weights for sequential batches in the same isolated worker."""
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions, TesseractCliOcrOptions, TableFormerMode
    from docling.datamodel.accelerator_options import AcceleratorOptions
    from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
    from docling.backend.docling_parse_backend import DoclingParseDocumentBackend
    options = PdfPipelineOptions(do_ocr=ocr, do_table_structure=config.table_structure, document_timeout=config.timeout_seconds,
        accelerator_options=AcceleratorOptions(num_threads=config.num_threads, device=config.device),
        layout_batch_size=config.batch_size, table_batch_size=config.batch_size, ocr_batch_size=config.batch_size,
        queue_max_size=config.queue_size)
    options.table_structure_options.mode = TableFormerMode(config.table_mode)
    options.generate_picture_images = config.picture_images
    if ocr:
        options.ocr_options = TesseractCliOcrOptions(lang=["kor", "eng"])
    backend = PyPdfiumDocumentBackend if backend_name == "pdfium" else DoclingParseDocumentBackend
    kwargs = {}
    if backend_name == "docling_parse" and config.parser_threads is not None:
        from docling.datamodel.backend_options import ThreadedDoclingParseBackendOptions
        kwargs["backend_options"] = ThreadedDoclingParseBackendOptions(parser_threads=config.parser_threads)
    return DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options, backend=backend, **kwargs)})


def repair_pdfplumber_cells(page, table):
    """Read missing edge cells using header columns and the shortest row geometry.

    Never invent values or forward-fill merged cells. Recovery provenance is kept
    for review; presence of text is not a clinical or table-accuracy approval.
    """
    cells, recovered = table.extract(), []
    if not cells or not table.rows:
        return cells, recovered
    headers = table.rows[0].cells
    for row_index, row in enumerate(cells):
        boxes = [b for b in table.rows[row_index].cells if b is not None]
        if not boxes:
            continue
        row_box = min(boxes, key=lambda b: b[3] - b[1])
        for col, cell in enumerate(row):
            if cell is not None or col >= len(headers) or headers[col] is None:
                continue
            header = headers[col]
            box = visible_box(page, (header[0], row_box[1], header[2], row_box[3]))
            if box is None:
                continue
            text = page.crop(box).extract_text() or ""
            if text.strip():
                row[col] = text
                recovered.append({"row": row_index, "column": col, "bbox": list(box), "text": text,
                                  "method": "header-column-shortest-row-geometry", "review_status": "unreviewed"})
    return cells, recovered


def visible_box(page, box):
    bounds = getattr(page, "bbox", None)
    if bounds is None:
        return box
    clipped = (max(bounds[0], box[0]), max(bounds[1], box[1]), min(bounds[2], box[2]), min(bounds[3], box[3]))
    return clipped if clipped[0] < clipped[2] and clipped[1] < clipped[3] else None


def table_text_preserved(source_text: str, cell_text: str) -> bool:
    normalized = lambda value: re.sub(r"\s+", "", unicodedata.normalize("NFKC", value).replace("−", "-").replace("–", "-"))
    target = normalized(cell_text)
    source_text = unicodedata.normalize("NFKC", source_text).replace("−", "-").replace("–", "-")
    cell_text = unicodedata.normalize("NFKC", cell_text).replace("−", "-").replace("–", "-")
    numeric = lambda value: Counter(normalized(token) for token in re.findall(r"[+\-]?\s*\d+(?:[.,]\d+)*", value))
    if numeric(source_text) - numeric(cell_text):
        return False
    for word in re.findall(r"[가-힣A-Za-z]+", source_text):
        if normalized(word) not in target:
            return False
    return True


def parse_document(source: SourceDocument, output: Path, *, parser: str = "pypdf",
                   pages: list[int] | None = None, ocr: bool = False, docling_backend: str = "docling_parse",
                   docling_config: DoclingConfig | None = None) -> Path:
    """Write canonical JSON plus a human-readable review copy, never upsert vectors.

    PyPDF is the text baseline. Docling keeps its full structural document model
    (table cells, provenance, pictures); Markdown is an inspection artifact only.
    Generated captions are deliberately absent until reviewed as derived content.
    """
    if parser not in {"pypdf", "docling", "pdfplumber"}:
        raise ValueError("parser must be pypdf, docling or pdfplumber")
    if docling_backend not in {"docling_parse", "pdfium"}:
        raise ValueError("Unknown Docling backend")
    if ocr and parser != "docling":
        raise ValueError("OCR is supported only by the Docling recipe")
    config = docling_config or DoclingConfig()
    from pypdf import PdfReader
    labels = PdfReader(source.path).page_labels
    selected = sorted(set(pages)) if pages is not None else list(range(1, len(labels) + 1))
    if not selected or any(p < 1 or p > len(labels) for p in selected):
        raise ValueError("Selected PDF pages are out of range")
    digest = hashlib.sha256(source.path.read_bytes()).hexdigest()
    parser_version = version(parser)
    effective_config = {"pages": selected, "ocr": ocr, "artifact_schema": 2,
        "parser_version": parser_version, "table_structure": config.table_structure if parser == "docling" else False,
        "picture_images": config.picture_images if parser == "docling" else False,
        "docling_backend": docling_backend if parser == "docling" else None,
        "document_timeout_seconds": config.timeout_seconds if parser == "docling" else None,
        "docling_config": asdict(config) if parser == "docling" else None,
        "ocr_engine": "tesseract_cli" if ocr else None, "ocr_languages": ["kor", "eng"] if ocr else [],
        "pdfplumber_table_settings": {} if parser == "pdfplumber" else None,
        "pdfplumber_text_policy": "recover-geometry-then-token-check-retain-source-if-incomplete-v1" if parser == "pdfplumber" else None}
    settings_id = hashlib.sha256(json.dumps(effective_config, sort_keys=True).encode()).hexdigest()[:12]
    run_id = uuid4().hex
    destination = output / digest / parser / settings_id / run_id
    destination.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    if parser == "pypdf":
        from pypdf import PdfReader
        document = PdfReader(source.path)
        blocks = [{"id": f"page-{i + 1}", "kind": "text", "pdf_page": i + 1,
                   "pdf_page_label": document.page_labels[i], "printed_page": None,
                   "text": page.extract_text() or "", "derived": False}
                  for i, page in enumerate(document.pages) if i + 1 in selected]
        canonical = {"blocks": blocks}
        markdown = "\n\n".join(f"<!-- PDF page {b['pdf_page']} -->\n{b['text']}" for b in blocks)
    elif parser == "pdfplumber":
        import pdfplumber
        blocks = []
        with pdfplumber.open(source.path) as document:
            for number in selected:
                page = document.pages[number - 1]
                tables = page.find_tables()
                extracted = []
                for table in tables:
                    cells, recovered = repair_pdfplumber_cells(page, table)
                    text = "\n".join(" | ".join(cell or "" for cell in row) for row in cells)
                    visible = visible_box(page, table.bbox)
                    source_text = (page.crop(visible).extract_text() or "") if visible else ""
                    preserved = visible == table.bbox and table_text_preserved(source_text, text)
                    extracted.append((table, cells, recovered, text, preserved, source_text))
                # Remove source text only for tables whose source tokens survived.
                # Unsafe structural tables remain review artifacts; native text stays searchable.
                boxes = [table.bbox for table, _, _, _, preserved, _ in extracted if preserved]
                text_page = page.filter(lambda obj: not any(
                    obj.get("x0", -1) >= box[0] and obj.get("x1", -1) <= box[2]
                    and obj.get("top", -1) >= box[1] and obj.get("bottom", -1) <= box[3] for box in boxes))
                blocks.append({"id": f"page-{number}", "kind": "text", "pdf_page": number,
                               "pdf_page_label": labels[number - 1], "printed_page": None,
                               "text": text_page.extract_text() or "", "derived": False})
                for index, (table, cells, recovered, text, preserved, source_text) in enumerate(extracted):
                    blocks.append({"id": f"page-{number}-table-{index}", "kind": "table", "pdf_page": number,
                        "bbox": list(table.bbox), "cells": cells, "text": text, "derived": not preserved,
                        "recovered_cells": recovered, "source_text_preserved": preserved, "native_table_text": source_text,
                        "quality_review_status": "unreviewed"})
                for index, picture in enumerate(page.images):
                    blocks.append({"id": f"page-{number}-image-{index}", "kind": "image", "pdf_page": number,
                        "bbox": [picture["x0"], picture["top"], picture["x1"], picture["bottom"]],
                        "text": "", "derived": False})
        canonical = {"blocks": blocks}
        markdown = "\n\n".join(f"<!-- PDF page {b['pdf_page']} ({b['kind']}) -->\n{b['text']}" for b in blocks)
    else:
        converter = _docling_converter(ocr, docling_backend, config)
        # Full JSON retains table cells and item provenance; no lossy Markdown reparse.
        # Convert contiguous ranges rather than silently processing unselected pages.
        runs = []
        for number in selected:
            if runs and number == runs[-1][-1] + 1:
                runs[-1].append(number)
            else:
                runs.append([number])
        documents = []
        for run in runs:
            result = converter.convert(source.path, page_range=(run[0], run[-1]))
            validate_docling_conversion(result, run)
            documents.append(result.document)
        blocks = []
        markdown_parts = []
        canonical_documents = []
        for run_index, document in enumerate(documents):
            canonical_documents.append(document.export_to_dict())
            markdown_parts.append(document.export_to_markdown())
            for item, level in document.iterate_items():
                if not item.prov:
                    continue
                number = item.prov[0].page_no
                if number not in selected:
                    continue
                label = str(item.label.value)
                kind = "table" if label == "table" else "image" if label == "picture" else "heading" if label in {"section_header", "title"} else "text"
                text = item.export_to_markdown(doc=document) if kind == "table" else getattr(item, "text", "")
                block = {"id": f"run-{run_index}:{item.self_ref}", "kind": kind, "pdf_page": number,
                    "pdf_page_label": labels[number - 1], "printed_page": None, "text": text, "derived": False,
                    "provenance": [prov.model_dump(mode="json") for prov in item.prov]}
                if kind == "table":
                    block["data"] = item.data.model_dump(mode="json")
                    (destination / f"table-{len(blocks)}.html").write_text(item.export_to_html(doc=document), encoding="utf-8")
                if kind == "image":
                    picture = item.get_image(document)
                    if picture is not None:
                        filename = f"picture-{len(blocks)}.png"
                        picture.save(destination / filename)
                        block["image_path"] = filename
                blocks.append(block)
        canonical = {"documents": canonical_documents}
        markdown = "\n\n".join(markdown_parts)
    metadata = {**asdict(source), "path": source.path.name, "sha256": digest,
                "ingestion_code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "parser": parser, "parser_version": parser_version, "run_id": run_id, "effective_config": effective_config,
                "selected_pages": selected, "ocr": ocr, "artifact_schema": 2,
                "elapsed_seconds": time.perf_counter() - started,
                "quality_review_status": "unreviewed"}
    (destination / "document.json").write_text(json.dumps(canonical, ensure_ascii=False, indent=2), encoding="utf-8")
    (destination / "blocks.json").write_text(json.dumps({"blocks": blocks}, ensure_ascii=False, indent=2), encoding="utf-8")
    (destination / "review.md").write_text(markdown, encoding="utf-8")
    (destination / "manifest.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return destination
