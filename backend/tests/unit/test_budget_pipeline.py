from contextlib import asynccontextmanager
from unittest.mock import AsyncMock
import pytest
from app.db import budget_pool


@pytest.mark.parametrize('fail', [False, True])
async def test_pipeline_finishes_before_pool_commit_and_propagates_failure(monkeypatch, fail):
    events = []
    conn = AsyncMock()
    @asynccontextmanager
    async def pipeline():
        events.append('pipeline_enter')
        yield
        events.append('pipeline_sync')
        if fail:
            raise ConnectionError('sync failure')
    conn.pipeline = pipeline
    class Pool:
        @asynccontextmanager
        async def connection(self):
            try:
                yield conn
            except ConnectionError:
                events.append('rollback')
                raise
            else:
                events.append('commit')
    monkeypatch.setattr(budget_pool, '_pool', Pool())
    async def run():
        async with budget_pool.connection(pipeline=True) as selected:
            assert selected is conn
            events.append('body')
        events.append('returned')
    if fail:
        with pytest.raises(ConnectionError):
            await run()
        assert events == ['pipeline_enter', 'body', 'pipeline_sync', 'rollback']
    else:
        await run()
        assert events == ['pipeline_enter', 'body', 'pipeline_sync', 'commit', 'returned']


async def test_pipeline_is_disabled_by_default(monkeypatch):
    from app.core.config import Settings
    assert Settings.model_fields['budget_pipeline'].default is False
