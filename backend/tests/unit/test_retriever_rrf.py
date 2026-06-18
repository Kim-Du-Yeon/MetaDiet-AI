from langchain_core.documents import Document

from app.rag.retriever import _doc_key, _rrf

_PREFIX = "x" * 60


def _doc(tail, source, page):
    return Document(page_content=_PREFIX + tail, metadata={"source_file": source, "page": page})


def test_doc_key_same_source_page_prefix_same_key():
    d1 = _doc(" tail one", "a.pdf", 3)
    d2 = _doc(" tail two but different ending entirely", "a.pdf", 3)
    assert _doc_key(d1) == _doc_key(d2)


def test_doc_key_different_page_different_key():
    d1 = _doc(" same", "a.pdf", 1)
    d2 = _doc(" same", "a.pdf", 2)
    assert _doc_key(d1) != _doc_key(d2)


def test_doc_key_different_source_different_key():
    d1 = _doc(" same", "a.pdf", 1)
    d2 = _doc(" same", "b.pdf", 1)
    assert _doc_key(d1) != _doc_key(d2)


def test_rrf_merges_and_dedups_overlap():
    a = _doc(" A", "x.pdf", 1)
    b = _doc(" B", "y.pdf", 2)
    c = _doc(" C", "z.pdf", 3)
    dense = [a, b]
    sparse = [b, c]  # b는 양쪽에 다 있음 -> 중복 제거 확인

    merged = _rrf(dense, sparse)
    keys = [_doc_key(d) for d in merged]

    assert len(keys) == len(set(keys))
    assert len(merged) == 3


def test_rrf_ranks_doc_found_in_both_lists_higher():
    a = _doc(" only dense", "x.pdf", 1)
    b = _doc(" both", "y.pdf", 2)
    c = _doc(" only sparse", "z.pdf", 3)
    dense = [b, a]
    sparse = [b, c]

    merged = _rrf(dense, sparse)

    assert _doc_key(merged[0]) == _doc_key(b)


def test_rrf_empty_sparse_preserves_dense_order():
    a = _doc(" first", "x.pdf", 1)
    b = _doc(" second", "y.pdf", 2)

    merged = _rrf([a, b], [])

    assert [_doc_key(d) for d in merged] == [_doc_key(a), _doc_key(b)]
