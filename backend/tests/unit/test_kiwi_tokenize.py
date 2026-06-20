import app.rag.retriever as retriever_module
from app.rag.retriever import kiwi_tokenize


def test_korean_text_tokenized_into_morphemes():
    tokens = kiwi_tokenize("한국어 형태소 분석기를 적용합니다")
    assert isinstance(tokens, list)
    assert all(isinstance(t, str) for t in tokens)
    # 형태소 분석은 어절 그대로 쪼개는 단순 split보다 토큰 수가 더 많아야 함
    assert len(tokens) > len("한국어 형태소 분석기를 적용합니다".split())


def test_english_text_returns_nonempty_tokens():
    tokens = kiwi_tokenize("protein intake recommendation")
    assert tokens


def test_get_kiwi_returns_same_singleton_instance(monkeypatch):
    monkeypatch.setattr(retriever_module, "_kiwi", None)

    first = retriever_module._get_kiwi()
    second = retriever_module._get_kiwi()

    assert first is second


def test_tokenize_failure_falls_back_to_split(monkeypatch):
    def boom():
        raise RuntimeError("kiwi load failed")
    monkeypatch.setattr(retriever_module, "_get_kiwi", boom)

    assert kiwi_tokenize("fallback text here") == "fallback text here".split()
