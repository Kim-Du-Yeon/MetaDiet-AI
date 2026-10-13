import json
from unittest.mock import AsyncMock
import pytest
from langchain_core.messages import AIMessage
from app.agents.team import DietTeam

HISTORY = [{'role': 'user', 'content': '점심 추천해줘. 조언만 해줘.'},
           {'role': 'assistant', 'content': '밥과 단백질 반찬을 곁들이세요.'}]


@pytest.mark.parametrize('message', ['그럼 한식뷔페 가서 일반식 한 접시 먹는 건 괜찮아?',
    '그럼 편의점에서 샌드위치 먹어도 괜찮아?', '그럼 일반식으로 밥이랑 계란 먹어도 괜찮아?'])
async def test_direct_followup_is_read_only_and_uses_fresh_context(message):
    seen = []
    class Model:
        def bind_tools(self, tools):
            seen.extend(t['function']['name'] for t in tools)
            return self
        async def ainvoke(self, messages, config=None):
            req = json.loads(messages[-1].content)
            assert req['verified_context']['intake']['calories'] == 600
            return AIMessage(content='한 접시로 담되 채소와 단백질 반찬을 곁들이세요.')
    repo = AsyncMock()
    team = DietTeam({'user_id':'u', 'message':message, 'messages':HISTORY}, repository=repo, db=object(), model_factory=Model)
    team.coaching_context = AsyncMock(return_value={'scope':'fresh_current_request','intake':{'calories':600}})
    result = await team.execute()
    assert result['agent_used'] == 'meal'
    assert result['execution_usage']['model_calls'] == 1
    assert not any(name.startswith(('delegate_', 'propose_')) for name in seen)
    repo.create.assert_not_called()


@pytest.mark.parametrize('extra', [
    {'message':'그럼 한식뷔페 먹었어 기록해줘'}, {'message':'그럼 한식뷔페 먹어도 돼? 식단 짜줘'},
    {'message':'그럼 약 먹어도 괜찮아?'}, {'message':'주식 사도 괜찮아?'},
    {'message':'당뇨인데 일반식 먹어도 괜찮아?'}, {'requested_action':'meal_plan'},
    {'message':'그럼 밥 먹어도 괜찮아? 아침 바나나 한 개 먹었으니 추가해줘'},
    {'message':'그럼 밥 먹어도 괜찮아? 아침 내용을 바꿔줘'},
    {'pending_proposal':{'id':'p'}}, {'awaiting_confirmation':True}, {'messages':[]},
])
def test_uncertain_or_mutating_requests_keep_supervisor(extra):
    from app.agents.coaching_route import simple_followup
    state = {'message':'그럼 한식뷔페 먹어도 괜찮아?', 'messages':HISTORY, **extra}
    assert not simple_followup(state)
