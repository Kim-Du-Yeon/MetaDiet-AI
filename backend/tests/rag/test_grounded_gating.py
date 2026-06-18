import pytest
from langchain_core.documents import Document
from langchain_openai import ChatOpenAI

import app.rag.retriever as retriever_module
from tests.conftest import FakeVectorStore


def _doc(content="some relevant content", source="a.pdf", page=1):
    return Document(page_content=content, metadata={"source_file": source, "page": page})


@pytest.fixture(autouse=True)
def _disable_bm25_and_reranker(monkeypatch):
    """BM25/FlashRank 로컬 모델 로드를 건너뛰어 dense-only 경로로 테스트(빠르고 결정적)."""
    monkeypatch.setattr(retriever_module, "_get_bm25", lambda: None)
    monkeypatch.setattr(retriever_module, "_get_reranker", lambda: None)


async def test_grounded_true_returns_context(monkeypatch):
    store = FakeVectorStore([(_doc("relevant content here"), 0.9)])
    monkeypatch.setattr(retriever_module, "get_vector_store", lambda: store)

    result = await retriever_module.retrieve("protein intake recommendation", k=4, max_docs=3)

    assert result["grounded"] is True
    assert "relevant content here" in result["context"]


async def test_grounded_false_returns_empty_context(monkeypatch):
    store = FakeVectorStore([(_doc("irrelevant content"), 0.05)])
    monkeypatch.setattr(retriever_module, "get_vector_store", lambda: store)

    result = await retriever_module.retrieve("protein intake recommendation", k=4, max_docs=3)

    assert result["grounded"] is False
    assert result["context"] == ""


async def test_english_query_no_translation_llm_call(monkeypatch):
    calls = []

    async def fake_ainvoke(self, *a, **k):
        calls.append(1)
        raise AssertionError("영어 입력인데 번역 LLM이 호출됨")

    monkeypatch.setattr(ChatOpenAI, "ainvoke", fake_ainvoke)
    store = FakeVectorStore([(_doc(), 0.9)])
    monkeypatch.setattr(retriever_module, "get_vector_store", lambda: store)

    await retriever_module.retrieve("protein intake recommendation", k=4)

    assert len(calls) == 0


async def test_korean_query_calls_translation_llm_once(monkeypatch):
    calls = []

    class _FakeResp:
        content = "protein intake recommendation"

    async def fake_ainvoke(self, *a, **k):
        calls.append(1)
        return _FakeResp()

    monkeypatch.setattr(ChatOpenAI, "ainvoke", fake_ainvoke)
    store = FakeVectorStore([(_doc(), 0.9)])
    monkeypatch.setattr(retriever_module, "get_vector_store", lambda: store)

    await retriever_module.retrieve("단백질 얼마나 먹어야 해?", k=4)

    assert len(calls) == 1
