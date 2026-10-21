"""Natural grounding requests must retrieve even if the model chooses no tools."""
import json
from unittest.mock import AsyncMock

import pytest
from langchain_core.documents import Document
from langchain_core.messages import AIMessage

from app.agents.team import DietTeam


@pytest.mark.parametrize('message', [
    '저녁에 치킨 약속이 있는데 점심을 어떻게 먹어야 좋을까? 다이어트를 위해서 어떻게 밥을 먹으면 좋을지 영양성분 지식에 근거해서 알려줘',
    '점심은 어떻게 먹을까? 영양학적으로 설명해줘',
    '근육을 유지하려면 어떻게 먹어야 해? 근거해서 알려줘',
    '오늘 저녁 추천해줘. 관련 자료도 찾아줘',
])
async def test_natural_request_searches_before_model_without_model_tool_call(monkeypatch, message):
    import app.rag.retriever as retriever
    retrieve = AsyncMock(return_value={'grounded':True, 'docs':[
        Document(page_content='검토한 영양 근거', metadata={'source_file':'guide.pdf','page':3,
            'source_url':'https://example.org/guide'})]})
    monkeypatch.setattr(retriever, 'retrieve', retrieve)
    class Model:
        def bind_tools(self, tools): return self
        async def ainvoke(self, messages, config=None):
            assert retrieve.await_count == 1
            request = json.loads(messages[-1].content)
            evidence = request['requested_evidence']['evidence']
            return AIMessage(content=f"담백한 점심을 권해요. [근거:{evidence[0]['evidence_id']}]")
    repo = AsyncMock()
    team = DietTeam({'user_id':'u','message':message}, model_factory=Model, db=object(), repository=repo)
    team.coaching_context = AsyncMock(return_value=None)
    result = await team.execute()
    assert result['answer_basis']['search']['status'] == 'cited'
    assert result['answer_basis']['documents'][0]['source'] == 'guide.pdf'
    assert result['execution_usage']['tool_calls'] == 1
    repo.create.assert_not_called()


@pytest.mark.parametrize('state', [
    {'message':'저녁 추천'},
    {'message':'영양학적으로 알려줘. 검색하지 마'},
    {'message':'내 기록에 근거해서 오늘 섭취량만 알려줘'},
    {'message':'영양학적으로 설명해줘', 'tool_policy':['read_profile']},
    {'message':'영양학적으로 설명해줘', 'pending_proposal':{'id':'pending','payload':{}}},
    {'message':'영양학적으로 설명해줘', 'requested_action':'record_only'},
])
async def test_ordinary_advice_no_search_and_policy_pending_boundaries_preserved(monkeypatch, state):
    import app.rag.retriever as retriever
    retrieve = AsyncMock()
    monkeypatch.setattr(retriever, 'retrieve', retrieve)
    class Model:
        def bind_tools(self, tools): return self
        async def ainvoke(self, messages, config=None): return AIMessage(content='일반 안내')
    team = DietTeam({'user_id':'u', **state}, model_factory=Model, db=object(), repository=AsyncMock())
    team.coaching_context = AsyncMock(return_value=None)
    result = await team.execute()
    retrieve.assert_not_called()
    assert result['answer_basis']['search']['status'] == 'not_searched'


@pytest.mark.parametrize('failure,status', [(False,'insufficient_evidence'), (True,'search_unavailable')])
async def test_requested_search_empty_or_failed_does_not_invent_citations(monkeypatch, failure, status):
    import app.rag.retriever as retriever
    retrieve = AsyncMock(side_effect=ConnectionError('secret') if failure else None,
        return_value={'grounded':False,'docs':[]})
    monkeypatch.setattr(retriever, 'retrieve', retrieve)
    class Model:
        def bind_tools(self, tools): return self
        async def ainvoke(self, messages, config=None): return AIMessage(content='일반 안내')
    team = DietTeam({'user_id':'u','message':'영양학적으로 점심 설명해줘'},
        model_factory=Model, db=object(), repository=AsyncMock())
    team.coaching_context = AsyncMock(return_value=None)
    result = await team.execute()
    assert result['answer_basis']['search']['status'] == status
    assert not result['answer_basis']['documents']
    assert 'secret' not in str(result)


async def test_grounded_but_uncited_response_is_not_auto_attributed(monkeypatch):
    import app.rag.retriever as retriever
    monkeypatch.setattr(retriever,'retrieve', AsyncMock(return_value={'grounded':True,
        'docs':[Document(page_content='근거',metadata={'source_file':'guide.pdf'})]}))
    class Model:
        def bind_tools(self, tools): return self
        async def ainvoke(self, messages, config=None): return AIMessage(content='문서를 인용하지 않은 안내')
    team = DietTeam({'user_id':'u','message':'영양학적으로 설명해줘'}, model_factory=Model,
        db=object(), repository=AsyncMock())
    team.coaching_context = AsyncMock(return_value=None)
    result = await team.execute()
    assert result['answer_basis']['search']['status'] == 'retrieved_not_cited'
    assert result['answer_basis']['documents'] == []


async def test_requested_evidence_reaches_delegated_specialist(monkeypatch):
    import app.rag.retriever as retriever
    monkeypatch.setattr(retriever,'retrieve', AsyncMock(return_value={'grounded':True,
        'docs':[Document(page_content='근거',metadata={'source_file':'guide.pdf'})]}))
    class Model:
        def bind_tools(self, tools): return self
        async def ainvoke(self, messages, config=None):
            request = json.loads(messages[-1].content)
            if 'task' not in request:
                return AIMessage(content='', tool_calls=[{'id':'d','name':'delegate_meal',
                    'args':{'query':'점심 조언'}}])
            key=request['requested_evidence']['evidence'][0]['evidence_id']
            return AIMessage(content=f'조언 [근거:{key}]')
    team=DietTeam({'user_id':'u','message':'점심을 영양학적으로 알려줘'}, model_factory=Model,
        db=object(),repository=AsyncMock())
    team.coaching_context=AsyncMock(return_value=None)
    result=await team.execute()
    assert len(result['answer_basis']['documents'])==1
