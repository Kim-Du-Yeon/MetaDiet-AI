"""Small transaction pool exclusively for durable execution reservations."""
from contextlib import asynccontextmanager, nullcontext
import time
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from app.db.proposals import connection as direct_connection
from app.core.config import get_settings
from app.agents.execution_stream import emit_runtime_event

_pool = None


@asynccontextmanager
async def lifespan(url):
    global _pool
    async with AsyncConnectionPool(
        url, min_size=1, max_size=3, timeout=10, open=False,
        kwargs={'autocommit': False, 'row_factory': dict_row,
                'prepare_threshold': None, 'connect_timeout': 10},
        check=AsyncConnectionPool.check_connection,
    ) as pool:
        await pool.open(wait=True)
        _pool = pool
        try:
            yield
        finally:
            _pool = None


@asynccontextmanager
async def connection(*, pipeline: bool | None = None):
    # Offline eval/CLI retains the original transaction behavior.
    if _pool is None:
        async with direct_connection() as conn:
            yield conn
        return
    # Pool context commits/rolls back before release. Never use the
    # checkpointer's autocommit connection for SELECT FOR UPDATE reservations.
    started = time.perf_counter()
    async with _pool.connection() as conn:
        await emit_runtime_event('stage_timing', stage='budget_pool_checkout',
                                 elapsed_ms=(time.perf_counter()-started)*1000)
        enabled = get_settings().budget_pipeline if pipeline is None else pipeline
        # The pool commits only AFTER pipeline synchronization succeeds. A
        # queued UPDATE or failed sync must never count as a durable reservation.
        async with (conn.pipeline() if enabled else nullcontext()):
            setup_started = time.perf_counter()
            await conn.execute("set local statement_timeout = '15s'")
            await emit_runtime_event('stage_timing',
                stage='budget_setup_enqueue' if enabled else 'budget_setup',
                elapsed_ms=(time.perf_counter()-setup_started)*1000)
            yield conn
