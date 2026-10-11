import json
from pypdf import PdfWriter
from app.rag.ingestion import SourceDocument, parse_document


def test_pdfplumber_exports_page_aligned_common_blocks(tmp_path):
    import pytest
    pytest.importorskip("pdfplumber", reason="optional isolated ingestion runtime")
    path = tmp_path / "sample.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.add_blank_page(width=200, height=200)
    writer.write(path)
    source = SourceDocument(path, "fixture", "https://example.org", "ko", "test", "adult", "test")
    result = parse_document(source, tmp_path / "out", parser="pdfplumber", pages=[2])
    blocks = json.loads((result / "blocks.json").read_text(encoding="utf-8"))["blocks"]
    assert blocks[0]["pdf_page"] == 2
    manifest = json.loads((result / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["selected_pages"] == [2]
    assert manifest["ocr"] is False
