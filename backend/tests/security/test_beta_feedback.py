from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID

import pytest
from unittest.mock import AsyncMock


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


def valid_payload(**overrides):
    payload = {
        "rating": 5,
        "category": "general",
        "comment": "좋아요",
        "client_submission_id": "55555555-5555-5555-5555-555555555555",
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_feedback_requires_authentication(client):
    response = await client.post("/feedback", json=valid_payload())

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_feedback_uses_internal_user_not_request_identity(client, mock_current_user, monkeypatch):
    import app.api.routes.main as main_module

    repository = AsyncMock()
    repository.create.return_value = ({"id": "feedback-1"}, True)
    monkeypatch.setattr(main_module, "FeedbackRepository", lambda: repository)

    response = await client.post("/feedback", json=valid_payload())
    rejected = await client.post(
        "/feedback",
        json=valid_payload(user_id="attacker", page="other"),
    )

    assert response.status_code == 201
    assert response.json() == {"id": "feedback-1", "status": "stored", "created": True}
    assert rejected.status_code == 422
    user_id, submission = repository.create.await_args.args
    assert user_id == mock_current_user
    assert submission.comment == "좋아요"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "override",
    [
        {"rating": 0},
        {"rating": 6},
        {"category": "medical"},
        {"comment": "가" * 1001},
        {"client_submission_id": "not-a-uuid"},
    ],
)
async def test_feedback_validates_rating_category_and_comment(
    client, mock_current_user, monkeypatch, override
):
    import app.api.routes.main as main_module

    repository = AsyncMock()
    monkeypatch.setattr(main_module, "FeedbackRepository", lambda: repository)

    response = await client.post("/feedback", json=valid_payload(**override))

    assert response.status_code == 422
    repository.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_feedback_trims_blank_comment_to_none(client, mock_current_user, monkeypatch):
    import app.api.routes.main as main_module

    repository = AsyncMock()
    repository.create.return_value = ({"id": "feedback-2"}, True)
    monkeypatch.setattr(main_module, "FeedbackRepository", lambda: repository)

    response = await client.post("/feedback", json=valid_payload(comment="   \n"))

    assert response.status_code == 201
    assert repository.create.await_args.args[1].comment is None


@pytest.mark.asyncio
async def test_feedback_replay_returns_existing_id(client, mock_current_user, monkeypatch):
    import app.api.routes.main as main_module

    repository = AsyncMock()
    repository.create.return_value = ({"id": "feedback-existing"}, False)
    monkeypatch.setattr(main_module, "FeedbackRepository", lambda: repository)

    response = await client.post("/feedback", json=valid_payload())

    assert response.status_code == 200
    assert response.json() == {
        "id": "feedback-existing",
        "status": "stored",
        "created": False,
    }


@pytest.mark.asyncio
async def test_feedback_db_failure_returns_redacted_503(
    client, mock_current_user, monkeypatch, caplog
):
    import app.api.routes.main as main_module
    from app.db.feedback import FeedbackStorageUnavailable

    secret = "민감한 식사 및 건강 내용"
    repository = AsyncMock()
    repository.create.side_effect = FeedbackStorageUnavailable(secret)
    monkeypatch.setattr(main_module, "FeedbackRepository", lambda: repository)

    response = await client.post("/feedback", json=valid_payload(comment=secret))

    assert response.status_code == 503
    assert response.json() == {"detail": "피드백 저장 서비스를 잠시 사용할 수 없습니다."}
    assert secret not in response.text
    assert secret not in caplog.text
