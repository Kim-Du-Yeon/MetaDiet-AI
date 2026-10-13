"""Reserve calls before external effects; survive crashes and checkpoint rollback."""
from datetime import datetime, timezone
import time
from psycopg.types.json import Jsonb
from app.db.budget_pool import connection
from app.agents.runtime import ExecutionStopped
from app.agents.execution_stream import emit_runtime_event


class DurableBudget:
    def __init__(self, user_id, run_id, limits, connect=connection, *, initialize_once=False):
        self.user_id, self.run_id, self.limits, self.connect = user_id, run_id, limits, connect
        self._initialized = False
        self.initialize_once = initialize_once

    @staticmethod
    def accrued(row, now):
        usage = dict(row["usage"])
        if row["active_since"]:
            usage["elapsed_seconds"] = usage.get("elapsed_seconds", 0) + max(0, (now - row["active_since"]).total_seconds())
        return usage

    async def update(self, kind=None, *, seed=None, finish=False):
        started = time.perf_counter()
        async with self.connect() as conn:
            await emit_runtime_event('stage_timing', stage='budget_connection_wait',
                                     elapsed_ms=(time.perf_counter()-started)*1000)
            sql_started = time.perf_counter()
            if not self.initialize_once or not self._initialized:
                await conn.execute("insert into agent_execution_budgets(user_id,run_id,usage) values(%s,%s,%s) on conflict do nothing",
                                   (self.user_id, self.run_id, Jsonb(seed or {})))
            row = await (await conn.execute("select * from agent_execution_budgets where user_id=%s and run_id=%s for update",
                                           (self.user_id, self.run_id))).fetchone()
            if row is None:
                raise ExecutionStopped('budget_row_missing')
            now = datetime.now(timezone.utc)
            usage = self.accrued(row, now)
            if seed:
                for key, value in seed.items():
                    if key == "delegations":
                        previous = usage.get(key, {})
                        usage[key] = {role: max(previous.get(role, 0), value.get(role, 0)) for role in previous.keys() | value.keys()}
                    else:
                        usage[key] = max(usage.get(key, 0), value)
            if not finish:
                if usage.get("elapsed_seconds", 0) >= self.limits["elapsed_seconds"]:
                    raise ExecutionStopped("execution_timeout")
                if kind:
                    if kind.startswith("delegate:"):
                        role = kind.split(":", 1)[1]
                        delegates = usage.setdefault("delegations", {})
                        delegates[role] = delegates.get(role, 0) + 1
                    else:
                        if usage.get(kind, 0) >= self.limits[kind]:
                            raise ExecutionStopped(f"{kind}_limit")
                        usage[kind] = usage.get(kind, 0) + 1
            await conn.execute("update agent_execution_budgets set usage=%s,active_since=%s,updated_at=%s where user_id=%s and run_id=%s",
                               (Jsonb(usage), None if finish else now, now, self.user_id, self.run_id))
            await emit_runtime_event('stage_timing', stage='budget_sql',
                                     elapsed_ms=(time.perf_counter()-sql_started)*1000)
            commit_started = time.perf_counter()
        # The connection context commits before returning. A failed commit must
        # never enable the INSERT fast path, or reserve an external side effect.
        self._initialized = True
        await emit_runtime_event('stage_timing', stage='budget_commit',
                                 elapsed_ms=(time.perf_counter()-commit_started)*1000)
        return usage

    async def reserve(self, kind):
        await self.update({"model": "model_calls", "tool": "tool_calls"}.get(kind, kind))
