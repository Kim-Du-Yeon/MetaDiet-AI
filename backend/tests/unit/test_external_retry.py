import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest
from google.genai.errors import ServerError
from app.core.external_retry import retry_external


@pytest.mark.parametrize('error', [httpx.ReadError('private'), ServerError(504, {'error': {'message': 'private'}})])
async def test_transient_retries_once_and_reserves_budget(error):
    call = AsyncMock(side_effect=[error, 'ok'])
    reserve = AsyncMock()
    assert await retry_external(call, operation='model', before_retry=reserve, delay=0) == 'ok'
    assert call.await_count == 2
    reserve.assert_awaited_once()


async def test_persistent_failure_stops_after_two_attempts():
    call = AsyncMock(side_effect=httpx.ReadError('private'))
    with pytest.raises(httpx.ReadError):
        await retry_external(call, operation='read', delay=0)
    assert call.await_count == 2


@pytest.mark.parametrize('error', [ValueError('bad input'), asyncio.CancelledError()])
async def test_nontransient_and_cancellation_not_retried(error):
    call = AsyncMock(side_effect=error)
    with pytest.raises(type(error)):
        await retry_external(call, operation='model', delay=0)
    assert call.await_count == 1


async def test_budget_denial_prevents_second_provider_call():
    call = AsyncMock(side_effect=httpx.ReadError('private'))
    reserve = AsyncMock(side_effect=RuntimeError('model_call_limit'))
    with pytest.raises(RuntimeError, match='model_call_limit'):
        await retry_external(call, operation='model', before_retry=reserve, delay=0)
    assert call.await_count == 1


async def test_runtime_retry_charges_model_without_replaying_tools():
    from langchain_core.messages import AIMessage
    from app.agents.runtime import ExecutionBudget, run_agent
    model = AsyncMock()
    model.ainvoke.side_effect = [httpx.ReadError('private'), AIMessage(content='done')]
    budget = ExecutionBudget(max_model_calls=2)
    result = await run_agent(model=model, instruction='help', request='advice', tools=[], budget=budget)
    assert result.status == 'completed'
    assert budget.model_calls == 2 and budget.tool_calls == 0


async def test_retry_respects_outer_deadline():
    call = AsyncMock(side_effect=httpx.ReadError('private'))
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(retry_external(call, operation='read'), timeout=.01)
    assert call.await_count == 1
