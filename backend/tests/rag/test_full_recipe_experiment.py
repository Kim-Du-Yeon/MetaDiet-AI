import pytest


def test_full_coverage_rejects_missing_and_duplicate_batch_pages():
    from scripts.eval.run_full_recipe_comparison import validate_batches
    validate_batches([{"pages": [1, 2], "status": "completed"}, {"pages": [3], "status": "completed"}], 3)
    with pytest.raises(ValueError):
        validate_batches([{"pages": [1, 2], "status": "completed"}], 3)
    with pytest.raises(ValueError):
        validate_batches([{"pages": [1, 2], "status": "completed"}, {"pages": [2, 3], "status": "completed"}], 3)


def test_context_budget_counts_headers_and_metrics_accept_equivalent_pages():
    from scripts.eval.run_full_recipe_comparison import pack_context, evidence_metrics
    items = [{"id": str(i), "text": "x" * 80, "metadata": {"source_file": "a.pdf", "pdf_pages": [i]}} for i in [1, 2]]
    text, delivered = pack_context(items, 110)
    assert len(text) <= 110
    assert len(delivered) == 1
    case = {"gold_source": "a.pdf", "gold_page": 24, "gold_excerpt": "25 g",
            "acceptable_evidence": [{"source": "a.pdf", "pdf_pages": [12, 24]}]}
    result = evidence_metrics([{ "text": "25 g per day", "metadata": {"source_file": "a.pdf", "pdf_pages": [12]}}], case)
    assert result["page_hit"] and result["excerpt_hit"]


def test_development_dataset_required():
    from scripts.eval.run_full_recipe_comparison import validate_gold
    with pytest.raises(ValueError):
        validate_gold([{"id": "x", "review_status": "reviewed", "split": "heldout"}])


def test_normalized_keyword_check_keeps_numbers_and_units():
    from scripts.eval.run_full_recipe_comparison import normalized
    assert normalized("25\ng") == normalized("25 g")
    assert normalized("25 g") != normalized("250 mg")


def test_mrr_uses_retrieved_item_rank_not_metadata_page_count():
    from scripts.eval.run_full_recipe_comparison import evidence_metrics
    item = {"text": "answer", "metadata": {"source_file": "a.pdf", "pdf_pages": list(range(1, 11))}}
    case = {"gold_source": "a.pdf", "gold_page": 10, "gold_excerpt": "answer"}
    assert evidence_metrics([item], case)["mrr"] == 1


def test_embedding_cache_requires_same_model_and_dimensions():
    from scripts.eval.run_full_recipe_comparison import validate_embedding_identity
    with pytest.raises(ValueError):
        validate_embedding_identity({"model": "old", "dimension": 3072}, "new", 3072)
    with pytest.raises(ValueError):
        validate_embedding_identity({"model": "new", "dimension": 3072}, "new", 768)


def test_parse_cache_requires_matching_source_pages_and_version():
    from scripts.eval.run_full_recipe_comparison import validate_parse_manifest
    manifest = {"sha256": "old", "selected_pages": [1], "parser": "docling", "parser_version": "1", "effective_config": {"docling_backend": "pdfium", "ocr": False}}
    with pytest.raises(ValueError):
        validate_parse_manifest(manifest, "new", [1], "docling", "1")
    with pytest.raises(ValueError):
        validate_parse_manifest(manifest, "old", [2], "docling", "1")
    with pytest.raises(ValueError):
        validate_parse_manifest(manifest, "old", [1], "docling", "2")


def test_cached_docling_page_coverage_checks_actual_canonical_document(tmp_path):
    import json
    from scripts.eval.run_full_recipe_comparison import validate_cached_docling_pages
    (tmp_path / "document.json").write_text(json.dumps({"documents": [{"pages": {"1": {}}}]}), encoding="utf8")
    with pytest.raises(ValueError):
        validate_cached_docling_pages(tmp_path, [1, 2])


def test_cached_baseline_requires_same_corpus_and_embedding():
    from types import SimpleNamespace
    from scripts.eval.run_full_recipe_comparison import validate_baseline_documents
    doc = SimpleNamespace(metadata={"source_file": "a.pdf", "document_sha256": "old", "embedding_model": "gemini-embedding-2", "embedding_dimension": 3072, "pdf_page": 1})
    with pytest.raises(ValueError):
        validate_baseline_documents([doc], {"a.pdf": "new"}, "gemini-embedding-2", 3072)
    doc.metadata["document_sha256"] = "new"
    with pytest.raises(ValueError):
        validate_baseline_documents([doc], {"a.pdf": "new"}, "other", 3072)


def test_preservation_audit_excludes_cached_control_without_parse_blocks(tmp_path):
    import json
    from scripts.eval.run_full_recipe_comparison import eligible_recipes
    (tmp_path / "parse-report.json").write_text(json.dumps({"recipes": [
        {"parser": "pdfplumber", "chunking": "page"}, {"parser": "pypdf", "chunking": "recursive", "control": True}]}), encoding="utf8")
    assert eligible_recipes(tmp_path, include_controls=False) == [("pdfplumber", "page")]
