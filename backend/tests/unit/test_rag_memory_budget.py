from unittest.mock import Mock


def test_small_cgroup_does_not_open_corpus(monkeypatch):
    from app.rag import retriever
    monkeypatch.setattr(retriever, '_bm25_loaded', False)
    monkeypatch.setattr(retriever, '_bm25', None)
    monkeypatch.setattr(retriever, '_memory_limit_bytes', lambda: 512 * 1024 * 1024, raising=False)
    corpus_open = Mock(side_effect=AssertionError('must not load'))
    monkeypatch.setattr(retriever, 'open', corpus_open, raising=False)
    assert retriever._get_bm25() is None
    assert retriever._bm25_loaded
    corpus_open.assert_not_called()


def test_memory_limit_reads_v2_and_ignores_unlimited(monkeypatch):
    from app.rag import retriever
    monkeypatch.setattr(retriever.Path, 'read_text', lambda self, **kwargs: '536870912' if self.name == 'memory.max' else '9223372036854771712')
    assert retriever._memory_limit_bytes() == 536870912
    monkeypatch.setattr(retriever.Path, 'read_text', lambda self, **kwargs: 'max')
    assert retriever._memory_limit_bytes() is None


def test_larger_container_keeps_existing_corpus_path(monkeypatch):
    from app.rag import retriever
    monkeypatch.setattr(retriever, '_bm25_loaded', False)
    monkeypatch.setattr(retriever, '_bm25', None)
    monkeypatch.setattr(retriever, '_memory_limit_bytes', lambda: 1024 * 1024 * 1024)
    corpus_open = Mock(side_effect=OSError('fixture'))
    monkeypatch.setattr(retriever, 'open', corpus_open, raising=False)
    assert retriever._get_bm25() is None
    corpus_open.assert_called_once()
