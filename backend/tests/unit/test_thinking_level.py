from unittest.mock import MagicMock
import pytest
from app.core.llm import get_chat_model


@pytest.mark.parametrize('level', [None, 'low', 'medium', 'high'])
def test_explicit_thinking_preserves_default_and_native_tools(monkeypatch, level):
    provider = MagicMock()
    monkeypatch.setattr('app.core.llm.ChatGoogleGenerativeAI', provider)
    monkeypatch.setattr('app.core.llm.get_settings', lambda: MagicMock(gemini_api_key='test-only'))
    model = get_chat_model(thinking_level=level)
    model.bind_tools([])
    kwargs = provider.call_args.kwargs
    if level is None:
        assert 'thinking_level' not in kwargs
    else:
        assert kwargs['thinking_level'] == level
    provider.return_value.bind_tools.assert_called_once_with([])


def test_unsupported_thinking_rejected_before_network():
    with pytest.raises(ValueError):
        get_chat_model(thinking_level='minimal')


@pytest.mark.parametrize('setting,expected', [('low','low'), ('default',None)])
@pytest.mark.parametrize('direct', [True, False])
async def test_lower_thinking_only_for_verified_followup(monkeypatch, setting, expected, direct):
    from unittest.mock import AsyncMock
    from langchain_core.messages import AIMessage
    from app.agents.team import DietTeam
    from app.core.config import get_settings
    settings = get_settings().model_copy(update={'coaching_thinking_level':setting, 'first_coaching_mode':'off'})
    monkeypatch.setattr('app.agents.team.get_settings', lambda:settings)
    seen = []
    class Model:
        def bind_tools(self, tools): return self
        async def ainvoke(self, messages, config=None):
            return AIMessage(content='채소와 단백질 반찬을 곁들이세요.')
    def factory(**kwargs):
        seen.append(kwargs.get('thinking_level'))
        return Model()
    monkeypatch.setattr('app.agents.team.get_chat_model', factory)
    team = DietTeam({'user_id':'u', 'message':'그럼 일반식 먹어도 괜찮아?' if direct else '점심 추천해줘',
        'messages':[{'role':'user','content':'점심 추천해줘'}]}, repository=AsyncMock(), db=object())
    team.coaching_context = AsyncMock(return_value={'scope':'fresh_current_request','intake':{'calories':600}})
    result = await team.execute()
    assert seen == [expected if direct else None]
    assert result['agent_used'] == ('meal' if direct else 'supervisor')
