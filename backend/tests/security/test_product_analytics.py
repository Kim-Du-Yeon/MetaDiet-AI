from contextlib import asynccontextmanager
import json
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from fastapi import HTTPException


class Cursor:
    def __init__(self, row=None):
        self.row = row

    async def fetchone(self):
        return self.row


class AnalyticsConnection:
    def __init__(self):
        self.queries = []
        self.insert_returns_row = True

    async def execute(self, sql, params=()):
        normalized = " ".join(sql.split()).lower()
        self.queries.append((normalized, params))
        if normalized.startswith("insert into product_events"):
            row = {"id": UUID("11111111-1111-1111-1111-111111111111")} if self.insert_returns_row else None
            return Cursor(row)
        if normalized.startswith("select id from product_events"):
            return Cursor({"id": UUID("11111111-1111-1111-1111-111111111111")})
        if "count(distinct user_id) filter" in normalized:
            return Cursor({
                "dau": 3, "wau": 8, "signups": 10, "onboarding_completed": 8,
                "first_meal_users": 5, "chat_total": 20, "chat_succeeded": 18,
                "latency_p50_ms": 900, "latency_p95_ms": 2400, "errors": 2,
            })
        return Cursor()


def connector(connection):
    @asynccontextmanager
    async def connect():
        yield connection
    return connect


@pytest.mark.asyncio
async def test_event_storage_is_idempotent_and_privacy_minimal():
    from app.db.analytics import ProductEventInput, ProductEventRepository

    connection = AnalyticsConnection()
    repository = ProductEventRepository(connect=connector(connection))
    event = ProductEventInput(
        event_name="onboarding_completed",
        status="success",
        client_event_id=UUID("22222222-2222-2222-2222-222222222222"),
        session_id=UUID("33333333-3333-3333-3333-333333333333"),
        duration_ms=1200,
        trace_id="trace-safe",
        properties={"source": "web"},
    )

    row, created = await repository.record("authenticated-user", event)

    sql, params = connection.queries[0]
    assert created is True
    assert row["id"] == "11111111-1111-1111-1111-111111111111"
    assert "on conflict (user_id, client_event_id) do nothing" in sql
    assert "message" not in sql and "weight" not in sql and "email" not in sql
    assert json.loads(params[-1]) == {"source": "web"}


@pytest.mark.asyncio
async def test_overview_returns_counts_rates_and_latency():
    from app.db.analytics import ProductEventRepository

    connection = AnalyticsConnection()
    repository = ProductEventRepository(connect=connector(connection))
    result = await repository.overview(days=7)

    assert result["active_users"] == {"daily": 3, "weekly": 8}
    assert result["funnel"]["onboarding_rate"] == 0.8
    assert result["funnel"]["first_meal_rate"] == 0.5
    assert result["agent"]["success_rate"] == 0.9
    assert result["agent"]["latency_p95_ms"] == 2400
    sql, params = connection.queries[0]
    assert "from auth.users" in sql
    assert "greatest(%s, 7)" in sql
    assert "event_name='chat_completed' and status='failed'" in sql
    assert params == (7,) * 7


def test_product_events_migration_is_private_indexed_and_constrained():
    migration = (
        Path(__file__).resolve().parents[2]
        / "scripts" / "migrations" / "add_product_events.sql"
    ).read_text(encoding="utf-8").lower()

    assert "create table if not exists public.product_events" in migration
    assert "references public.users(id) on delete cascade" in migration
    assert "unique (user_id, client_event_id)" in migration
    assert "enable row level security" in migration
    assert "revoke all on table public.product_events from anon, authenticated" in migration
    assert "create policy" not in migration
    assert "event_name, created_at desc" in migration
    assert "user_id, created_at desc" in migration


def valid_event(**overrides):
    payload = {
        "event_name": "onboarding_completed",
        "status": "success",
        "client_event_id": "44444444-4444-4444-4444-444444444444",
        "session_id": "55555555-5555-5555-5555-555555555555",
        "duration_ms": 950,
        "properties": {"source": "web"},
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_event_endpoint_uses_authenticated_internal_user(client, mock_current_user, monkeypatch):
    import app.api.routes.main as main_module

    repository = AsyncMock()
    repository.record.return_value = ({"id": "event-1"}, True)
    monkeypatch.setattr(main_module, "ProductEventRepository", lambda: repository)

    response = await client.post("/analytics/events", json=valid_event())

    assert response.status_code == 201
    assert response.json() == {"id": "event-1", "created": True}
    assert repository.record.await_args.args[0] == mock_current_user


@pytest.mark.asyncio
async def test_event_endpoint_rejects_payload_content_and_unknown_events(client, mock_current_user):
    response = await client.post(
        "/analytics/events",
        json=valid_event(event_name="meal_text", properties={"message": "민감한 식사 내용"}),
    )
    assert response.status_code == 422

    sensitive = await client.post('/analytics/events', json=valid_event(
        properties={'source': 'private health information'}))
    assert sensitive.status_code == 422


@pytest.mark.asyncio
async def test_admin_overview_requires_admin_dependency(client, monkeypatch):
    import app.api.routes.main as main_module
    from app.core.auth import get_current_admin

    repository = AsyncMock()
    repository.overview.return_value = {"active_users": {"daily": 1, "weekly": 2}}
    monkeypatch.setattr(main_module, "ProductEventRepository", lambda: repository)

    denied = await client.get("/admin/analytics/overview")
    assert denied.status_code == 401

    main_module.app.dependency_overrides[get_current_admin] = lambda: "admin-auth-id"
    try:
        allowed = await client.get("/admin/analytics/overview?days=7")
    finally:
        main_module.app.dependency_overrides.pop(get_current_admin, None)
    assert allowed.status_code == 200
    repository.overview.assert_awaited_once_with(days=7)


def test_admin_authorization_uses_verified_top_level_email_only(monkeypatch):
    import app.core.auth as auth_module

    monkeypatch.setattr(auth_module, "_decode_verified_token", lambda _token: {
        "sub": "auth-user", "email": "owner@example.com",
        "user_metadata": {"email": "attacker@example.com", "role": "admin"},
    })
    monkeypatch.setattr(auth_module, "get_settings", lambda: type("Settings", (), {
        "admin_emails": "owner@example.com"
    })())
    assert auth_module.get_current_admin("verified-token") == "auth-user"

    monkeypatch.setattr(auth_module, "_decode_verified_token", lambda _token: {
        "sub": "auth-user", "email": "member@example.com",
        "user_metadata": {"email": "owner@example.com", "role": "admin"},
    })
    with pytest.raises(HTTPException) as error:
        auth_module.get_current_admin("verified-token")
    assert error.value.status_code == 403
