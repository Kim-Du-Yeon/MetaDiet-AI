from unittest.mock import AsyncMock, MagicMock
import pytest
from langchain_core.messages import AIMessage
from app.core.llm import get_chat_model
from app.core.config import get_settings


def test_chat_override_preserves_native_tools_and_low_thinking(monkeypatch):
    provider = MagicMock()
    monkeypatch.setattr('app.core.llm.ChatGoogleGenerativeAI', provider)
    monkeypatch.setattr('app.core.llm.get_settings', lambda: MagicMock(gemini_api_key='test-only'))
    get_chat_model(model_name='gemini-3.5-flash-lite', thinking_level='low').bind_tools([])
    assert provider.call_args.kwargs['model'] == 'gemini-3.5-flash-lite'
    assert provider.call_args.kwargs['thinking_level'] == 'low'
    provider.return_value.bind_tools.assert_called_once_with([])


@pytest.mark.parametrize('role', ['vision', 'eval'])
def test_followup_override_cannot_change_other_roles(role):
    with pytest.raises(ValueError):
        get_chat_model(role=role, model_name='gemini-3.5-flash-lite')


@pytest.mark.parametrize('candidate', [False, True])
@pytest.mark.parametrize('first', [False, True])
async def test_lite_only_used_for_verified_followup(monkeypatch, candidate, first):
    from app.agents.team import DietTeam
    settings = get_settings().model_copy(update={'followup_model': 'gemini-3.5-flash-lite' if candidate else 'default'})
    monkeypatch.setattr('app.agents.team.get_settings', lambda: settings)
    seen = []
    class Model:
        def bind_tools(self, tools):
            assert not any(t['function']['name'].startswith('propose_') for t in tools)
            return self
        async def ainvoke(self, messages, config=None):
            assert '600' in messages[-1].content
            return AIMessage(content='채소와 단백질 반찬을 곁들이세요.')
    def factory(**kwargs):
        seen.append(kwargs)
        return Model()
    monkeypatch.setattr('app.agents.team.get_chat_model', factory)
    repo = AsyncMock()
    team = DietTeam({'user_id': 'u', 'message': '점심 추천해줘' if first else '그럼 밥 먹어도 괜찮아?',
                     'messages': [{'role': 'user', 'content': '점심 추천해줘'}]}, repository=repo, db=object())
    team.coaching_context = AsyncMock(return_value={'scope': 'fresh_current_request', 'intake': {'calories': 600}})
    result = await team.execute()
    assert seen[0].get('model_name') == ('gemini-3.5-flash-lite' if candidate and not first else None)
    assert seen[0]['thinking_level'] == 'low'
    assert result['execution_usage']['model_calls'] == 1
    repo.create.assert_not_called()
