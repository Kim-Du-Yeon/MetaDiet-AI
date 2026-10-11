import asyncio
import time
import pytest
from app.rag import retriever


async def test_blocking_dense_search_does_not_block_request_timeout(monkeypatch):
    monkeypatch.setattr(retriever, "get_vector_store", lambda: object())
    def slow(*args):
        time.sleep(0.15)
        return [], 0
    monkeypatch.setattr(retriever, "_dense_search", slow)
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(retriever.retrieve("english", use_hybrid=False, use_rerank=False), timeout=0.01)
