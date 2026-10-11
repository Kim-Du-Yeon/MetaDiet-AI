from unittest.mock import AsyncMock
from app.rag import qa


async def test_evaluation_answer_uses_exact_retrieved_context(monkeypatch):
    retrieve = AsyncMock(side_effect=AssertionError("must not retrieve again"))
    monkeypatch.setattr(qa, "retrieve", retrieve)
    result = await qa.answer_from_knowledge("test", retrieval_result={
        "context": "", "grounded": False, "max_score": 0, "docs": []})
    assert result["answer"] == qa.NO_EVIDENCE
    retrieve.assert_not_called()
