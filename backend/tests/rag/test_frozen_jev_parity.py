import pytest


def test_jev_rejects_changed_bundle_or_candidate_text():
    from scripts.eval.compare_frozen_jev import validate_candidates
    chunk = {'id': 'one', 'text': 'original', 'metadata': {'page': 1}}
    bundle = {'search_chunks': [chunk]}
    rows = [{'candidates': [chunk]}]
    validate_candidates(bundle, rows, 'same', 'same')
    with pytest.raises(ValueError): validate_candidates(bundle, rows, 'old', 'new')
    with pytest.raises(ValueError):
        validate_candidates(bundle, [{'candidates': [{**chunk, 'text': 'changed'}]}], 'same', 'same')
