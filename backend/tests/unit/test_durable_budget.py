from unittest.mock import AsyncMock
import pytest
from app.agents.runtime import ExecutionBudget, ExecutionStopped
from app.db.execution_budget import DurableBudget
from datetime import datetime, timedelta, timezone


async def test_reservation_persists_before_local_count():
    budget = ExecutionBudget()
    persist = AsyncMock()
    budget.persist = persist
    await budget.reserve("model")
    persist.assert_awaited_once_with("model")
    assert budget.model_calls == 1


async def test_failed_persistence_blocks_execution():
    budget = ExecutionBudget()
    budget.persist = AsyncMock(side_effect=ConnectionError())
    with pytest.raises(ExecutionStopped, match="budget_storage_unavailable"):
        await budget.reserve("tool")
    assert budget.tool_calls == 0


def test_crash_interval_is_counted_but_hitl_wait_is_excluded():
    now = datetime.now(timezone.utc)
    row = {"usage": {"model_calls": 2, "elapsed_seconds": 5}, "active_since": now - timedelta(seconds=10)}
    assert DurableBudget.accrued(row, now)["elapsed_seconds"] == 15
    row["active_since"] = None
    assert DurableBudget.accrued(row, now)["elapsed_seconds"] == 5


async def test_storage_failure_in_team_node_is_a_blocked_result(monkeypatch):
    import app.db.execution_budget as storage
    from app.agents.team import team_node
    durable = AsyncMock()
    durable.update.side_effect = ConnectionError("private connection details")
    monkeypatch.setattr(storage, "DurableBudget", lambda *args: durable)
    result = await team_node({"user_id": "u", "run_id": "r"})
    assert result["execution_status"] == "blocked"
    assert "private" not in str(result)
