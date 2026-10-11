from types import SimpleNamespace

import pytest

from app.core.embeddings import GeminiEmbeddings


def test_documents_are_not_aggregated_and_query_has_retrieval_prefix(monkeypatch, tmp_path):
    import app.core.embeddings as module
    monkeypatch.setattr(module, "get_settings", lambda: SimpleNamespace(embedding_dimension=2, embedding_model="gemini-embedding-2"))
    calls = []

    def embed_content(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(embeddings=[SimpleNamespace(values=[3.0, 4.0])])

    embedding = GeminiEmbeddings(cache_root=tmp_path)
    monkeypatch.setattr(embedding, "_client", lambda: SimpleNamespace(models=SimpleNamespace(embed_content=embed_content)))
    assert embedding.embed_documents(["one", "two"]) == [[0.6, 0.8], [0.6, 0.8]]
    assert embedding.embed_query("question") == [0.6, 0.8]
    assert sorted(call["contents"] for call in calls) == sorted(["title: none | text: one", "title: none | text: two", "task: search result | query: question"])
    assert embedding.embed_documents(["one", "two"]) == [[0.6, 0.8], [0.6, 0.8]]
    assert len(calls) == 3


def test_missing_key_does_not_fall_back(monkeypatch):
    import app.core.embeddings as module
    monkeypatch.setattr(module, "get_settings", lambda: SimpleNamespace(embedding_dimension=3072, embedding_model="gemini-embedding-2", gemini_api_key=""))
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        GeminiEmbeddings().embed_query("question")


def test_legacy_model_is_rejected(monkeypatch):
    import app.core.embeddings as module
    monkeypatch.setattr(module, "get_settings", lambda: SimpleNamespace(embedding_model="legacy-model"))
    with pytest.raises(ValueError, match="rebuild"):
        GeminiEmbeddings().embed_query("question")


def test_retrieval_rejects_missing_build_manifest(monkeypatch, tmp_path):
    from app.rag import retriever
    monkeypatch.setattr(retriever.settings, "rag_chunks_path", str(tmp_path / "chunks.pkl"))
    with pytest.raises(ValueError, match="not activated"):
        retriever.get_vector_store()


def test_retrieval_rejects_foreign_embedding_manifest(monkeypatch, tmp_path):
    import json
    from app.rag import retriever
    monkeypatch.setattr(retriever.settings, "rag_chunks_path", str(tmp_path / "chunks.pkl"))
    (tmp_path / "activation.json").write_text(json.dumps({"namespace": "legacy"}), encoding="utf-8")
    with pytest.raises(ValueError, match="does not match"):
        retriever.get_vector_store()
