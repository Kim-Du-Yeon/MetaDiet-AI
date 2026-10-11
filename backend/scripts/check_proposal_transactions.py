"""Exercise real Postgres proposal transactions; always rollback synthetic data/DDL."""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
import sys
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from psycopg import AsyncConnection, Rollback, sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from app.core.config import get_settings
from app.db.proposals import ProposalRepository, ProposalConflict
from app.core.energy_policy import EnergyInputs
from app.core.onboarding import baseline_payload
from app.core.service_clock import service_today


async def main():
    local = "--local" in sys.argv
    url = "postgresql://postgres@127.0.0.1:55439/postgres" if local else get_settings().supabase_db_url
    async with await AsyncConnection.connect(url, row_factory=dict_row, connect_timeout=10) as conn:
        async with conn.transaction():
            await conn.execute("set local statement_timeout='15s'")
            if local:
                for role in ("anon", "authenticated", "service_role"):
                    await conn.execute(sql.SQL("do $$ begin create role {}; exception when duplicate_object then null; end $$").format(sql.Identifier(role)))
                await conn.execute("create schema auth; create function auth.uid() returns uuid language sql as 'select null::uuid'")
                schema = Path(__file__).resolve().parents[1] / "app/db/schema.sql"
                await conn.execute(schema.read_text(encoding="utf-8"))
                await conn.execute("alter table meal_logs add column sodium_mg float default 0, add column source text default 'csv'")
            repository_root = Path(__file__).resolve().parents[2]
            migration = repository_root / "supabase/migrations/20261008233749_agent_proposals.sql"
            if not migration.is_file():
                migration = Path(__file__).resolve().parents[1] / "migrations/20261008233749_agent_proposals.sql"
            await conn.execute(migration.read_text(encoding="utf-8"))
            user_id = str(uuid4())
            energy = EnergyInputs(age=30, sex="male", weight_kg=70, height_cm=170,
                                  activity="low_active", general_adult_confirmed=True)
            profile = {**energy.model_dump(), "gender": energy.sex, "goal": "maintain", "region": "KR",
                       "nutrition_policy_context": energy.model_dump()}
            await conn.execute(
                "insert into users(id,auth_id,name,goal,height_cm,age,weight_kg,region,nutrition_policy_context) "
                "values(%s,%s,'synthetic transaction test','maintain',%s,%s,%s,%s,%s)",
                (user_id, uuid4(), profile["height_cm"], profile["age"], profile["weight_kg"],
                 profile["region"], Jsonb(profile["nutrition_policy_context"])),
            )

            @asynccontextmanager
            async def connect():
                async with conn.transaction():
                    yield conn

            repo = ProposalRepository(connect)
            payload = {"kind": "plan", "log_date": "2026-10-09", "meals": [
                {"food_name": "synthetic", "quantity_g": 100, "meal_type": "lunch", "calories": 100,
                 "protein_g": 5, "carbs_g": 15, "fat_g": 2, "source": "csv"}]}
            proposal = await repo.create(user_id, "test", payload, "plan-1")
            await repo.resolve(user_id, proposal["id"], proposal["version"], "confirm")
            await repo.resolve(user_id, proposal["id"], proposal["version"], "confirm")
            row = await (await conn.execute("select count(*) as n from meal_logs where user_id=%s", (user_id,))).fetchone()
            assert row["n"] == 0, "Plan must not increase intake"
            row = await (await conn.execute("select count(*) as n from meal_plans where user_id=%s", (user_id,))).fetchone()
            assert row["n"] == 1, "Duplicate approval must be idempotent"
            intake = await repo.create(user_id, "test", {**payload, "kind": "intake"}, "intake-1")
            newer = await repo.create(user_id, "test", {**payload, "kind": "intake"}, "intake-2")
            try:
                await repo.resolve(user_id, intake["id"], intake["version"], "confirm")
                raise AssertionError("Superseded proposal must be rejected")
            except ProposalConflict:
                pass
            try:
                await repo.resolve(str(uuid4()), newer["id"], newer["version"], "confirm")
                raise AssertionError("Other user must be rejected")
            except ProposalConflict:
                pass
            await repo.resolve(user_id, newer["id"], newer["version"], "confirm")
            row = await (await conn.execute("select count(*) as n from meal_logs where user_id=%s", (user_id,))).fetchone()
            assert row["n"] == 1
            failed = await repo.create(user_id, "failure", {**payload, "kind": "intake", "meals": payload["meals"] * 2}, "rollback-case")
            class FailingRepository(ProposalRepository):
                async def _apply(self, connection, user, proposal, body):
                    await super()._apply(connection, user, proposal, body)
                    raise RuntimeError("synthetic failure before proposal commit")
            try:
                await FailingRepository(connect).resolve(user_id, failed["id"], failed["version"], "confirm")
                raise AssertionError("Failure must propagate")
            except RuntimeError:
                pass
            count = await (await conn.execute("select count(*) as n from meal_logs where user_id=%s", (user_id,))).fetchone()
            assert count["n"] == 1, "Partial meal insert must rollback"
            assert (await repo.get(user_id, failed["id"]))["status"] == "pending"
            strategy = baseline_payload(profile, None)
            strategy.update({"kind": "strategy", "effective_date": service_today().isoformat(),
                             "based_on_strategy_id": None})
            draft = await repo.create(user_id, "strategy", strategy, "strategy-1")
            applied = await repo.resolve(user_id, draft["id"], draft["version"], "confirm")
            strategy["based_on_strategy_id"] = applied["result"]["strategy_id"]
            draft2 = await repo.create(user_id, "strategy", strategy, "strategy-2")
            try:
                await FailingRepository(connect).resolve(user_id, draft2["id"], draft2["version"], "confirm")
            except RuntimeError:
                pass
            active = await (await conn.execute("select id from diet_strategies where user_id=%s and is_active", (user_id,))).fetchall()
            assert len(active) == 1 and str(active[0]["id"]) == strategy["based_on_strategy_id"]
            meal = await (await conn.execute("select id,calories from meal_logs where user_id=%s", (user_id,))).fetchone()
            edit = await repo.create(user_id, "edit", {"kind": "meal_replace", "meal_id": str(meal["id"]),
                "expected": {"calories": meal["calories"]}, "meal": {**payload["meals"][0], "calories": 200}}, "edit-1")
            await repo.resolve(user_id, edit["id"], edit["version"], "confirm")
            stale = await repo.create(user_id, "delete", {"kind": "meal_delete", "meal_id": str(meal["id"]),
                "expected": {"calories": 100}}, "delete-stale")
            try:
                await repo.resolve(user_id, stale["id"], stale["version"], "confirm")
                raise AssertionError("Changed meal must reject stale deletion")
            except ProposalConflict:
                pass
            deletion = await repo.create(user_id, "delete", {"kind": "meal_delete", "meal_id": str(meal["id"]),
                "expected": {"calories": 200}}, "delete-current")
            await repo.resolve(user_id, deletion["id"], deletion["version"], "confirm")
            assert not await (await conn.execute("select id from meal_logs where user_id=%s", (user_id,))).fetchall()
            print("PASS: plan/intake, idempotency, stale version, ownership, intake rollback, atomic strategy rollback, replacement and stale deletion")
            raise Rollback()
    print("Rolled back all synthetic data and migration DDL")


if __name__ == "__main__":
    try:
        asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop if sys.platform == "win32" else None)
    except Exception as exc:
        print(f"Transaction verification failed: {type(exc).__name__} (credentials and query values omitted)")
        sys.exit(1)
