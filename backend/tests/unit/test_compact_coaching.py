from unittest.mock import AsyncMock
import pytest
from langchain_core.messages import AIMessage
from app.agents.team import DietTeam
from app.core.config import get_settings


@pytest.mark.parametrize('compact', [False, True])
@pytest.mark.parametrize('first', [False, True])
async def test_compact_only_changes_verified_followup_prompt(monkeypatch, compact, first):
    settings = get_settings().model_copy(update={'compact_followup_prompt': compact})
    monkeypatch.setattr('app.agents.team.get_settings', lambda: settings)
    seen = {}
    class Model:
        def bind_tools(self, tools):
            seen['tools'] = [t['function']['name'] for t in tools]
            return self
        async def ainvoke(self, messages, config=None):
            seen['instruction'] = messages[0].content
            return AIMessage(content='채소와 단백질을 곁들이세요.')
    repo = AsyncMock()
    team = DietTeam({'user_id': 'synthetic', 'message': '점심 추천해줘' if first else '그럼 일반식 먹어도 괜찮아?',
                    'messages': [{'role':'user', 'content':'점심 추천해줘'}]},
                    model_factory=Model, repository=repo, db=object())
    team.coaching_context = AsyncMock(return_value={'scope': 'fresh_current_request', 'intake': {'calories': 600}})
    result = await team.execute()
    assert ('후속 코칭 전용' in seen['instruction']) == (compact and not first)
    assert not any(t.startswith('propose_') for t in seen['tools'])
    assert result['execution_usage']['model_calls'] == 1
    repo.create.assert_not_called()
