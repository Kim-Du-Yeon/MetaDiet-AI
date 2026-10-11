"""Durable proposals; approval and all resulting writes share one SQL transaction."""
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from uuid import uuid4

from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from app.core.config import get_settings
from app.core.service_clock import service_today
from app.schemas.proposals import payload_adapter


class ProposalConflict(ValueError):
    pass


@asynccontextmanager
async def connection():
    async with await AsyncConnection.connect(get_settings().supabase_db_url, row_factory=dict_row,
                                            connect_timeout=10) as conn:
        await conn.execute("set local statement_timeout = '15s'")
        yield conn


class ProposalRepository:
    def __init__(self, connect=connection):
        self.connect = connect

    async def create(self, user_id: str, thread_id: str, payload: dict, dedupe_key: str, *, replaces=None) -> dict:
        payload = payload_adapter.validate_python(payload).model_dump(mode="json")
        async with self.connect() as conn:
            await conn.execute("select id from users where id=%s for update", (user_id,))
            previous = await (await conn.execute(
                "select * from agent_proposals where user_id=%s and dedupe_key=%s", (user_id, dedupe_key))).fetchone()
            if previous:
                if previous["payload"] != payload:
                    raise ProposalConflict("같은 요청 ID에 다른 내용이 전달됐습니다.")
                return self.public(previous)
            if replaces:
                old = await (await conn.execute("select id from agent_proposals where user_id=%s and id=%s and version=%s and status='pending' for update",
                    (user_id, replaces[0], replaces[1]))).fetchone()
                if not old:
                    raise ProposalConflict("수정하려는 제안이 이미 변경되었습니다.")
            row = await (await conn.execute(
                "select coalesce(max(version),0)+1 as version from agent_proposals where user_id=%s and thread_id=%s",
                (user_id, thread_id))).fetchone()
            await conn.execute("update agent_proposals set status='superseded' where user_id=%s and thread_id=%s and status='pending'",
                               (user_id, thread_id))
            result = await (await conn.execute(
                "insert into agent_proposals(id,user_id,thread_id,version,kind,payload,dedupe_key) values(%s,%s,%s,%s,%s,%s,%s) returning *",
                (uuid4(), user_id, thread_id, row["version"], payload["kind"], Jsonb(payload), dedupe_key))).fetchone()
            return self.public(result)

    async def get(self, user_id: str, proposal_id: str) -> dict:
        async with self.connect() as conn:
            row = await (await conn.execute("select * from agent_proposals where user_id=%s and id=%s",
                                           (user_id, proposal_id))).fetchone()
            if not row:
                raise ProposalConflict("제안을 찾을 수 없습니다.")
            return self.public(row)

    async def resolve(self, user_id: str, proposal_id: str, version: int, action: str) -> dict:
        if action not in {"confirm", "cancel"}:
            raise ProposalConflict("명시적 확인 또는 취소가 필요합니다.")
        async with self.connect() as conn:
            await conn.execute("select id from users where id=%s for update", (user_id,))
            row = await (await conn.execute("select * from agent_proposals where id=%s and user_id=%s for update",
                                           (proposal_id, user_id))).fetchone()
            if not row or row["version"] != version:
                raise ProposalConflict("제안이 없거나 버전이 변경되었습니다.")
            target = "confirmed" if action == "confirm" else "cancelled"
            if row["status"] == target:
                return self.public(row)  # duplicate click/network retry
            if row["status"] != "pending" or row["expires_at"] <= datetime.now(timezone.utc):
                raise ProposalConflict("오래되었거나 이미 처리된 제안입니다.")
            payload = payload_adapter.validate_python(row["payload"]).model_dump(mode="json")
            result = await self._apply(conn, user_id, row, payload) if action == "confirm" else {}
            saved = await (await conn.execute(
                "update agent_proposals set status=%s,result=%s,resolved_at=now() where id=%s returning *",
                (target, Jsonb(result), proposal_id))).fetchone()
            return self.public(saved)

    async def _apply(self, conn, user_id, proposal, payload):
        kind = payload["kind"]
        if kind in {"meal_delete", "meal_replace"}:
            current = await (await conn.execute("select id,food_name,meal_type,quantity_g,calories,protein_g,carbs_g,fat_g from meal_logs where id=%s and user_id=%s for update",
                (payload["meal_id"], user_id))).fetchone()
            expected = payload["expected"]
            if not current or any(current.get(k) != v for k, v in expected.items()):
                raise ProposalConflict("기록이 변경되었거나 삭제되었습니다. 다시 조회해주세요.")
            if kind == "meal_delete":
                await conn.execute("delete from meal_logs where id=%s and user_id=%s", (payload["meal_id"], user_id))
            else:
                meal = payload["meal"]
                await conn.execute("update meal_logs set food_name=%s,meal_type=%s,quantity_g=%s,calories=%s,protein_g=%s,carbs_g=%s,fat_g=%s,sodium_mg=%s,source=%s where id=%s and user_id=%s",
                    (*(meal[k] for k in ("food_name", "meal_type", "quantity_g", "calories", "protein_g", "carbs_g", "fat_g", "sodium_mg", "source")), payload["meal_id"], user_id))
            return {"meal_id": payload["meal_id"], "action": kind}
        if kind == "plan":
            row = await (await conn.execute(
                "insert into meal_plans(user_id,proposal_id,plan_date,meals) values(%s,%s,%s,%s) returning id",
                (user_id, proposal["id"], payload["log_date"], Jsonb(payload["meals"])))).fetchone()
            return {"plan_id": str(row["id"])}
        if kind == "intake":
            ids = []
            for meal in payload["meals"]:
                row = await (await conn.execute(
                    "insert into meal_logs(user_id,log_date,meal_type,food_name,quantity_g,calories,protein_g,carbs_g,fat_g,sodium_mg,source) "
                    "values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) returning id",
                    (user_id, payload["log_date"], meal["meal_type"], meal["food_name"], meal["quantity_g"],
                     meal["calories"], meal["protein_g"], meal["carbs_g"], meal["fat_g"], meal["sodium_mg"], meal["source"])) ).fetchone()
                ids.append(str(row["id"]))
            return {"meal_ids": ids}
        if kind == "measurement":
            row = await (await conn.execute(
                "insert into inbody_logs(user_id,measured_date,weight_kg,skeletal_muscle_kg,body_fat_kg,body_fat_pct,bmi,bmr_kcal,protein_kg,mineral_kg) "
                "values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) returning id",
                (user_id, *(payload[k] for k in ("measured_date", "weight_kg", "skeletal_muscle_kg", "body_fat_kg",
                 "body_fat_pct", "bmi", "bmr_kcal", "protein_kg", "mineral_kg"))))).fetchone()
            return {"measurement_id": str(row["id"])}
        if payload["effective_date"] != service_today().isoformat():
            raise ProposalConflict("전략 적용일을 오늘로 다시 확인해주세요.")
        from app.rag.strategy_evidence import evaluate_strategy, load_claims
        profile = await (await conn.execute('select * from users where id=%s', (user_id,))).fetchone()
        try:
            receipt = evaluate_strategy(payload, profile or {}, load_claims())
            if payload.get('evidence_policy') != receipt or payload['policy_version'] != receipt['policy_version']:
                raise ValueError('Evidence policy changed since proposal')
        except (ValueError, OSError, KeyError, TypeError):
            raise ProposalConflict('근거 정책이 미확정이거나 변경되었습니다. 전략 변경을 보류합니다.') from None
        active = await (await conn.execute("select id from diet_strategies where user_id=%s and is_active=true order by created_at desc limit 1",
                                          (user_id,))).fetchone()
        if (str(active["id"]) if active else None) != payload["based_on_strategy_id"]:
            raise ProposalConflict("현재 전략이 변경되었습니다. 새 전략을 다시 검토해주세요.")
        await conn.execute("update diet_strategies set is_active=false where user_id=%s and is_active=true", (user_id,))
        row = await (await conn.execute(
            "insert into diet_strategies(user_id,daily_calories,protein_g,carbs_g,fat_g,strategy_note,triggered_by,is_active) "
            "values(%s,%s,%s,%s,%s,%s,'confirmed_proposal',true) returning id",
            (user_id, *(payload[k] for k in ("daily_calories", "protein_g", "carbs_g", "fat_g", "strategy_note"))))).fetchone()
        await conn.execute(
            "insert into strategy_versions(user_id,proposal_id,strategy_id,version,evidence,policy_version,effective_date) "
            "select %s,%s,%s,coalesce(max(version),0)+1,%s,%s,%s from strategy_versions where user_id=%s",
            (user_id, proposal["id"], row["id"], Jsonb(payload["evidence"]), payload["policy_version"], payload["effective_date"], user_id))
        return {"strategy_id": str(row["id"])}

    @staticmethod
    def public(row):
        return {"id": str(row["id"]), "version": row["version"], "kind": row["kind"],
                "thread_id": row["thread_id"],
                "payload": row["payload"], "status": row["status"], "result": row.get("result"),
                "expires_at": row["expires_at"].isoformat()}
