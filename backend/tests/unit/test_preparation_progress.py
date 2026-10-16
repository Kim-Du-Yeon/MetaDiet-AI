import asyncio
import json
from contextlib import asynccontextmanager

import pytest
from app.db import thread_lock
from app.agents.execution_stream import progress_for_runtime_event


async def test_preparation_is_sent_before_lock_and_never_unlocks_early(monkeypatch):
    acquired = False
    @asynccontextmanager
    async def lock(*args):
        nonlocal acquired
        acquired = True
        yield
        acquired = False
    monkeypatch.setattr(thread_lock, 'conversation_lock', lock)
    async def factory():
        assert acquired
        yield 'completed'
    stream = thread_lock.serialized_stream(factory, 'synthetic', 'thread')
    first = json.loads((await anext(stream)).removeprefix('data: '))
    assert first['phase'] == 'conversation_wait'
    assert not acquired
    assert 'seq' not in first  # Preparation is transient, not part of replay sequence.
    assert 'checkpoint_restore' in await anext(stream)
    assert acquired
    assert await anext(stream) == 'completed'
    with pytest.raises(StopAsyncIteration):
        await anext(stream)
    assert not acquired


async def test_lock_failure_is_reported_after_waiting_status(monkeypatch):
    @asynccontextmanager
    async def lock(*args):
        raise RuntimeError('private detail')
        yield
    monkeypatch.setattr(thread_lock, 'conversation_lock', lock)
    async def factory():
        yield 'must not run'
    frames = [frame async for frame in thread_lock.serialized_stream(factory, 'u', 't')]
    assert len(frames) == 2
    assert 'error' in frames[-1] and 'private detail' not in frames[-1]


def test_model_preparation_does_not_claim_intent_or_delegation():
    event = progress_for_runtime_event('model_preparing', agent='supervisor')
    assert event['phase'] == 'model_preparation'
    assert '위임' not in event['label']
