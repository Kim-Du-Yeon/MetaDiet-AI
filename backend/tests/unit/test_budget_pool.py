from contextlib import asynccontextmanager
from unittest.mock import AsyncMock
import pytest


async def test_budget_connection_returns_transaction_on_success_and_failure(monkeypatch):
    from app.db import budget_pool
    outcomes = []
    conn = AsyncMock()

    class Pool:
        @asynccontextmanager
        async def connection(self):
            try:
                yield conn
            except ValueError:
                outcomes.append('rollback')
                raise
            else:
                outcomes.append('commit')

    monkeypatch.setattr(budget_pool, '_pool', Pool())
    async with budget_pool.connection() as selected:
        assert selected is conn
    with pytest.raises(ValueError):
        async with budget_pool.connection():
            raise ValueError('fixture')
    assert outcomes == ['commit', 'rollback']
    assert conn.execute.await_count == 2


async def test_uninitialized_budget_pool_preserves_cli_connection(monkeypatch):
    from app.db import budget_pool
    conn = object()
    @asynccontextmanager
    async def direct():
        yield conn
    monkeypatch.setattr(budget_pool, '_pool', None)
    monkeypatch.setattr(budget_pool, 'direct_connection', direct)
    async with budget_pool.connection() as selected:
        assert selected is conn
