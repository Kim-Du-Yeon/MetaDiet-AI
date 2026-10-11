import httpx
import asyncio
from app.agents.runtime import ExecutionBudget
from app.core.jev import JevClient


def response(choice="meal", confidence=1.0):
    return {"model": "jev-1.13.0", "answers": {"decision": {"type": "choice",
        "choice": choice, "confidence": confidence, "probabilities": {"meal": 1.0, "goal": 0.0}}},
        "usage": {"input_tokens": 10, "output_tokens": 2}}


async def test_choice_counts_shared_budget_and_accepts_only_offered_candidates():
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=response()))
    budget = ExecutionBudget()
    result = await JevClient(api_key="synthetic", transport=transport).choose(
        state={"request": "record"}, candidates={"meal": "record food", "goal": "goal"}, budget=budget)
    assert result.choice == "meal" and result.fallback_reason is None
    assert budget.model_calls == 1 and result.usage["input_tokens"] == 10


async def test_invalid_candidate_is_not_accepted():
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=response("delete_everything")))
    result = await JevClient(api_key="synthetic", transport=transport).choose(
        state={}, candidates={"meal": "food", "goal": "goal"}, budget=ExecutionBudget())
    assert result.choice is None and result.fallback_reason == "invalid_response"


async def test_missing_key_does_not_call_api_or_consume_budget():
    budget = ExecutionBudget()
    result = await JevClient(api_key="").choose(state={}, candidates={"meal": "food"}, budget=budget)
    assert result.fallback_reason == "missing_key" and budget.model_calls == 0


async def test_api_error_is_sanitized():
    transport = httpx.MockTransport(lambda request: httpx.Response(429, text="private provider content"))
    result = await JevClient(api_key="synthetic", transport=transport).choose(
        state={}, candidates={"meal": "food", "goal": "goal"}, budget=ExecutionBudget())
    assert result.choice is None and result.fallback_reason == "http_429"
    assert "private" not in str(result)


async def test_malformed_usage_returns_fallback():
    body = response()
    body["usage"] = None
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=body))
    result = await JevClient(api_key="synthetic", transport=transport).choose(
        state={}, candidates={"meal": "food", "goal": "goal"}, budget=ExecutionBudget())
    assert result.fallback_reason == "invalid_response"


async def test_total_request_deadline_respects_shared_budget():
    async def slow(request):
        await asyncio.sleep(.15)
        return httpx.Response(200, json=response())
    result = await JevClient(api_key="synthetic", transport=httpx.MockTransport(slow)).choose(
        state={}, candidates={"meal": "food", "goal": "goal"}, budget=ExecutionBudget(timeout_seconds=.02))
    assert result.fallback_reason == "timeout"
