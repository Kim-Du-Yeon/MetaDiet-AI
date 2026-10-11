import json

import pytest


def _case(case_id="new-en", *, group="new", language="en"):
    return {
        "id": case_id,
        "case_group": group,
        "question": "A new question?",
        "language": language,
        "split": "final",
        "gold_source": "source.pdf",
        "gold_page": 3,
        "gold_excerpt": "new evidence",
        "gold_answer": "A grounded answer.",
        "document_sha256": "a" * 64,
        "review_status": "reviewed",
        "reviewer": "source reviewer",
        "review_scope": "factual source-text review only",
        "acceptable_evidence": [{"source": "source.pdf", "pdf_pages": [3], "core_excerpt": "new evidence"}],
        "applicability": "adults",
        "expected_action": "answer_with_scope_and_citation",
    }


def test_final_dataset_requires_reviewed_bilingual_disjoint_groups(tmp_path):
    from scripts.eval.run_final_rag_evaluation import validate_final_dataset

    cases = [_case("new-en", group="new", language="en"),
             _case("new-ko", group="new", language="ko")]
    prior = [_case("old-en", group="old", language="en")]
    validate_final_dataset(cases, prior_cases=prior, source_dir=tmp_path, verify_sources=False)

    with pytest.raises(ValueError, match="overlap"):
        validate_final_dataset(cases, prior_cases=[_case("old-en", group="new")],
                               source_dir=tmp_path, verify_sources=False)
    with pytest.raises(ValueError, match="language pair"):
        validate_final_dataset(cases[:1], prior_cases=[], source_dir=tmp_path, verify_sources=False)


def test_final_dataset_verifies_source_hash(tmp_path):
    from scripts.eval.run_final_rag_evaluation import validate_final_dataset

    source = tmp_path / "source.pdf"
    source.write_bytes(b"real source")
    cases = [_case("new-en", language="en"), _case("new-ko", language="ko")]
    with pytest.raises(ValueError, match="SHA"):
        validate_final_dataset(cases, prior_cases=[], source_dir=tmp_path, verify_sources=True)


def test_evidence_diagnostics_accepts_any_reviewed_page_and_excerpt():
    from scripts.eval.run_final_rag_evaluation import evidence_diagnostics

    case = _case()
    docs = [{"text": "prefix NEW   EVIDENCE suffix",
             "metadata": {"source_file": "source.pdf", "page_number": 3}}]
    assert evidence_diagnostics(case, docs) == {
        "source_page_hit": True,
        "excerpt_hit": True,
    }


def test_frozen_identity_changes_with_dataset_or_recipe(tmp_path):
    from scripts.eval.run_final_rag_evaluation import frozen_identity

    dataset = tmp_path / "gold.json"
    dataset.write_text(json.dumps([_case()]), encoding="utf-8")
    first = frozen_identity(dataset, {"embedding_dimension": 3072})
    second = frozen_identity(dataset, {"embedding_dimension": 768})
    assert first != second
    dataset.write_text(json.dumps([_case("changed")]), encoding="utf-8")
    assert frozen_identity(dataset, {"embedding_dimension": 3072}) != first


def test_saved_answer_scorer_requires_dataset_hash_for_final_scope():
    from scripts.eval.score_saved_answers import (
        FINAL_METRIC_NAMES,
        score_trace_options,
        validate_reference_overlay,
        validate_score_scope,
    )

    with pytest.raises(ValueError, match="dataset SHA"):
        validate_score_scope("final-post-selection", None)
    validate_score_scope("final-post-selection", "a" * 64)
    validate_score_scope("development", None)
    assert FINAL_METRIC_NAMES == ("faithfulness", "context_recall", "factual_correctness")
    rows = [{"id": "one"}, {"id": "two"}]
    overlay = {"base_dataset_sha256": "a" * 64,
               "references": {"one": "하나", "two": "둘"}}
    assert validate_reference_overlay(overlay, rows, "a" * 64) == overlay["references"]
    with pytest.raises(ValueError, match="identity"):
        validate_reference_overlay(overlay, rows, "b" * 64)
    with pytest.raises(ValueError, match="case IDs"):
        validate_reference_overlay({**overlay, "references": {"one": "하나"}}, rows, "a" * 64)
    assert score_trace_options("eval-1", "case-1", "faithfulness", "final-post-selection") == {
        "metadata": {"evaluation_id": "eval-1", "case_id": "case-1",
                     "metric": "faithfulness", "evaluation_scope": "final-post-selection"}
    }


