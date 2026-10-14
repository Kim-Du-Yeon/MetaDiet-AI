from unittest.mock import AsyncMock
import pytest
from langchain_core.messages import AIMessage
from app.agents.team import DietTeam
from app.core.config import get_settings


@pytest.mark.parametrize('message', ['그럼 한식뷔페 가서 일반식 먹어도 괜찮아?',
    '그럼 샌드위치 먹어도 괜찮아?', '밥이랑 계란 먹어도 괜찮아?', '닭가슴살이랑 샐러드 먹어도 괜찮아?'])
@pytest.mark.parametrize('header', [False, True])
def test_plain_advice_can_display_verified_current_values_without_tools(message, header):
    from app.agents.coaching_route import followup_needs_tools
    if header:
        message += ' 첫 문장에 "오늘 섭취: N kcal, 하루 기준: N kcal" 형식으로 적어줘.'
    assert not followup_needs_tools(message)


@pytest.mark.parametrize('enabled', [False, True])
@pytest.mark.parametrize('case', ['plain', 'evidence', 'nutrition', 'medical', 'gout', 'brand', 'first', 'unverified'])
async def test_only_verified_plain_followup_omits_optional_tools(monkeypatch, enabled, case):
    settings = get_settings().model_copy(update={'followup_tools_enabled': enabled, 'followup_model': 'default'})
    monkeypatch.setattr('app.agents.team.get_settings', lambda: settings)
    seen = {'tools': []}
    class Model:
        def bind_tools(self, tools):
            seen['tools'] = [t['function']['name'] for t in tools]
            return self
        async def ainvoke(self, messages, config=None):
            seen['request'] = messages[-1].content
            return AIMessage(content='채소와 단백질 반찬을 곁들이세요.')
    message = {'plain': '그럼 밥이랑 계란 먹어도 괜찮아?',
               'evidence': '그럼 밥 먹어도 괜찮아? 공식 근거도 알려줘.',
               'nutrition': '그럼 밥 100g 먹어도 괜찮아?',
               'medical': '콜레스테롤이 높다는데 밥 먹어도 괜찮아?',
               'gout': '통풍인데 닭가슴살 먹어도 괜찮아?',
               'brand': '써브웨이 샌드위치 먹어도 괜찮아? 열량 알려줘.',
               'first': '점심 추천해줘', 'unverified': '그럼 밥 먹어도 괜찮아?'}[case]
    repo = AsyncMock()
    team = DietTeam({'user_id': 'u', 'message': message,
                     'messages': [{'role': 'user', 'content': '점심 추천해줘'}]},
                    model_factory=Model, repository=repo, db=object())
    team.coaching_context = AsyncMock(return_value=None if case == 'unverified' else
                                    {'scope': 'fresh_current_request', 'intake': {'calories': 600}})
    result = await team.execute()
    omit = not enabled and case == 'plain'
    assert bool(seen['tools']) == (not omit)
    if omit:
        assert '600' in seen['request']
        assert result['execution_usage']['model_calls'] == 1
    repo.create.assert_not_called()
