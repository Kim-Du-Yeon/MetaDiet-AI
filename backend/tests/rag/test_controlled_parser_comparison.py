from pathlib import Path
import pytest
from scripts.eval.run_controlled_parser_comparison import select_pages, validate_artifact, runtime_environment


def test_selection_includes_alternative_evidence_and_structure_checks():
    sources = [{'path': 'a.pdf'}, {'path': 'b.pdf'}]
    cases = [{'gold_source': 'a.pdf', 'gold_page': 3, 'acceptable_evidence': [{'source': 'a.pdf', 'pdf_pages': [7]}]}]
    anchors = {'text_anchors': [{'source': 'b.pdf', 'page': 2}], 'table_rows': []}
    assert select_pages(sources, {'a.pdf': [1], 'b.pdf': [1]}, cases, anchors) == {'a.pdf': [1, 3, 7], 'b.pdf': [1, 2]}
    with pytest.raises(ValueError):
        select_pages(sources, {'a.pdf': [1], 'b.pdf': [0]}, cases, anchors)


def test_manifest_rejects_wrong_code_source_and_backend():
    expected = {'sha256': 'source', 'parser': 'docling', 'pages': [1], 'code': 'code', 'backend': 'docling_parse', 'config': {'parser_threads': 1}}
    manifest = {'sha256': 'source', 'parser': 'docling', 'selected_pages': [1], 'ingestion_code_sha256': 'code', 'effective_config': {'ocr': False, 'docling_backend': 'docling_parse', 'docling_config': {'parser_threads': 1}}}
    validate_artifact(manifest, expected)
    for key in ['sha256', 'ingestion_code_sha256']:
        with pytest.raises(ValueError):
            validate_artifact({**manifest, key: 'different'}, expected)
    with pytest.raises(ValueError):
        validate_artifact({**manifest, 'effective_config': {**manifest['effective_config'], 'docling_backend': 'pdfium'}}, expected)


def test_runtime_temp_and_caches_stay_inside_workspace(tmp_path):
    overrides = runtime_environment(tmp_path)
    for key in ['TEMP', 'TMP', 'TMPDIR', 'PIP_CACHE_DIR', 'HF_HOME']:
        assert Path(overrides[key]).is_relative_to(tmp_path)
        assert Path(overrides[key]).is_dir()


def test_failed_cache_is_not_reused(tmp_path):
    import json
    from scripts.eval.run_controlled_parser_comparison import completed_cache
    path = tmp_path / 'result.json'
    path.write_text(json.dumps({'status': 'wall_timeout'}))
    assert completed_cache(path) is None
    path.write_text(json.dumps({'status': 'completed', 'artifact': 'verified-later'}))
    assert completed_cache(path)['artifact'] == 'verified-later'


def test_sections_do_not_join_nonadjacent_selected_pages():
    from scripts.eval.run_controlled_parser_comparison import build_bundle
    blocks = [{'id': 'p1', 'kind': 'text', 'pdf_page': 1, 'text': 'adult guideline'},
              {'id': 'p7', 'kind': 'text', 'pdf_page': 7, 'text': 'child guideline'}]
    bundle = build_bundle(blocks, {'sha256': 'source', 'source_file': 'a.pdf'}, 'section')
    assert [c['metadata']['pdf_pages'] for c in bundle['search_chunks']] == [[1], [7]]


def test_parser_version_mismatch_is_rejected():
    expected = {'sha256': 's', 'parser': 'pypdf', 'pages': [1], 'code': 'c', 'parser_version': 'new'}
    manifest = {'sha256': 's', 'parser': 'pypdf', 'selected_pages': [1], 'ingestion_code_sha256': 'c', 'parser_version': 'old', 'effective_config': {'ocr': False}}
    with pytest.raises(ValueError):
        validate_artifact(manifest, expected)

def test_donor_runtime_mismatch_is_rejected():
    from scripts.eval.run_controlled_parser_comparison import validate_runtime
    with pytest.raises(ValueError):
        validate_runtime({'torch': 'old'}, {'torch': 'new'})
    with pytest.raises(ValueError):
        validate_runtime({}, {'torch': 'new'})
    validate_runtime({'torch': 'new'}, {'torch': 'new', 'kiwipiepy': 'irrelevant'})


def test_excerpt_matching_normalizes_range_dash_without_losing_sign():
    from scripts.eval.run_full_recipe_comparison import normalized
    assert normalized('700–3000 mg') == normalized('700-3000 mg')
    assert normalized('-20 mg') != normalized('20 mg')
