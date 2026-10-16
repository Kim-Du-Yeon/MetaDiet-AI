from unittest.mock import AsyncMock
from langchain_core.messages import AIMessage
from app.agents.team import DietTeam
from test_diet_team import Model


async def test_explicit_readonly_goal_review_uses_one_specialist_without_write_tools():
    model = Model([AIMessage(content='목표 검토 결과입니다.')])
    team = DietTeam({'user_id':'u1','message':'목표 검토와 영양 근거 검토를 함께 해줘. 기록은 변경하지 마.'},
        model_factory=lambda:model, repository=AsyncMock(), db=object())
    team.budget.persist = AsyncMock()
    result = await team.execute()
    assert model.ainvoke.await_count == 1
    assert result['agent_used'] == 'goal'
    names = str(model.schemas)
    assert 'read_profile' in names and 'search_evidence' in names
    assert 'propose_strategy' not in names and 'propose_meal' not in names
    team.repository.create.assert_not_called()
    team.budget.persist.assert_any_await('delegate:goal')
    assert team.delegations == {'goal':1}


async def test_goal_change_without_readonly_instruction_retains_supervisor():
    model = Model([AIMessage(content='검토하겠습니다.')])
    team = DietTeam({'user_id':'u1','message':'목표 검토하고 전략을 변경해줘'},
        model_factory=lambda:model, repository=AsyncMock(), db=object())
    result = await team.execute()
    assert result['agent_used'] == 'supervisor'
    assert 'delegate_goal' in str(model.schemas)


async def test_readonly_trend_without_explicit_evidence_request_retains_supervisor():
    model = Model([AIMessage(content='추세 검토 결과입니다.')])
    team = DietTeam({'user_id':'u1','message':'최근 식사와 체중 추세를 확인하고 목표 진행과 근손실 위험을 검토해줘. 기록은 변경하지 마.'},
        model_factory=lambda:model, repository=AsyncMock(), db=object())
    result = await team.execute()
    assert result['agent_used'] == 'supervisor'
    assert 'delegate_goal' in str(model.schemas)