def test_final_recipe_must_match_runtime_and_activated_chunks(tmp_path):
    from scripts.eval.run_final_rag_evaluation import validate_active_recipe

    activation = {
        "namespace": "metadiet-gemini-build",
        "embedding_model": "gemini-embedding-2",
        "embedding_dimension": 3072,
    }
    chunk_metadata = {
        "parser": "pypdf", "chunking": "recursive",
        "embedding_model": "gemini-embedding-2", "embedding_dimension": 3072,
    }
    runtime = {
        "pinecone_namespace": "metadiet-gemini-build",
        "embedding_model": "gemini-embedding-2",
        "embedding_dimension": 3072,
        "rag_candidate_k": 20,
    }
    validate_active_recipe(runtime, activation, chunk_metadata)
    with pytest.raises(ValueError, match="candidate_k"):
        validate_active_recipe({**runtime, "rag_candidate_k": 12}, activation, chunk_metadata)
    with pytest.raises(ValueError, match="parser"):
        validate_active_recipe(runtime, activation, {**chunk_metadata, "parser": "docling"})


def test_cached_case_reuses_only_complete_matching_rows():
    from scripts.eval.run_final_rag_evaluation import validate_cached_case

    case = _case()
    complete = {
        "identity": "frozen", "id": case["id"], "case_group": case["case_group"],
        "language": case["language"], "question": case["question"],
        "reference": case["gold_answer"], "status": "completed", "context": "x",
        "response": "y", "documents": [], "latency_seconds": 1.0,
        "grounded": True, "source_page_hit": True, "excerpt_hit": True,
        "attempts": [{"status": "completed"}],
    }
    assert validate_cached_case(complete, case, "frozen") is True
    assert validate_cached_case({**complete, "status": "failed"}, case, "frozen") is False
    with pytest.raises(ValueError, match="question"):
        validate_cached_case({**complete, "question": "changed"}, case, "frozen")


def test_final_scoring_inputs_are_bound_to_dataset_answers_and_capture(tmp_path):
    from scripts.eval.score_saved_answers import validate_final_inputs, validate_adjudication

    dataset = tmp_path / "dataset.json"
    answers = tmp_path / "answers.json"
    report = tmp_path / "capture-report.json"
    adjudication = tmp_path / "adjudication.json"
    case = _case()
    row = {"id": case["id"], "question": case["question"],
           "reference": case["gold_answer"], "identity": "capture-1"}
    dataset.write_text(json.dumps([case]), encoding="utf-8")
    answers.write_text(json.dumps([row]), encoding="utf-8")
    from scripts.eval.score_saved_answers import file_sha256
    report.write_text(json.dumps({"identity": "capture-1", "status": "completed",
        "completed": 1, "failed": 0, "cases": [case["id"]],
        "dataset_sha256": file_sha256(dataset), "answers_sha256": file_sha256(answers)}), encoding="utf-8")
    provenance = validate_final_inputs(dataset, answers, report)
    assert provenance["capture_identity"] == "capture-1"
    adjudication.write_text(json.dumps({"capture_identity": "capture-1",
        "dataset_sha256": file_sha256(dataset), "answers_sha256": file_sha256(answers),
        "cases": [{"id": case["id"]}]}), encoding="utf-8")
    validate_adjudication(adjudication, provenance, [row])
    answers.write_text(json.dumps([{**row, "reference": "tampered"}]), encoding="utf-8")
    with pytest.raises(ValueError, match="answers SHA"):
        validate_final_inputs(dataset, answers, report)
