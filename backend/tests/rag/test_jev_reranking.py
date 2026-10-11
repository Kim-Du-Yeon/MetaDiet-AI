from unittest.mock import AsyncMock

from langchain_core.documents import Document
from app.agents.runtime import ExecutionBudget
from app.core.jev import Decision


async def test_jev_ranking_uses_relevance_probability_and_shared_budget():
    from app.rag.jev_reranker import rerank
    client = AsyncMock()
    client.choose.side_effect = [
        Decision(("relevant", "irrelevant"), choice="irrelevant", probabilities={"relevant": .1, "irrelevant": .9}),
        Decision(("relevant", "irrelevant"), choice="relevant", probabilities={"relevant": .8, "irrelevant": .2}),
    ]
    docs = [Document(page_content=t) for t in ("wrong", "right")]
    budget = ExecutionBudget()
    result = await rerank("question", docs, client=client, budget=budget, k=1)
    assert result["docs"] == [docs[1]]
    assert all(call.kwargs["budget"] is budget for call in client.choose.call_args_list)


async def test_partial_failure_preserves_baseline_order_instead_of_mixing_scores():
    from app.rag.jev_reranker import rerank
    client = AsyncMock()
    client.choose.side_effect = [
        Decision(("relevant", "irrelevant"), fallback_reason="timeout"),
        Decision(("relevant", "irrelevant"), choice="relevant", probabilities={"relevant": .99, "irrelevant": .01}),
    ]
    docs = [Document(page_content=t) for t in ("first", "second")]
    result = await rerank("question", docs, client=client, budget=ExecutionBudget(), k=1)
    assert result["docs"] == [docs[0]]
    assert result["fallback_reason"] == "incomplete_scores"


async def test_insufficient_budget_skips_all_jev_calls():
    from app.rag.jev_reranker import rerank
    client = AsyncMock()
    docs = [Document(page_content=str(i)) for i in range(20)]
    result = await rerank("question", docs, client=client, budget=ExecutionBudget(max_model_calls=12))
    assert result["docs"] == docs[:4]
    assert result["fallback_reason"] == "budget_insufficient"
    client.choose.assert_not_called()
