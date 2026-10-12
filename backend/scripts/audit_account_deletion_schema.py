"""Inspect deletion-relevant schema metadata without reading user rows."""
import json
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    load_dotenv(ROOT / "backend" / ".env")
    db_url = os.getenv("SUPABASE_DB_URL")
    if not db_url:
        raise RuntimeError("SUPABASE_DB_URL is required")
    with psycopg.connect(db_url) as connection:
        checkpoint_columns = connection.execute(
            """select table_name,
                      json_agg(json_build_object('name', column_name,
                                                 'type', data_type,
                                                 'nullable', is_nullable,
                                                 'default', column_default)
                               order by ordinal_position)
               from information_schema.columns
               where table_schema = 'public' and table_name like 'checkpoint%'
               group by table_name order by table_name"""
        ).fetchall()
        users_columns = connection.execute(
            """select column_name, data_type, is_nullable, column_default
               from information_schema.columns
               where table_schema = 'public' and table_name = 'users'
               order by ordinal_position"""
        ).fetchall()
        user_fks = connection.execute(
            """select tc.table_name, kcu.column_name, rc.delete_rule
               from information_schema.table_constraints tc
               join information_schema.key_column_usage kcu
                 on tc.constraint_name = kcu.constraint_name and tc.constraint_schema = kcu.constraint_schema
               join information_schema.referential_constraints rc
                 on tc.constraint_name = rc.constraint_name and tc.constraint_schema = rc.constraint_schema
               join information_schema.constraint_column_usage ccu
                 on rc.unique_constraint_name = ccu.constraint_name and rc.unique_constraint_schema = ccu.constraint_schema
               where tc.constraint_type = 'FOREIGN KEY' and tc.table_schema = 'public'
                 and ccu.table_name = 'users' and ccu.column_name = 'id'
               order by tc.table_name"""
        ).fetchall()
        protected_tables = connection.execute(
            """select c.relname, c.relrowsecurity
               from pg_class c
               join pg_namespace n on n.oid = c.relnamespace
               where n.nspname = 'public'
                 and c.relname in ('beta_feedback', 'product_events')"""
        ).fetchall()
        idempotency_constraints = connection.execute(
            """select t.relname, pg_get_constraintdef(c.oid)
               from pg_constraint c
               join pg_class t on t.oid = c.conrelid
               join pg_namespace n on n.oid = t.relnamespace
               where n.nspname = 'public'
                 and t.relname in ('beta_feedback', 'product_events') and c.contype = 'u'"""
        ).fetchall()
    table_security = {row[0]: bool(row[1]) for row in protected_tables}
    constraint_text = {row[0]: row[1] for row in idempotency_constraints}
    for table, key in (("beta_feedback", "client_submission_id"), ("product_events", "client_event_id")):
        if not table_security.get(table):
            raise RuntimeError(f"{table} table is missing or RLS is disabled")
        if not any(row[0] == table and row[1] == "user_id" and row[2] == "CASCADE" for row in user_fks):
            raise RuntimeError(f"{table}.user_id must cascade when users.id is deleted")
        if key not in constraint_text.get(table, ""):
            raise RuntimeError(f"{table} idempotency constraint is missing")
    print(json.dumps({
        "checkpoint_tables": [{"table": row[0], "columns": row[1]} for row in checkpoint_columns],
        "users_columns": [
            {"name": row[0], "type": row[1], "nullable": row[2], "default": row[3]}
            for row in users_columns
        ],
        "user_foreign_keys": [
            {"table": row[0], "column": row[1], "delete_rule": row[2]} for row in user_fks
        ],
        "beta_feedback": {
            "rls_enabled": table_security["beta_feedback"],
            "user_delete_cascade": True,
            "idempotency_unique": True,
        },
        "product_events": {
            "rls_enabled": table_security["product_events"],
            "user_delete_cascade": True,
            "idempotency_unique": True,
        },
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
