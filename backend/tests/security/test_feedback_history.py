from unittest.mock import AsyncMock
from uuid import uuid4
from fastapi import HTTPException
from app.core.auth import get_current_admin
from app.api.routes.main import app
import pytest
from contextlib import asynccontextmanager
from app.db.admin_feedback import AdminFeedbackRepository, InvalidAssignee
from app.db.feedback import FeedbackStorageUnavailable


async def test_assignment_and_history_are_admin_only(client):
    paths = ['/admin/feedback/assignees', f'/admin/feedback/{uuid4()}/history']
    for path in paths:
        assert (await client.get(path)).status_code == 401
    def denied():
        raise HTTPException(403, 'denied')
    app.dependency_overrides[get_current_admin] = denied
    try:
        for path in paths:
            assert (await client.get(path)).status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_admin, None)


@pytest.mark.parametrize('fail_history', [False, True])
async def test_review_and_history_share_transaction(fail_history):
    conn = AsyncMock()
    before = {'status':'received','admin_note':'old','assignee_id':None}
    after = {**before, 'status':'resolved','admin_note':'new','version':2,'id':uuid4()}
    conn.execute.side_effect = [AsyncMock(fetchone=AsyncMock(return_value=before)),
                               AsyncMock(fetchone=AsyncMock(return_value=after)),
                               RuntimeError('audit write failed') if fail_history else AsyncMock()]
    ended = []
    @asynccontextmanager
    async def connect():
        try:
            yield conn
        except Exception:
            ended.append('rollback')
            raise
        else:
            ended.append('commit')
    operation = AdminFeedbackRepository(connect).update(after['id'], version=1, status='resolved',
        admin_note='new', admin_auth_id=uuid4(), assignee_id=None)
    if fail_history:
        with pytest.raises(FeedbackStorageUnavailable):
            await operation
        assert ended == ['rollback']
    else:
        assert (await operation)['version'] == 2
        assert ended == ['commit']
    sql, params = conn.execute.call_args.args
    assert 'insert into beta_feedback_history' in sql
    assert params[3:7] == ('received','resolved','old','new')


async def test_invalid_assignee_aborts_without_update(monkeypatch):
    conn = AsyncMock()
    conn.execute.side_effect = [AsyncMock(fetchone=AsyncMock(return_value={
        'status':'received','admin_note':'','assignee_id':None})), AsyncMock(fetchone=AsyncMock(return_value=None))]
    @asynccontextmanager
    async def connect():
        yield conn
    monkeypatch.setattr('app.db.admin_feedback.admin_emails', lambda: ['admin@example.invalid'])
    with pytest.raises(InvalidAssignee):
        await AdminFeedbackRepository(connect).update(uuid4(),version=1,status='resolved',admin_note='',
            admin_auth_id=uuid4(),assignee_id=uuid4())
    assert conn.execute.call_count == 2
    sql, params = conn.execute.call_args.args
    assert 'auth.users' in sql and params[1] == ['admin@example.invalid']


async def test_assignment_validation_and_legacy_preservation(client, monkeypatch):
    from app.api.routes import admin_feedback as routes
    repo = AsyncMock()
    repo.update.return_value = {'version': 2}
    monkeypatch.setattr(routes, 'AdminFeedbackRepository', lambda: repo)
    app.dependency_overrides[get_current_admin] = lambda: 'server-actor'
    path = f'/admin/feedback/{uuid4()}'
    body = {'version': 1, 'status': 'received'}
    try:
        assert (await client.patch(path, json={**body, 'assignee_id': 'bad'})).status_code == 422
        assert (await client.patch(path, json=body)).status_code == 200
        assert 'assignee_id' not in repo.update.call_args.kwargs
        assert (await client.patch(path, json={**body, 'assignee_id': None})).status_code == 200
        assert repo.update.call_args.kwargs['assignee_id'] is None
        assert repo.update.call_args.kwargs['admin_auth_id'] == 'server-actor'
    finally:
        app.dependency_overrides.pop(get_current_admin, None)
