"""Local-container-only concurrent confirmation and checkpoint pool verification."""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
import sys
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from psycopg import AsyncConnection, sql
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from app.db.proposals import ProposalRepository

BASE = "postgresql://postgres@127.0.0.1:55439/"


async def main():
    name = "metadiet_test_" + uuid4().hex
    async with await AsyncConnection.connect(BASE + "postgres", autocommit=True) as admin:
        await admin.execute(sql.SQL("create database {}").format(sql.Identifier(name)))
        try:
            url = BASE + name
            async with await AsyncConnection.connect(url) as conn:
                for role in ("anon", "authenticated", "service_role"):
                    await conn.execute(sql.SQL("do $$ begin create role {}; exception when duplicate_object then null; end $$").format(sql.Identifier(role)))
                await conn.execute("create schema auth; create function auth.uid() returns uuid language sql as 'select null::uuid'")
                root = Path(__file__).resolve().parents[2]
                await conn.execute((root / "backend/app/db/schema.sql").read_text(encoding="utf-8"))
                await conn.execute("alter table meal_logs add column sodium_mg float default 0, add column source text default 'csv'")
                await conn.execute((root / "supabase/migrations/20261008233749_agent_proposals.sql").read_text(encoding="utf-8"))
                user = str(uuid4())
                await conn.execute("insert into users(id,auth_id,name,goal) values(%s,%s,'synthetic','maintain')", (user, uuid4()))
            @asynccontextmanager
            async def connect():
                async with await AsyncConnection.connect(url, row_factory=dict_row) as connection:
                    yield connection
            repo = ProposalRepository(connect)
            proposal = await repo.create(user, "concurrent", {"kind": "intake", "log_date": "2026-10-09", "meals": [{
                "food_name": "fixture", "meal_type": "lunch", "quantity_g": 100, "calories": 100,
                "protein_g": 5, "carbs_g": 15, "fat_g": 2}]}, "concurrent-1")
            results = await asyncio.gather(*(repo.resolve(user, proposal["id"], proposal["version"], "confirm") for _ in range(4)))
            assert all(item["status"] == "confirmed" for item in results)
            async with connect() as conn:
                count = await (await conn.execute("select count(*) as n from meal_logs where user_id=%s", (user,))).fetchone()
                assert count["n"] == 1
            async with AsyncConnectionPool(url, min_size=1, max_size=3, kwargs={"autocommit": True, "prepare_threshold": 0}, open=False) as pool:
                await pool.open(wait=True)
                saver = AsyncPostgresSaver(pool)
                await saver.setup()
                assert await saver.aget_tuple({"configurable": {"thread_id": "synthetic"}}) is None
            print("PASS: four concurrent confirmations produce one row; pooled checkpointer initializes and reads")
        finally:
            await admin.execute(sql.SQL("drop database {} with (force)").format(sql.Identifier(name)))
            print("Removed isolated synthetic test database")


if __name__ == "__main__":
    asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop if sys.platform == "win32" else None)
