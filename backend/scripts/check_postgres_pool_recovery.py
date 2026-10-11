"""Read-only concurrency and cancellation recovery check for the checkpoint pool."""
import asyncio
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from psycopg_pool import AsyncConnectionPool


def backend_dir(script_path: Path) -> Path:
    return script_path.resolve().parent.parent


BACKEND = backend_dir(Path(__file__))
OUTPUT = BACKEND / "artifacts" / "postgres-pool-recovery-v1.json"


async def scalar(pool, sql: str):
    async with pool.connection() as connection:
        async with connection.cursor() as cursor:
            await cursor.execute(sql)
            row = await cursor.fetchone()
            return row[-1]


async def main() -> None:
    load_dotenv(BACKEND / ".env")
    db_url = os.getenv("SUPABASE_DB_URL")
    if not db_url:
        raise RuntimeError("SUPABASE_DB_URL is required")
    started = time.perf_counter()
    async with AsyncConnectionPool(
        db_url, min_size=1, max_size=10, timeout=15,
        kwargs={"autocommit": True, "prepare_threshold": 0}, open=False,
    ) as pool:
        await pool.open(wait=True)
        concurrent_started = time.perf_counter()
        values = await asyncio.wait_for(
            asyncio.gather(*(scalar(pool, "select pg_sleep(0.05), 1") for _ in range(20))),
            timeout=15,
        )
        concurrent_seconds = time.perf_counter() - concurrent_started

        async def interrupted_query():
            return await scalar(pool, "select pg_sleep(10), 1")

        task = asyncio.create_task(interrupted_query())
        await asyncio.sleep(0.2)
        task.cancel()
        cancelled = False
        try:
            await task
        except asyncio.CancelledError:
            cancelled = True

        recovery_started = time.perf_counter()
        recovered_value = await asyncio.wait_for(scalar(pool, "select 1"), timeout=5)
        recovery_seconds = time.perf_counter() - recovery_started
        stats = pool.get_stats()

    report = {
        "experiment": "postgres-pool-recovery-v1",
        "workload": {"concurrent_reads": 20, "all_results_valid": values == [1] * 20},
        "pool": {"min_size": 1, "max_size": 10, "timeout_seconds": 15},
        "cancellation": {"cancelled": cancelled, "subsequent_query_value": recovered_value},
        "timing": {
            "concurrent_seconds": round(concurrent_seconds, 4),
            "recovery_seconds": round(recovery_seconds, 4),
            "total_seconds": round(time.perf_counter() - started, 4),
        },
        "pool_stats": {key: value for key, value in stats.items() if isinstance(value, (int, float))},
        "contains_user_data": False,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
