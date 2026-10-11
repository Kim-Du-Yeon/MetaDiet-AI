"""Apply and verify the additive chat-history thread migration.

Credentials are loaded from backend/.env and are never printed.
"""
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
    migration = ROOT / "supabase" / "migrations" / "20261011120000_chat_history_thread_id.sql"
    with psycopg.connect(db_url) as connection:
        connection.execute(migration.read_text(encoding="utf-8"))
        column = connection.execute(
            """select is_nullable, column_default
               from information_schema.columns
               where table_schema = 'public' and table_name = 'chat_history'
                 and column_name = 'thread_id'"""
        ).fetchone()
        index_count = connection.execute(
            """select count(*) from pg_indexes
               where schemaname = 'public' and tablename = 'chat_history'
                 and indexname = 'idx_chat_history_user_thread'"""
        ).fetchone()[0]
        unclassified = connection.execute(
            "select count(*) from public.chat_history where thread_id is null or btrim(thread_id) = ''"
        ).fetchone()[0]
    print({"column": column, "index_count": index_count, "unclassified_rows": unclassified})


if __name__ == "__main__":
    main()
