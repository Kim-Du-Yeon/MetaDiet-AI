from types import SimpleNamespace
from contextlib import asynccontextmanager

import pytest


@pytest.mark.asyncio
async def test_graph_lifespan_uses_bounded_pool_and_releases_graph(monkeypatch):
    import app.agents.graph as module

    events = []

    class Pool:
        def __init__(self, url, **kwargs):
            events.append(("pool", url, kwargs))

        async def __aenter__(self):
            events.append(("enter",))
            return self

        async def __aexit__(self, exc_type, exc, tb):
            events.append(("exit",))

        async def open(self, wait=False):
            events.append(("open", wait))

    class Saver:
        def __init__(self, pool):
            self.pool = pool

        async def setup(self):
            events.append(("setup",))

    graph = object()
    @asynccontextmanager
    async def budget_lifespan(url):
        assert url == "postgresql://fixture"
        yield
    monkeypatch.setattr("app.db.budget_pool.lifespan", budget_lifespan)
    monkeypatch.setattr(module, "get_settings", lambda: SimpleNamespace(supabase_db_url="postgresql://fixture"))
    monkeypatch.setattr(module, "AsyncConnectionPool", Pool)
    monkeypatch.setattr(module, "AsyncPostgresSaver", Saver)
    monkeypatch.setattr(module, "build_graph", lambda checkpointer: graph)

    async with module.lifespan(object()):
        assert module.get_graph() is graph

    assert module._diet_agent_graph is None
    pool = events[0]
    assert pool[0:2] == ("pool", "postgresql://fixture")
    assert pool[2]["min_size"] == 1
    assert pool[2]["max_size"] == 10
    assert pool[2]["timeout"] == 15
    assert ("open", True) in events
    assert ("setup",) in events
    assert events[-1] == ("exit",)
