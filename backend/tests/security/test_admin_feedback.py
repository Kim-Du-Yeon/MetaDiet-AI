from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from app.core.auth import get_current_admin
from app.api.routes.main import app


async def test_feedback_admin_routes_require_sign_in(client):
    assert (await client.get('/admin/feedback')).status_code == 401
    assert (await client.get(f'/admin/feedback/{uuid4()}')).status_code == 401
    assert (await client.patch(f'/admin/feedback/{uuid4()}', json={
        'version':1, 'status':'received'})).status_code == 401


@pytest.mark.asyncio
async def test_feedback_admin_routes_deny_members_before_repository(client, monkeypatch):
    def denied():
        raise HTTPException(403, '관리자 권한이 필요합니다.')
    app.dependency_overrides[get_current_admin] = denied
    try:
        assert (await client.get('/admin/feedback')).status_code == 403
        assert (await client.get(f'/admin/feedback/{uuid4()}')).status_code == 403
        assert (await client.patch(f'/admin/feedback/{uuid4()}', json={
            'version': 1, 'status': 'resolved', 'admin_note': ''})).status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_admin, None)


@pytest.mark.asyncio
async def test_admin_feedback_validation_and_conflict(client, monkeypatch):
    from app.api.routes import admin_feedback as routes
    repo = AsyncMock()
    repo.list.return_value = {'items': [], 'has_more': False}
    repo.get.return_value = None
    monkeypatch.setattr(routes, 'AdminFeedbackRepository', lambda: repo)
    app.dependency_overrides[get_current_admin] = lambda: 'admin-auth'
    try:
        assert (await client.get('/admin/feedback?limit=101')).status_code == 422
        assert (await client.get('/admin/feedback?status=bad')).status_code == 422
        assert (await client.get('/admin/feedback?category=bad')).status_code == 422
        assert (await client.get('/admin/feedback')).json() == {'items': [], 'has_more': False}
        assert (await client.get('/admin/feedback')).headers['cache-control'] == 'no-store'
        assert (await client.get(f'/admin/feedback/{uuid4()}')).status_code == 404
        repo.update.return_value = None
        result = await client.patch(f'/admin/feedback/{uuid4()}', json={
            'version': 1, 'status': 'resolved', 'admin_note': 'verified'})
        assert result.status_code == 409
        assert repo.update.call_args.kwargs['admin_auth_id'] == 'admin-auth'
        assert (await client.patch(f'/admin/feedback/{uuid4()}', json={
            'version': 1, 'status': 'bad', 'admin_note': ''})).status_code == 422
        assert (await client.patch(f'/admin/feedback/{uuid4()}', json={
            'version': 1, 'status': 'received', 'admin_note': 'x'*1001})).status_code == 422
        assert (await client.patch(f'/admin/feedback/{uuid4()}', json={
            'version': 1, 'status': 'received', 'updated_by': 'forged'})).status_code == 422
        repo.get.return_value = {'id':'one','comment':'private'}
        assert (await client.get(f'/admin/feedback/{uuid4()}')).json()['comment'] == 'private'
        repo.update.return_value = {'status':'resolved','version':2}
        saved = await client.patch(f'/admin/feedback/{uuid4()}', json={
            'version':1,'status':'resolved','admin_note':' done '})
        assert saved.json()['version'] == 2
        assert repo.update.call_args.kwargs['admin_note'] == 'done'
    finally:
        app.dependency_overrides.pop(get_current_admin, None)


async def test_feedback_database_parameters_privacy_and_conflict():
    from contextlib import asynccontextmanager
    from app.db.admin_feedback import AdminFeedbackRepository
    conn = AsyncMock()
    cursor = AsyncMock()
    conn.execute.return_value = cursor
    cursor.fetchall.return_value = [{'id':uuid4(),'preview':'one'}, {'id':uuid4(),'preview':'two'}]
    cursor.fetchone.return_value = None
    @asynccontextmanager
    async def connect():
        yield conn
    repo = AdminFeedbackRepository(connect)
    result = await repo.list(status='received',category='bug',limit=1,offset=20)
    sql, params = next(call.args for call in conn.execute.call_args_list if 'left(comment, 100)' in call.args[0])
    assert params == ('received','bug',2,20)
    assert 'left(comment, 100)' in sql and 'user_id' not in sql
    assert result['has_more'] is True and len(result['items']) == 1
    feedback_id = uuid4()
    assert await repo.update(feedback_id,version=2,status='resolved',admin_note="' SQL",admin_auth_id='admin') is None
    sql, params = conn.execute.call_args.args
    assert 'where id=%s and version=%s' in sql
    assert params == (feedback_id,2)
    assert 'for update' in sql
    assert "' SQL" not in sql


async def test_admin_failure_is_sanitized(client, monkeypatch):
    from app.api.routes import admin_feedback as routes
    from app.db.feedback import FeedbackStorageUnavailable
    repo = AsyncMock()
    repo.list.side_effect = FeedbackStorageUnavailable('sensitive original comment')
    monkeypatch.setattr(routes,'AdminFeedbackRepository',lambda:repo)
    app.dependency_overrides[get_current_admin] = lambda:'admin'
    try:
        result = await client.get('/admin/feedback')
        assert result.status_code == 503
        assert 'sensitive' not in result.text
    finally:
        app.dependency_overrides.pop(get_current_admin,None)
