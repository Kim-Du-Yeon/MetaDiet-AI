"""Separate fictional definition development set; every provider is mocked."""
from unittest.mock import AsyncMock

import pytest
from langchain_core.documents import Document

from app.rag.agentic import Assessment, bounded_retrieve


@pytest.mark.asyncio
@pytest.mark.parametrize('question,related,direct', [
    ('How does the fictional Nivo manual define reserve balance?',
     'The Quota is a daily allocation intended to maintain reserve balance.',
     'Reserve balance means available units equal reserved units.'),
    ('가상 솔 문서에서 고요 지표의 정의는 무엇인가요?',
     '보조 지수는 고요 지표를 유지하는 데 필요한 입력량이다.',
     '고요 지표는 입력 사건 수와 출력 사건 수의 차이를 뜻한다.'),
    ('What does the fictional Vela indicator mean?',
     'The Nova factor predicts the Vela indicator for a pilot cohort.',
     'The Vela indicator is the fraction of completed trials among eligible trials.'),
    ('가상 고리 수치가 뭐야?',
     '보조량은 가상 고리 수치를 예측한다.',
     '가상 고리 수치는 완료된 사건의 개수를 뜻한다.'),
])
async def test_related_concept_cannot_end_definition_search(question, related, direct):
    fetch=AsyncMock(side_effect=[{'grounded':True,'max_score':.9,
        'docs':[Document(page_content=related,metadata={'source_file':'fiction.txt','page':1})]},
        {'grounded':True,'max_score':.9,
        'docs':[Document(page_content=direct,metadata={'source_file':'fiction.txt','page':2})]}])
    assess=AsyncMock(side_effect=[
        Assessment(sufficient=True,missing_core=[],supported_excerpts=[related],definition_support='related_only'),
        Assessment(sufficient=True,missing_core=[],supported_excerpts=[direct],definition_support='direct')])
    value=await bounded_retrieve(question,retrieve=fetch,assess=assess,expand=AsyncMock(return_value=[]))
    assert value['grounded'] and fetch.await_count==2
    assert value['agentic']['definition_research_required']
    assert value['agentic']['definition_support']=='direct'
    assert question in fetch.await_args_list[1].args[0]
    assert direct in value['answer_guidance']
    assert all(call.args[0]==question for call in assess.await_args_list)


@pytest.mark.asyncio
@pytest.mark.parametrize('support', ['related_only','missing','not_assessed','not_requested'])
async def test_no_direct_definition_is_not_promoted_to_partial_answer(support):
    text='Quota preserves fictional reserve balance but does not define it.'
    fetch=AsyncMock(return_value={'grounded':True,'max_score':.9,
        'docs':[Document(page_content=text,metadata={'source_file':'fiction.txt'})]})
    value=await bounded_retrieve('Define fictional reserve balance.',retrieve=fetch,
        assess=AsyncMock(return_value=Assessment(sufficient=True,missing_core=[],
            supported_excerpts=[text],definition_support=support)),expand=AsyncMock(return_value=[]))
    assert fetch.await_count==2
    assert not value['grounded'] and not value['context']
    assert value['agentic']['missing_core']


@pytest.mark.asyncio
async def test_direct_definition_needs_no_second_search():
    text='A fictional value is the count of selected events.'
    fetch=AsyncMock(return_value={'grounded':True,'max_score':.9,
        'docs':[Document(page_content=text,metadata={'source_file':'fiction.txt'})]})
    value=await bounded_retrieve('Define the fictional value.',retrieve=fetch,
        assess=AsyncMock(return_value=Assessment(sufficient=True,missing_core=[],
            supported_excerpts=[text],definition_support='direct')),expand=AsyncMock(return_value=[]))
    assert value['grounded'] and fetch.await_count==1


@pytest.mark.asyncio
@pytest.mark.parametrize('question', [
    'What quantity is listed for the fictional value?',
    'Do not define the fictional value; just list its quantity.',
    '정의 말고 가상 지표의 분량만 알려줘.',
])
async def test_quantity_question_does_not_require_definition_classification(question):
    value=await bounded_retrieve(question,
        retrieve=AsyncMock(return_value={'grounded':True,'max_score':.9,'docs':[], 'context':'16 units'}),
        assess=AsyncMock(return_value=Assessment(sufficient=True,missing_core=[])))
    assert value['grounded']


@pytest.mark.asyncio
async def test_definition_query_does_not_treat_an_empty_quote_as_direct_evidence():
    fetch=AsyncMock(return_value={'grounded':True,'max_score':.9,'docs':[], 'context':'related'})
    value=await bounded_retrieve('Define the fictional value.',retrieve=fetch,
        assess=AsyncMock(return_value=Assessment(sufficient=True,missing_core=[],definition_support='direct')))
    assert fetch.await_count==2 and not value['grounded']


@pytest.mark.asyncio
async def test_scoped_definition_is_direct_without_inventing_general_applicability():
    text='For pilot participants only, marker L means selected events divided by all events.'
    fetch=AsyncMock(return_value={'grounded':True,'max_score':.9,
        'docs':[Document(page_content=text,metadata={'source_file':'fiction.txt'})]})
    value=await bounded_retrieve('Define marker L for the pilot population.',retrieve=fetch,
        assess=AsyncMock(return_value=Assessment(sufficient=True,missing_core=[],
            definition_support='direct',supported_excerpts=[text])),expand=AsyncMock(return_value=[]))
    assert value['grounded'] and fetch.await_count==1
    assert text in value['answer_guidance']


@pytest.mark.asyncio
async def test_shared_budget_stop_prevents_definition_research_call():
    from app.agents.runtime import ExecutionStopped
    fetch=AsyncMock(return_value={'grounded':True,'max_score':.9,'docs':[], 'context':'related only'})
    reserve=AsyncMock(side_effect=[None,ExecutionStopped('tool_call_limit')])
    with pytest.raises(ExecutionStopped):
        await bounded_retrieve('Define the fictional value.',retrieve=fetch,
            assess=AsyncMock(return_value=Assessment(sufficient=True,missing_core=[],
                definition_support='related_only')),reserve=reserve)
    assert fetch.await_count==1
