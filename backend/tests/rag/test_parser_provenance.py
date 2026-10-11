import json
import pytest
from pypdf import PdfWriter
from app.rag.ingestion import SourceDocument, parse_document


def test_docling_diagnostic_config_rejects_unbounded_or_invalid_settings():
    from app.rag.ingestion import DoclingConfig
    for changes in ({"timeout_seconds": 0}, {"timeout_seconds": float("inf")},
                    {"num_threads": 0}, {"batch_size": 0}, {"table_mode": "unknown"}, {"device": "unknown"}):
        with pytest.raises(ValueError):
            DoclingConfig(**changes)


def test_docling_experiment_config_is_immutable_cache_identity():
    from app.rag.ingestion import DoclingConfig
    from dataclasses import FrozenInstanceError
    baseline = DoclingConfig()
    reduced = DoclingConfig(timeout_seconds=300, num_threads=1, batch_size=1)
    assert len({baseline, reduced, DoclingConfig(table_structure=False)}) == 3
    with pytest.raises(FrozenInstanceError):
        reduced.num_threads = 4


def test_native_parser_threads_are_separate_from_model_threads():
    from app.rag.ingestion import DoclingConfig
    config = DoclingConfig(num_threads=4, parser_threads=1)
    assert config.num_threads == 4 and config.parser_threads == 1
    assert config != DoclingConfig(num_threads=4)
    with pytest.raises(ValueError):
        DoclingConfig(parser_threads=0)


def test_docling_changed_settings_reach_converter_and_artifact_identity(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from app.rag import ingestion
    path = tmp_path / "fixture.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.write(path)
    source = SourceDocument(path, "fixture", "https://example.org", "ko", "test", "test", "test")
    captured = []
    document = SimpleNamespace(pages={1: None}, export_to_dict=lambda: {"pages": {"1": {}}},
                               export_to_markdown=lambda: "", iterate_items=lambda: [])
    def fake_converter(ocr, backend, config):
        captured.append(config)
        return SimpleNamespace(convert=lambda *a, **k: SimpleNamespace(status="success", document=document))
    monkeypatch.setattr(ingestion, "_docling_converter", fake_converter)
    monkeypatch.setattr(ingestion, "version", lambda name: "test")
    first = parse_document(source, tmp_path / "out", parser="docling")
    config = ingestion.DoclingConfig(timeout_seconds=300, num_threads=1, batch_size=1, table_structure=False)
    second = parse_document(source, tmp_path / "out", parser="docling", docling_config=config)
    assert first.parent != second.parent
    manifest = json.loads((second / "manifest.json").read_text(encoding="utf8"))
    assert captured[-1] == config
    assert manifest["effective_config"]["document_timeout_seconds"] == 300
    assert manifest["effective_config"]["table_structure"] is False
    assert manifest["effective_config"]["docling_config"]["num_threads"] == 1


def test_pypdf_artifact_has_source_hash_page_and_review_status(tmp_path):
    path = tmp_path / "fixture.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.write(path)
    source = SourceDocument(path, "Synthetic fixture", "https://example.org/fixture",
                            "ko", "test", "test", "synthetic")
    result = parse_document(source, tmp_path / "output")
    metadata = json.loads((result / "manifest.json").read_text(encoding="utf-8"))
    document = json.loads((result / "document.json").read_text(encoding="utf-8"))
    assert len(metadata["sha256"]) == 64
    assert metadata["quality_review_status"] == "unreviewed"
    assert metadata["source_url"] == source.source_url
    assert document["blocks"][0]["pdf_page"] == 1
    assert document["blocks"][0]["printed_page"] is None
    assert document["blocks"][0]["derived"] is False


def test_parser_reruns_do_not_overwrite_existing_artifacts(tmp_path):
    path = tmp_path / "fixture.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.write(path)
    source = SourceDocument(path, "fixture", "https://example.org", "ko", "test", "test", "test")
    first = parse_document(source, tmp_path / "output")
    second = parse_document(source, tmp_path / "output")
    assert first != second
    assert (first / "document.json").exists()
    assert json.loads((second / "manifest.json").read_text(encoding="utf-8"))["effective_config"]["artifact_schema"] == 2


def test_unknown_docling_backend_is_rejected_before_conversion(tmp_path):
    import pytest
    source = SourceDocument(tmp_path / "unused.pdf", "fixture", "https://example.org", "ko", "test", "test", "test")
    with pytest.raises(ValueError, match="backend"):
        parse_document(source, tmp_path / "out", parser="docling", docling_backend="unknown")


def test_docling_partial_conversion_cannot_be_counted_as_complete():
    import pytest
    from types import SimpleNamespace
    from app.rag.ingestion import validate_docling_conversion
    with pytest.raises(ValueError, match="incomplete"):
        validate_docling_conversion(SimpleNamespace(status=SimpleNamespace(value="partial_success"), document=SimpleNamespace(pages={1: None})), [1, 2])
    with pytest.raises(ValueError, match="coverage"):
        validate_docling_conversion(SimpleNamespace(status=SimpleNamespace(value="success"), document=SimpleNamespace(pages={1: None})), [1, 2])


def test_pdfplumber_recovers_missing_cell_from_source_geometry():
    from types import SimpleNamespace
    from app.rag.ingestion import repair_pdfplumber_cells
    table = SimpleNamespace(extract=lambda: [["age", "value"], ["adult", None]],
        rows=[SimpleNamespace(cells=[(0, 0, 50, 10), (50, 0, 100, 10)]), SimpleNamespace(cells=[(0, 10, 50, 20), None])])
    observed = []
    def crop(box):
        observed.append(box)
        return SimpleNamespace(extract_text=lambda: "25 g")
    cells, recovered = repair_pdfplumber_cells(SimpleNamespace(crop=crop), table)
    assert cells[1][1] == "25 g"
    assert observed == [(50, 10, 100, 20)]
    assert recovered[0]["row"] == 1 and recovered[0]["column"] == 1


def test_table_source_removal_requires_numeric_sign_and_value_preservation():
    from app.rag.ingestion import table_text_preserved
    assert not table_text_preserved("adult -100 mg", "adult 100 mg")
    assert not table_text_preserved("adult 25 mg", "adult 250 mg")
    assert not table_text_preserved("adult 20 mg", "adult -20 mg")
    assert table_text_preserved("age 0-5 months +20 mg", "age 0-5 months | +20 mg")


def test_source_crop_is_clamped_to_visible_page():
    from types import SimpleNamespace
    from app.rag.ingestion import visible_box
    assert visible_box(SimpleNamespace(bbox=(0, 0, 100, 100)), (10, 80, 90, 110)) == (10, 80, 90, 100)
    assert visible_box(SimpleNamespace(bbox=(0, 0, 100, 100)), (10, 101, 90, 110)) is None
