import numpy as np
import pytest
from scripts.eval.run_dimension_comparison import project_vectors, validate_matrix


def test_projection_normalizes_prefix_and_preserves_full_vector():
    rows=np.array([[3.,4.,12.]])
    reduced=project_vectors(rows,2)
    assert reduced.shape==(1,2)
    assert np.allclose(reduced,[[.6,.8]])
    assert np.allclose(np.linalg.norm(project_vectors(rows,3),axis=1),[1.])


def test_projection_rejects_invalid_or_zero_prefix():
    with pytest.raises(ValueError): project_vectors(np.array([[0.,0.,1.]]),2)
    with pytest.raises(ValueError): project_vectors(np.array([[float('nan'),1.]]),2)
    with pytest.raises(ValueError): project_vectors(np.array([[1.,2.]]),3)


def test_matrix_validation_rejects_shape_and_non_unit_cache():
    with pytest.raises(ValueError): validate_matrix(np.ones((1,3)),1,3)
    with pytest.raises(ValueError): validate_matrix(np.array([[1.,0.]]),2,2)
    validate_matrix(np.array([[1.,0.]]),1,2)

def test_dimension_source_rejects_legacy_or_incomplete_matrix():
    from scripts.eval.run_dimension_comparison import validate_source
    with pytest.raises(ValueError):
        validate_source({'recipes':[{'parser':'docling','chunking':'page'}]}, {'backend':'pdfium'})
    with pytest.raises(ValueError):
        validate_source({'recipes':[],'excluded':[]}, {'config':{},'pages':{}})


def test_heldout_requires_explicit_mode_and_reviewed_unique_cases():
    from scripts.eval.run_dimension_comparison import validate_cases
    cases = [{'id': 'one', 'split': 'heldout', 'review_status': 'reviewed'}]
    validate_cases(cases, 'heldout')
    with pytest.raises(ValueError): validate_cases(cases, 'development')
    with pytest.raises(ValueError): validate_cases(cases * 2, 'heldout')
    with pytest.raises(ValueError): validate_cases([{**cases[0], 'review_status': 'draft'}], 'heldout')
