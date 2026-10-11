from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest


class Cursor:
    def __init__(self, row=None, rowcount=0):
        self.row = row
        self.rowcount = rowcount

    async def fetchone(self):
        return self.row


class Connection:
    def __init__(self, *, fail_on=None):
        self.queries = []
        self.fail_on = fail_on

    async def execute(self, sql, params=()):
        normalized = " ".join(sql.split()).lower()
        self.queries.append((normalized, params))
        if self.fail_on and self.fail_on in normalized:
            raise ConnectionError("injected database failure")
        if normalized.startswith("select id from users"):
            return Cursor({"id": "11111111-1111-1111-1111-111111111111"})
        if normalized.startswith("select 1 from auth.sessions"):
            return Cursor({"exists": 1})
        return Cursor(rowcount=1)


def connector(connection, lifecycle):
    @asynccontextmanager
    async def connect():
        lifecycle.append("begin")
        try:
            yield connection
        except Exception:
            lifecycle.append("rollback")
            raise
        else:
            lifecycle.append("commit")
    return connect


@pytest.mark.asyncio
async def test_account_deletion_removes_checkpoint_prefix_then_cascades_user():
    from app.db.account_deletion import AccountDeletionService

    lifecycle = []
    connection = Connection()
    auth_delete = AsyncMock()
    service = AccountDeletionService(connect=connector(connection, lifecycle), delete_auth=auth_delete)

    result = await service.delete(
        "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
    )

    sql = [query for query, _ in connection.queries]
    tombstone_insert = (
        "insert into account_deletion_tombstones(auth_id_hash) values(%s) "
        "on conflict(auth_id_hash) do nothing"
    )
    assert tombstone_insert in sql
    user_lock = "select pg_advisory_xact_lock(hashtextextended(%s,0))"
    assert user_lock in sql
    user_lock_index = next(
        index
        for index, (query, params) in enumerate(connection.queries)
        if query == user_lock
        and params == ("account:11111111-1111-1111-1111-111111111111",)
    )
    assert user_lock_index < sql.index(
        "delete from checkpoint_writes where thread_id like %s escape '\\'"
    )
    assert sql.index("delete from checkpoint_writes where thread_id like %s escape '\\'") < sql.index(
        "delete from users where id=%s")
    assert "delete from checkpoint_blobs where thread_id like %s escape '\\'" in sql
    assert "delete from checkpoints where thread_id like %s escape '\\'" in sql
    assert not any("delete from beta_feedback" in query for query in sql)
    assert lifecycle == ["begin", "commit", "begin", "commit"]
    auth_delete.assert_awaited_once_with("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    assert "delete from account_deletion_tombstones where auth_id_hash=%s" in sql
    assert result["status"] == "deleted"


@pytest.mark.asyncio
async def test_database_failure_rolls_back_and_never_deletes_auth_identity():
    from app.db.account_deletion import AccountDeletionService

    lifecycle = []
    connection = Connection(fail_on="checkpoint_blobs")
    auth_delete = AsyncMock()
    service = AccountDeletionService(connect=connector(connection, lifecycle), delete_auth=auth_delete)

    with pytest.raises(ConnectionError):
        await service.delete(
            "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        )

    assert lifecycle == ["begin", "rollback"]
    auth_delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_auth_failure_is_retryable_after_application_data_is_deleted():
    from app.db.account_deletion import AccountDeletionPartialFailure, AccountDeletionService

    lifecycle = []
    connection = Connection()
    auth_delete = AsyncMock(side_effect=ConnectionError("auth unavailable"))
    service = AccountDeletionService(connect=connector(connection, lifecycle), delete_auth=auth_delete)

    with pytest.raises(AccountDeletionPartialFailure) as exc:
        await service.delete(
            "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        )

    assert exc.value.application_data_deleted is True
    assert lifecycle == ["begin", "commit"]
    assert not any(
        sql.startswith("delete from account_deletion_tombstones")
        for sql, _ in connection.queries
    )


@pytest.mark.asyncio
async def test_revoked_session_cannot_delete_account():
    from app.db.account_deletion import AccountDeletionService, InvalidAuthSession

    lifecycle = []
    connection = Connection()
    original_execute = connection.execute

    async def execute(sql, params=()):
        normalized = " ".join(sql.split()).lower()
        if normalized.startswith("select 1 from auth.sessions"):
            connection.queries.append((normalized, params))
            return Cursor(None)
        return await original_execute(sql, params)

    connection.execute = execute
    auth_delete = AsyncMock()
    service = AccountDeletionService(connect=connector(connection, lifecycle), delete_auth=auth_delete)

    with pytest.raises(InvalidAuthSession):
        await service.delete("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "revoked-session")

    assert lifecycle == ["begin", "rollback"]
    auth_delete.assert_not_awaited()
    assert not any(sql.startswith("delete from users") for sql, _ in connection.queries)


def test_delete_request_requires_explicit_confirmation():
    from pydantic import ValidationError
    from app.api.routes.main import AccountDeleteRequest

    assert AccountDeleteRequest(confirmation="DELETE").confirmation == "DELETE"
    with pytest.raises(ValidationError):
        AccountDeleteRequest(confirmation="yes")


@pytest.mark.asyncio
async def test_delete_endpoint_forwards_recent_authenticated_session(client, monkeypatch):
    from app.api.routes.main import app
    from app.core.auth import AuthContext, get_recent_auth_context
    import app.db.account_deletion as deletion

    service = AsyncMock()
    service.delete.return_value = {"status": "deleted"}
    monkeypatch.setattr(deletion, "AccountDeletionService", lambda: service)
    app.dependency_overrides[get_recent_auth_context] = lambda: AuthContext(
        auth_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        session_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
    )
    try:
        response = await client.request(
            "DELETE", "/users/me", json={"confirmation": "DELETE"}
        )
    finally:
        app.dependency_overrides.pop(get_recent_auth_context, None)

    assert response.status_code == 200
    service.delete.assert_awaited_once_with(
        "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
    )


@pytest.mark.asyncio
async def test_conversation_lock_takes_shared_user_lock_and_rechecks_account(monkeypatch):
    from app.db import thread_lock

    lifecycle = []
    connection = Connection()
    original_execute = connection.execute

    async def execute(sql, params=()):
        normalized = " ".join(sql.split()).lower()
        if normalized.startswith("select id from users where id="):
            connection.queries.append((normalized, params))
            return Cursor({"id": params[0]})
        return await original_execute(sql, params)

    connection.execute = execute
    monkeypatch.setattr(thread_lock, "connection", connector(connection, lifecycle))

    async with thread_lock.conversation_lock("u1", "t1"):
        pass

    assert connection.queries == [
        (
            "select pg_advisory_xact_lock_shared(hashtextextended(%s,0))",
            ("account:u1",),
        ),
        ("select id from users where id=%s", ("u1",)),
        (
            "select pg_advisory_xact_lock(hashtextextended(%s,0))",
            ("conversation:u1:t1",),
        ),
    ]


@pytest.mark.asyncio
async def test_conversation_lock_refuses_request_that_waited_past_account_deletion(monkeypatch):
    from app.db import thread_lock

    lifecycle = []
    connection = Connection()
    original_execute = connection.execute

    async def execute(sql, params=()):
        normalized = " ".join(sql.split()).lower()
        if normalized.startswith("select id from users where id="):
            connection.queries.append((normalized, params))
            return Cursor(None)
        return await original_execute(sql, params)

    connection.execute = execute
    monkeypatch.setattr(thread_lock, "connection", connector(connection, lifecycle))

    with pytest.raises(thread_lock.AccountUnavailable):
        async with thread_lock.conversation_lock("deleted-user", "t1"):
            pytest.fail("deleted account must not enter the graph")

    assert lifecycle == ["begin", "rollback"]
