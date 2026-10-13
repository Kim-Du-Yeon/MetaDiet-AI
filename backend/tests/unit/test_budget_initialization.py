from contextlib import asynccontextmanager
from datetime import datetime, timezone
import pytest
from app.db.execution_budget import DurableBudget


class Store:
    def __init__(self):
        self.row = None
        self.inserts = 0
        self.fail_commit = False

    @asynccontextmanager
    async def connect(self):
        yield self
        if self.fail_commit:
            self.row = None
            raise ConnectionError('commit failed')

    async def execute(self, sql, params):
        if sql.startswith('insert'):
            self.inserts += 1
            self.row = self.row or {'usage': params[2].obj, 'active_since': None}
        if sql.startswith('update'):
            self.row = {'usage': params[0].obj, 'active_since': params[1]}
        return self

    async def fetchone(self):
        return self.row


async def test_insert_once_only_after_committed_initialization():
    store = Store()
    budget = DurableBudget('u', 'r', {'elapsed_seconds': 120, 'model_calls': 2}, connect=store.connect, initialize_once=True)
    await budget.update()
    await budget.reserve('model')
    await budget.reserve('model')
    assert store.inserts == 1
    from app.agents.runtime import ExecutionStopped
    with pytest.raises(ExecutionStopped):
        await budget.reserve('model')
    assert store.row['usage']['model_calls'] == 2


async def test_failed_commit_does_not_mark_initialized():
    store = Store(); store.fail_commit = True
    budget = DurableBudget('u', 'r', {'elapsed_seconds': 120}, connect=store.connect, initialize_once=True)
    with pytest.raises(ConnectionError):
        await budget.update()
    store.fail_commit = False
    await budget.update()
    assert store.inserts == 2


async def test_deleted_row_is_reinitialized_and_seed_never_reduces_counts():
    store = Store()
    budget = DurableBudget('u', 'r', {'elapsed_seconds': 120, 'model_calls': 3}, connect=store.connect, initialize_once=True)
    await budget.update(seed={'model_calls': 2})
    await budget.update(seed={'model_calls': 1})
    assert store.row['usage']['model_calls'] == 2
    # Removing an active budget must fail closed, not reset the run's allowance.
    store.row = None
    from app.agents.runtime import ExecutionStopped
    with pytest.raises(ExecutionStopped, match='budget_row_missing'):
        await budget.reserve('model')
