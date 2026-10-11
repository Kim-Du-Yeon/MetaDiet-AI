import pytest
from app.rag import retriever


async def test_strict_ablation_refuses_missing_bm25(monkeypatch):
    monkeypatch.setattr(retriever, "get_vector_store", lambda: object())
    monkeypatch.setattr(retriever, "_get_bm25", lambda: None)
    with pytest.raises(RuntimeError, match="BM25"):
        await retriever.retrieve("english", use_rerank=False, strict_components=True)


def test_strict_sparse_propagates_failure(monkeypatch):
    class Broken:
        def invoke(self, query):
            raise ConnectionError("broken")
    monkeypatch.setattr(retriever, "_get_bm25", lambda: Broken())
    with pytest.raises(ConnectionError):
        retriever._sparse_search("english", strict=True)
