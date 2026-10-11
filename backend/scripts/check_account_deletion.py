"""Verify account deletion against synthetic Supabase Auth and Postgres rows only."""
import asyncio
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

import psycopg
import jwt
from dotenv import load_dotenv
from supabase import create_client


if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
ARTIFACT = ROOT / "backend" / "artifacts" / "account-deletion-v1.json"


def _auth_exists(admin, auth_id: str) -> bool:
    try:
        admin.get_user_by_id(auth_id)
        return True
    except Exception as exc:
        status = getattr(exc, "status_code", None)
        if status == 404 or "not found" in str(exc).lower():
            return False
        raise


async def run() -> dict:
    load_dotenv(ROOT / "backend" / ".env")
    db_url = os.getenv("SUPABASE_DB_URL")
    if not db_url:
        raise RuntimeError("SUPABASE_DB_URL is required")

    from app.core.account_lifecycle import auth_id_hash
    from app.core.auth import validate_recent_auth_payload
    from app.db.account_deletion import AccountDeletionService
    from app.db.supabase_client import get_supabase

    admin = get_supabase().auth.admin
    # Never sign a user into the cached service-role client: sign-in replaces
    # its Authorization header and would make subsequent admin calls return 403.
    auth_client = create_client(
        os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"]
    )
    marker = uuid4().hex
    email = f"account-delete-{marker}@example.invalid"
    password = f"T!{marker}a9"
    created = admin.create_user({
        "email": email,
        "password": password,
        "email_confirm": True,
    })
    target_auth_id = str(created.user.id)
    signed_in = auth_client.auth.sign_in_with_password({"email": email, "password": password})
    access_token = signed_in.session.access_token
    claims = jwt.decode(access_token, options={"verify_signature": False})
    session_id = str(claims["session_id"])
    password_amr = any(
        item.get("method") == "password" and item.get("timestamp")
        for item in claims.get("amr") or []
    )
    if not password_amr:
        raise RuntimeError("Supabase password sign-in did not issue a password AMR timestamp")
    recent_context = validate_recent_auth_payload(claims)
    if recent_context.auth_id != target_auth_id or recent_context.session_id != session_id:
        raise RuntimeError("recent authentication context did not match the synthetic user session")
    control_auth_id = str(uuid4())
    target_user_id = None
    control_user_id = None
    target_thread = None
    control_thread = None

    try:
        with psycopg.connect(db_url) as conn:
            target_user_id = str(conn.execute(
                "insert into users(auth_id,name,goal) values(%s,%s,%s) returning id",
                (target_auth_id, "synthetic-delete-target", "maintain"),
            ).fetchone()[0])
            control_user_id = str(conn.execute(
                "insert into users(auth_id,name,goal) values(%s,%s,%s) returning id",
                (control_auth_id, "synthetic-delete-control", "maintain"),
            ).fetchone()[0])
            target_thread = f"{target_user_id}_delete-check"
            control_thread = f"{control_user_id}_delete-check"
            conn.execute(
                "insert into chat_history(user_id,thread_id,role,content) values(%s,%s,'user',%s)",
                (target_user_id, "delete-check", "synthetic account deletion fixture"),
            )
            conn.execute(
                "insert into chat_history(user_id,thread_id,role,content) values(%s,%s,'user',%s)",
                (control_user_id, "delete-check", "synthetic isolation fixture"),
            )
            for thread_id in (target_thread, control_thread):
                conn.execute(
                    """insert into checkpoints
                       (thread_id,checkpoint_ns,checkpoint_id,type,checkpoint,metadata)
                       values(%s,'','synthetic-checkpoint','json',%s::jsonb,%s::jsonb)""",
                    (thread_id, json.dumps({"v": 1}), json.dumps({"synthetic": True})),
                )

        result = await AccountDeletionService().delete(target_auth_id, session_id)

        with psycopg.connect(db_url) as conn:
            target_users = conn.execute(
                "select count(*) from users where auth_id=%s", (target_auth_id,)
            ).fetchone()[0]
            target_chats = conn.execute(
                "select count(*) from chat_history where user_id=%s", (target_user_id,)
            ).fetchone()[0]
            target_checkpoints = conn.execute(
                "select count(*) from checkpoints where thread_id=%s", (target_thread,)
            ).fetchone()[0]
            target_tombstones = conn.execute(
                "select count(*) from account_deletion_tombstones where auth_id_hash=%s",
                (auth_id_hash(target_auth_id),),
            ).fetchone()[0]
            control_users = conn.execute(
                "select count(*) from users where id=%s", (control_user_id,)
            ).fetchone()[0]
            control_chats = conn.execute(
                "select count(*) from chat_history where user_id=%s", (control_user_id,)
            ).fetchone()[0]
            control_checkpoints = conn.execute(
                "select count(*) from checkpoints where thread_id=%s", (control_thread,)
            ).fetchone()[0]

        summary = {
            "status": result["status"],
            "target": {
                "recent_password_auth": True,
                "active_session_validated": True,
                "auth_deleted": not _auth_exists(admin, target_auth_id),
                "user_rows": target_users,
                "chat_rows": target_chats,
                "checkpoint_rows": target_checkpoints,
                "tombstone_rows": target_tombstones,
            },
            "control": {
                "user_rows": control_users,
                "chat_rows": control_chats,
                "checkpoint_rows": control_checkpoints,
            },
        }
        expected = {
            "status": "deleted",
            "target": {
                "recent_password_auth": True,
                "active_session_validated": True,
                "auth_deleted": True,
                "user_rows": 0,
                "chat_rows": 0,
                "checkpoint_rows": 0,
                "tombstone_rows": 0,
            },
            "control": {"user_rows": 1, "chat_rows": 1, "checkpoint_rows": 1},
        }
        if summary != expected:
            raise AssertionError(f"account deletion verification mismatch: {summary}")
        ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
        ARTIFACT.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        return summary
    finally:
        with psycopg.connect(db_url) as conn:
            if target_thread:
                conn.execute("delete from checkpoints where thread_id=%s", (target_thread,))
            if control_thread:
                conn.execute("delete from checkpoints where thread_id=%s", (control_thread,))
            if target_user_id:
                conn.execute("delete from users where id=%s", (target_user_id,))
            if control_user_id:
                conn.execute("delete from users where id=%s", (control_user_id,))
        if _auth_exists(admin, target_auth_id):
            admin.delete_user(target_auth_id)


def main() -> None:
    print(json.dumps(asyncio.run(run()), ensure_ascii=False))


if __name__ == "__main__":
    main()
