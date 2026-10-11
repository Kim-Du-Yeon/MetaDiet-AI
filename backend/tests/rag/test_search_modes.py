import pytest


def test_rrf_combines_channels_without_duplicating_candidates():
    from scripts.eval.compare_search_modes import fuse
    assert fuse([[0, 1], [1, 2]], 3) == [1, 0, 2]
    assert fuse([[0, 0, 1]], 3) == [0, 1]


def test_rrf_preserves_candidate_cap_and_rejects_invalid_cap():
    from scripts.eval.compare_search_modes import fuse
    assert fuse([[0, 1], [2, 3]], 2) == [0, 2]
    with pytest.raises(ValueError): fuse([[0]], 0)


def test_vector_identity_rejects_stale_same_shape_embeddings():
    from scripts.eval.compare_search_modes import validate_vector_identity
    expected = {'source_parse': 'source', 'bundles': {'recipe': 'chunks'},
                'dataset': 'gold', 'translations': 'queries'}
    identity = {**expected, 'model': 'gemini-embedding-2', 'base_dimension': 3072}
    validate_vector_identity(identity, expected)
    for key in ('source_parse', 'bundles', 'dataset', 'translations', 'model', 'base_dimension'):
        with pytest.raises(ValueError):
            validate_vector_identity({**identity, key: 'stale'}, expected)
