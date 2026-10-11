import pytest
from scripts import build_rag


def test_numeric_and_short_table_content_is_not_discarded():
    assert not build_rag._is_junk("나트륨 mg\n성인 1500 2300\n칼슘 mg 800 1000")
    assert build_rag._is_junk("  ")


def test_clear_requires_explicit_namespace(monkeypatch):
    monkeypatch.setattr(build_rag.settings, "pinecone_namespace", "")
    with pytest.raises(ValueError, match="PINECONE_NAMESPACE"):
        build_rag._clear_index()


def test_changed_or_removed_document_gets_new_build_identity():
    from langchain_core.documents import Document
    first = Document(page_content="first", metadata={"source_file": "a.pdf"})
    second = Document(page_content="second", metadata={"source_file": "b.pdf"})
    original = build_rag._build_identity([first, second])
    assert original == build_rag._build_identity([first, second])
    assert original != build_rag._build_identity([first])
    assert original != build_rag._build_identity([first, Document(page_content="changed", metadata=second.metadata)])


def test_manifest_selects_only_explicit_editions_and_language(tmp_path):
    import json
    (tmp_path / "old.pdf").write_bytes(b"old")
    (tmp_path / "KDRI_2025.pdf").write_bytes(b"new")
    (tmp_path / "corpus_manifest.json").write_text(json.dumps([
        {"path": "KDRI_2025.pdf", "language": "ko", "edition": "2025", "title": "new"}]), encoding="utf-8")
    selected = build_rag._select_sources(tmp_path)
    assert list(selected) == [tmp_path / "KDRI_2025.pdf"]
    assert selected[tmp_path / "KDRI_2025.pdf"]["language"] == "ko"
