from datetime import date
from unittest.mock import AsyncMock
import pytest
from app.agents.team import DietTeam, Empty
from test_diet_team import Model, call
from langchain_core.messages import AIMessage


def make_team(**kwargs):
    return DietTeam({'user_id':'u1','message':'점심 추천해줘','requested_action':'meal_plan'},
        repository=AsyncMock(),db=object(),**kwargs)

async def test_same_request_reads_profile_and_intake_once():
    team=make_team()
    team.rows=AsyncMock(side_effect=[[{'goal':'diet'}],[{'daily_calories':2000}],[{'calories':300}]])
    await team.read_profile(Empty());await team.read_profile(Empty())
    await team.read_intake(Empty());await team.read_intake(Empty())
    assert team.rows.await_count==3

async def test_next_request_and_other_user_never_reuse_previous_cache():
    for user in ['u1','u1','u2']:
        team=make_team();team.state['user_id']=user
        team.rows=AsyncMock(return_value=[{'calories':900}])
        assert (await team.read_intake(Empty()))['calories']==900
        team.rows.assert_awaited_once()
        assert team.rows.call_args.kwargs['user_id']==user

async def test_date_change_invalidates_request_intake(monkeypatch):
    day=[date(2026,10,13)];monkeypatch.setattr('app.agents.team.service_today',lambda:day[0])
    team=make_team();team.rows=AsyncMock(side_effect=[[{'calories':300}],[]])
    assert (await team.read_intake(Empty()))['calories']==300
    day[0]=date(2026,10,14)
    assert (await team.read_intake(Empty()))['calories']==0
    assert team.rows.await_count==2

async def test_failed_read_is_not_cached_as_zero():
    team=make_team();team.rows=AsyncMock(side_effect=[ConnectionError('offline'),[{'calories':600}]])
    with pytest.raises(ConnectionError):await team.read_intake(Empty())
    assert team.intake is None
    assert (await team.read_intake(Empty()))['calories']==600

async def test_coaching_prefetch_eliminates_model_read_selection_round():
    root=Model([call('delegate_meal',{'query':'점심 조언'})]);child=Model([AIMessage(content='담백한 단백질과 채소를 골라보세요.')])
    models=iter([root,child]);team=make_team(model_factory=lambda:next(models))
    team.rows=AsyncMock(side_effect=[[{'goal':'diet'}],[{'daily_calories':2000}],[{'calories':300}]])
    result=await team.execute()
    assert result['execution_usage']['model_calls']==2
    assert team.rows.await_count==3
    assert 'verified_context' in str(child.ainvoke.call_args)
    team.repository.create.assert_not_called()

async def test_restricted_policy_does_not_prefetch():
    root=Model([call('delegate_meal',{'query':'조언'})]);child=Model([AIMessage(content='정보 확인 권한이 없습니다.')])
    models=iter([root,child]);team=make_team(model_factory=lambda:next(models));team.allowed={'search_foods'}
    team.rows=AsyncMock()
    await team.execute()
    team.rows.assert_not_called()


async def test_prefetch_failure_does_not_escape_or_claim_empty_intake():
    team=make_team();team.rows=AsyncMock(side_effect=RuntimeError('db disconnected'))
    result=await team.coaching_context()
    assert result['status']=='unavailable'
    assert 'intake' not in result
    assert team.intake is None


async def test_prefetch_preserves_execution_budget_stop():
    from app.agents.runtime import ExecutionStopped
    team=make_team();team.budget.max_tool_calls=0
    with pytest.raises(ExecutionStopped,match='tool_call_limit'):
        await team.coaching_context()

def test_coaching_progress_describes_verified_context():
    from app.agents.execution_stream import progress_for_runtime_event
    result=progress_for_runtime_event('coaching_context_ready',agent='meal')
    assert result['phase']=='coaching_context'
    assert result['label']=='확인한 기록을 바탕으로 답변 준비 중'

async def test_changed_strategy_is_loaded_in_next_request():
    for target in [2000,1800]:
        team=make_team();team.rows=AsyncMock(side_effect=[[{'goal':'diet'}],[{'daily_calories':target}]])
        assert (await team.read_profile(Empty()))['strategy']['daily_calories']==target
        assert team.rows.await_count==2


async def test_direct_supervisor_coaching_also_uses_fresh_context():
    root=Model([AIMessage(content='한식뷔페도 괜찮습니다.')])
    team=make_team(model_factory=lambda:root)
    team.rows=AsyncMock(side_effect=[[{'goal':'diet'}],[{'daily_calories':2000}],[{'calories':900}]])
    result=await team.execute()
    assert team.rows.await_count==3
    assert 'verified_context' in str(root.ainvoke.call_args)
    assert result['execution_usage']['model_calls']==1
    assert team.intake['calories']==900
