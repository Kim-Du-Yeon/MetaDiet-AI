from unittest.mock import AsyncMock
from uuid import uuid4
from app.api.routes.main import app
from app.core.auth import get_current_admin
from contextlib import asynccontextmanager
import pytest
from app.db.admin_feedback import AdminFeedbackRepository


async def test_assignee_filter_validated_and_forwarded(client, monkeypatch):
    from app.api.routes import admin_feedback as routes
    repo=AsyncMock()
    repo.list.return_value={'items':[], 'has_more':False, 'counts':{'total_unprocessed':4,'unprocessed':2,'matched_total':0}}
    monkeypatch.setattr(routes,'AdminFeedbackRepository',lambda:repo)
    app.dependency_overrides[get_current_admin]=lambda:'admin'
    try:
        assert (await client.get('/admin/feedback?assignee=bad')).status_code==422
        result=await client.get('/admin/feedback?assignee=unassigned&status=fixed&category=bug')
        assert result.status_code==200
        assert repo.list.call_args.kwargs['assignee']=='unassigned'
        assert result.json()['counts']['unprocessed']==2
        identifier=str(uuid4())
        assert (await client.get('/admin/feedback?assignee='+identifier)).status_code==200
        assert str(repo.list.call_args.kwargs['assignee'])==identifier
    finally:
        app.dependency_overrides.pop(get_current_admin,None)


@pytest.mark.parametrize('assignee', [None, 'unassigned', uuid4()])
async def test_count_scope_is_not_pagination_or_status_scope(assignee):
    conn=AsyncMock()
    rows=AsyncMock(fetchall=AsyncMock(return_value=[]))
    counts={'total_unprocessed':8,'unprocessed':3,'matched_total':1}
    conn.execute.side_effect=[AsyncMock(), rows, AsyncMock(fetchone=AsyncMock(return_value=counts))]
    @asynccontextmanager
    async def connect():
        yield conn
    result=await AdminFeedbackRepository(connect).list(status='fixed',category='bug',assignee=assignee,offset=40,limit=20)
    assert result['counts']==counts
    assert conn.execute.call_args_list[0].args==('set transaction isolation level repeatable read, read only',)
    list_sql,list_params=conn.execute.call_args_list[1].args
    count_sql,count_params=conn.execute.call_args_list[2].args
    expected_pending=('bug',) + ((assignee,) if assignee not in (None,'unassigned') else ())
    expected_list=('fixed','bug') + ((assignee,) if assignee not in (None,'unassigned') else ())
    assert list_params==(*expected_list,21,40)
    assert count_params==(*expected_pending,*expected_list)
    assert 'offset' not in count_sql and 'limit' not in count_sql
    assert "'received','reproducing','on_hold'" in count_sql
    assert ('assignee_id is null' in list_sql)==(assignee=='unassigned')
