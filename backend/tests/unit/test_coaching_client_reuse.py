import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage

from app.core import llm


@pytest.fixture
def provider_factory(monkeypatch):
    monkeypatch.setattr(llm, '_shared_provider', None, raising=False)
    settings = SimpleNamespace(gemini_api_key='synthetic-key', gemini_model='chat-test',
        gemini_vision_model='vision-test', gemini_eval_model='judge-test',
        model_timeout_seconds=30, eval_model_timeout_seconds=90, model_max_retries=0)
    monkeypatch.setattr(llm, 'get_settings', lambda: settings)
    created = []
    class Provider:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.client = SimpleNamespace(aio=SimpleNamespace(aclose=AsyncMock()), close=lambda: None)
            self.aclose = AsyncMock()
            created.append(self)
        def bind_tools(self, tools, **kwargs):
            return (self, tools)
        async def ainvoke(self, value, config=None):
            await asyncio.sleep(0)
            return AIMessage(content=value + ':' + config['metadata']['user'])
    monkeypatch.setattr(llm, 'ChatGoogleGenerativeAI', Provider)
    return created, settings


async def test_reuse_is_opt_in_and_tool_bindings_are_not_shared(provider_factory):
    created, _ = provider_factory
    a, b = llm.get_chat_model(reuse_provider=True), llm.get_chat_model(reuse_provider=True)
    assert a.bind_tools(['a'])[0] is b.bind_tools(['b'])[0]
    assert a.bind_tools(['a'])[1] != b.bind_tools(['b'])[1]
    assert len(created) == 1
    llm.get_chat_model().prepare()
    llm.get_chat_model().prepare()
    assert len(created) == 3


async def test_concurrent_requests_keep_messages_and_config_separate(provider_factory):
    results = await asyncio.gather(*[llm.get_chat_model(reuse_provider=True).ainvoke(
        'message-'+str(i), config={'metadata': {'user': str(i)}}) for i in range(10)])
    assert [r.content for r in results] == ['message-'+str(i)+':'+str(i) for i in range(10)]
    assert len(provider_factory[0]) == 1


@pytest.mark.parametrize('change', ['key', 'model', 'thinking', 'temperature', 'tokens', 'timeout', 'retry'])
async def test_configuration_changes_do_not_reuse_old_client(provider_factory, change):
    created, settings = provider_factory
    first = llm.get_chat_model(reuse_provider=True, thinking_level='low')._client()
    kwargs = {'reuse_provider': True, 'thinking_level': 'low'}
    if change == 'key': settings.gemini_api_key = 'rotated-synthetic-key'
    elif change == 'model': kwargs['model_name'] = 'different-model'
    elif change == 'thinking': kwargs['thinking_level'] = 'medium'
    elif change == 'temperature': kwargs['temperature'] = 1
    elif change == 'tokens': kwargs['max_tokens'] = 100
    elif change == 'timeout': settings.model_timeout_seconds = 5
    else: settings.model_max_retries = 1
    assert llm.get_chat_model(**kwargs)._client() is not first
    assert len(created) == 2


async def test_shutdown_closes_async_client_and_releases_shared_reference(provider_factory):
    model = llm.get_chat_model(reuse_provider=True)
    provider = model._client()
    await llm.close_shared_model_client()
    provider.aclose.assert_awaited_once()
    provider.client.aio.aclose.assert_not_awaited()
    assert llm.get_chat_model(reuse_provider=True)._client() is not provider


async def test_other_loop_does_not_receive_or_close_cached_client(provider_factory):
    provider = llm.get_chat_model(reuse_provider=True)._client()
    llm._shared_provider.loop = object()
    assert llm.get_chat_model(reuse_provider=True)._client() is not provider
    await llm.close_shared_model_client()
    provider.aclose.assert_not_awaited()


def test_role_and_nonrunning_loop_cannot_share_provider(provider_factory):
    with pytest.raises(ValueError): llm.get_chat_model(role='eval', reuse_provider=True)
    with pytest.raises(ValueError): llm.get_chat_model(role='vision', reuse_provider=True)
    assert llm.get_chat_model(reuse_provider=True)._client() is not llm.get_chat_model(reuse_provider=True)._client()
