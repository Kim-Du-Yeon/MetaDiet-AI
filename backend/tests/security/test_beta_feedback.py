from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID

import pytest


class Cursor:
    def __init__(self, row=None):
        self.row = row

    async def fetchone(self):
        return self.row


class FeedbackConnection:
    def __init__(self):
        self.queries = []
        self.row = {
            "id": UUID("11111111-1111-1111-1111-111111111111"),
            "rating": 5,
            "category": "answer_quality",
            "page": "settings",
            "created_at": __import__("datetime").datetime(2026, 10, 11, tzinfo=__import__("datetime").timezone.utc),
        }
        self.insert_returns_row = True

    async def execute(self, sql, params=()):
        normalized = " ".join(sql.split()).lower()
        self.queries.append((normalized, params))
        if normalized.startswith("insert into beta_feedback"):
            return Cursor(self.row if self.insert_returns_row else None)
        if normalized.startswith("select id, rating, category, page, created_at from beta_feedback"):
            return Cursor(self.row)
        return Cursor()


def connector(connection):
    @asynccontextmanager
    async def connect():
        yield connection

    return connect


@pytest.mark.asyncio
async def test_feedback_insert_uses_authenticated_user_and_fixed_page():
    from app.db.feedback import FeedbackInput, FeedbackRepository

    connection = FeedbackConnection()
    repository = FeedbackRepository(connect=connector(connection))
    submission = FeedbackInput(
        rating=5,
        category="answer_quality",
        comment="도움이 됐어요",
        client_submission_id=UUID("22222222-2222-2222-2222-222222222222"),
    )

    row, created = await repository.create("authenticated-user", submission)

    insert_sql, params = connection.queries[0]
    assert insert_sql.startswith("insert into beta_feedback")
    assert params == (
        "authenticated-user",
        5,
        "answer_quality",
        "도움이 됐어요",
        "settings",
        UUID("22222222-2222-2222-2222-222222222222"),
    )
    assert "email" not in insert_sql
    assert "message" not in insert_sql
    assert row["id"] == "11111111-1111-1111-1111-111111111111"
    assert created is True


@pytest.mark.asyncio
async def test_feedback_submission_is_idempotent_per_user():
    from app.db.feedback import FeedbackInput, FeedbackRepository

    connection = FeedbackConnection()
    connection.insert_returns_row = False
    repository = FeedbackRepository(connect=connector(connection))
    submission = FeedbackInput(
        rating=4,
        category="general",
        comment=None,
        client_submission_id=UUID("33333333-3333-3333-3333-333333333333"),
    )

    row, created = await repository.create("authenticated-user", submission)

    assert created is False
    assert row["id"] == "11111111-1111-1111-1111-111111111111"
    assert len(connection.queries) == 2
    assert connection.queries[1][1] == (
        "authenticated-user",
        UUID("33333333-3333-3333-3333-333333333333"),
    )


def test_feedback_migration_has_checks_rls_and_user_cascade():
    migration = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "migrations"
        / "add_beta_feedback.sql"
    ).read_text(encoding="utf-8").lower()

    assert "rating between 1 and 5" in migration
    assert "answer_quality" in migration and "usability" in migration and "bug" in migration
    assert "char_length(comment) <= 1000" in migration
    assert "unique (user_id, client_submission_id)" in migration
    assert "references public.users(id) on delete cascade" in migration
    assert "enable row level security" in migration
    assert "create policy" not in migration


@pytest.mark.asyncio
async def test_feedback_storage_error_redacts_comment():
    from app.db.feedback import FeedbackInput, FeedbackRepository, FeedbackStorageUnavailable

    secret_comment = "민감한 건강 피드백"

    @asynccontextmanager
    async def broken_connection():
        raise RuntimeError(f"database rejected {secret_comment}")
        yield

    repository = FeedbackRepository(connect=broken_connection)
    submission = FeedbackInput(
        rating=1,
        category="bug",
        comment=secret_comment,
        client_submission_id=UUID("44444444-4444-4444-4444-444444444444"),
    )

    with pytest.raises(FeedbackStorageUnavailable) as exc:
        await repository.create("authenticated-user", submission)

    assert secret_comment not in str(exc.value)
    assert "database rejected" not in str(exc.value)
