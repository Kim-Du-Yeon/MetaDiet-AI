from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage

from app.agents.execution_stream import set_event_sink, reset_event_sink
from app.agents.runtime import run_agent, ExecutionBudget
from app.core import llm


async def test_sdk_preparation_is_outside_provider_timer(monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setattr(llm, 'get_settings', lambda: get_settings().model_copy(
        update={'gemini_api_key': 'not-a-real-key'}))
    timeline = []
    class Provider:
        def __init__(self, **kwargs):
            timeline.append('constructed')
        async def ainvoke(self, messages, config=None):
            timeline.append('called')
            return AIMessage(content='채소를 곁들이세요.')
    monkeypatch.setattr(llm, 'ChatGoogleGenerativeAI', Provider)
    async def sink(kind, payload):
        if kind == 'stage_timing':
            timeline.append(payload['stage'])
    token = set_event_sink(sink)
    try:
        result = await run_agent(model=llm.get_chat_model(), instruction='private',
            request='private', tools=[], budget=ExecutionBudget(), agent_name='meal')
    finally:
        reset_event_sink(token)
    assert result.status == 'completed'
    assert timeline.index('sdk_prepare_meal') < timeline.index('called')
    assert 'provider_roundtrip' in timeline
    assert timeline.index('provider_roundtrip') < timeline.index('model_meal')


async def test_provider_failure_keeps_safe_phase_timing():
    from app.agents.model_delivery import invoke_model
    class Provider:
        async def ainvoke(self, messages, config=None):
            raise ValueError('private credential and health value')
    events = []
    async def sink(kind, payload):
        events.append((kind, payload))
    token = set_event_sink(sink)
    try:
        with pytest.raises(ValueError):
            await invoke_model(Provider(), ['private'], None)
    finally:
        reset_event_sink(token)
    timing = [p for k, p in events if k == 'stage_timing']
    assert timing and timing[0]['stage'] == 'provider_roundtrip'
    assert timing[0]['elapsed_ms'] >= 0
    assert 'private' not in str(events)
