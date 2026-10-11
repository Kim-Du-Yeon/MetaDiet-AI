import json
from types import SimpleNamespace

import pytest

from app.rag import retriever


def _settings(tmp_path):
    chunks = tmp_path / "chunks.pkl"
    (tmp_path / "activation.json").write_text(json.dumps({
        "namespace": "metadiet-gemini-test",
        "embedding_model": "gemini-embedding-2",
        "embedding_dimension": 3072,
    }), encoding="utf-8")
    return SimpleNamespace(
        get_chunks_path=lambda: str(chunks),
        pinecone_namespace="metadiet-gemini-test",
        embedding_model="gemini-embedding-2",
        embedding_dimension=3072,
        pinecone_api_key="test-key",
        pinecone_index_name="missing-index",
    )


def test_runtime_retrieval_never_creates_missing_pinecone_index(monkeypatch, tmp_path):
    created = []

    class FakePinecone:
        def __init__(self, **_kwargs):
            pass

        def list_indexes(self):
            return []

        def create_index(self, **kwargs):
            created.append(kwargs)

    monkeypatch.setattr(retriever, "settings", _settings(tmp_path))
    monkeypatch.setattr(retriever, "Pinecone", FakePinecone)
    monkeypatch.setattr(retriever, "_vector_store", None)

    with pytest.raises(RuntimeError, match="does not exist"):
        retriever._load_vector_store(for_build=False)

    assert created == []
