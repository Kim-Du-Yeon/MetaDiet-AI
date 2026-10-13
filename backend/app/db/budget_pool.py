"""Small transaction pool exclusively for durable execution reservations."""
from contextlib import asynccontextmanager
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from app.db.proposals import connection as direct_connection

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
async def connection():
    # Offline eval/CLI retains the original transaction behavior.
    if _pool is None:
        async with direct_connection() as conn:
            yield conn
        return
    # Pool context commits/rolls back before release. Never use the
    # checkpointer's autocommit connection for SELECT FOR UPDATE reservations.
    async with _pool.connection() as conn:
        await conn.execute("set local statement_timeout = '15s'")
        yield conn
