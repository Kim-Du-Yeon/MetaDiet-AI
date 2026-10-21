import asyncio
from unittest.mock import AsyncMock
import pytest
from app.rag.agentic import bounded_retrieve, Assessment, Limits


def result(grounded=True):
    return {"grounded": grounded, "context": "source evidence", "docs": [], "max_score": .8}

@pytest.mark.asyncio
async def test_sufficient_stops_and_keeps_original_result():
    fetch = AsyncMock(return_value=result())
    assess = AsyncMock(return_value=Assessment(sufficient=True, rewrite=""))
    r = await bounded_retrieve("original", retrieve=fetch, assess=assess)
    assert r["grounded"] and fetch.await_count == 1
    assert r["agentic"]["stop_reason"] == "sufficient"

@pytest.mark.asyncio
async def test_rewrites_once_and_grades_original_question():
    fetch = AsyncMock(return_value=result())
    assess = AsyncMock(side_effect=[Assessment(sufficient=False, rewrite="better query"), Assessment(sufficient=True)])
    r = await bounded_retrieve("original", retrieve=fetch, assess=assess)
    assert fetch.await_count == 2
    assert [c.args[0] for c in assess.await_args_list] == ["original", "original"]
    assert r["agentic"]["rounds"] == 2

@pytest.mark.asyncio
async def test_similarity_cannot_be_overruled_by_model():
    r = await bounded_retrieve("original", retrieve=AsyncMock(return_value=result(False)),
        assess=AsyncMock(return_value=Assessment(sufficient=True)))
    assert not r["grounded"] and not r["context"]

@pytest.mark.asyncio
async def test_duplicate_and_exhaustion_fail_closed():
    for rewrite, reason, count in [(" original ", "duplicate_query", 1), ("new query", "round_limit", 2)]:
        fetch = AsyncMock(return_value=result())
        r = await bounded_retrieve("original", retrieve=fetch,
            assess=AsyncMock(return_value=Assessment(sufficient=False, rewrite=rewrite)))
        assert not r["grounded"] and fetch.await_count == count
        assert r["agentic"]["stop_reason"] == reason

@pytest.mark.asyncio
async def test_error_and_deadline_do_not_expose_unassessed_evidence():
    async def slow(*args):
        await asyncio.sleep(.1)
    for assessor, limits, reason in [(AsyncMock(side_effect=ValueError("private")), Limits(), "controller_error"),
                                    (slow, Limits(timeout_seconds=.01), "timeout")]:
        r = await bounded_retrieve("original", retrieve=AsyncMock(return_value=result()), assess=assessor, limits=limits)
        assert not r["grounded"] and r["agentic"]["stop_reason"] == reason
        assert "private" not in str(r)

@pytest.mark.asyncio
async def test_budget_reservations_and_cancellation():
    reserve = AsyncMock()
    await bounded_retrieve("한국어", retrieve=AsyncMock(return_value=result()),
        assess=AsyncMock(return_value=Assessment(sufficient=True)), reserve=reserve)
    assert [c.args[0] for c in reserve.await_args_list] == ["model", "model"]
    with pytest.raises(asyncio.CancelledError):
        await bounded_retrieve("original", retrieve=AsyncMock(side_effect=asyncio.CancelledError()), assess=AsyncMock())

def test_hard_limits():
    with pytest.raises(ValueError):
        Limits(max_rounds=3)

@pytest.mark.asyncio
async def test_shared_budget_exhaustion_propagates():
    from app.agents.runtime import ExecutionStopped
    with pytest.raises(ExecutionStopped):
        await bounded_retrieve("original", retrieve=AsyncMock(return_value=result()),
            assess=AsyncMock(), reserve=AsyncMock(side_effect=ExecutionStopped("model_call_limit")))

@pytest.mark.asyncio
async def test_team_enabled_path_charges_and_preserves_source(monkeypatch):
    from app.core.config import get_settings
    from app.agents.team import DietTeam, Query
    from app.rag import agentic, retriever
    from langchain_core.documents import Document
    monkeypatch.setattr(get_settings(), "agentic_rag_enabled", True)
    captured={}
    async def loop(question, **kwargs):
        captured.update(kwargs)
        await kwargs['reserve']('model')
        return {'grounded': True, 'docs': [Document(page_content='valid', metadata={'source_file':'guide.pdf','page':4})],
                'agentic':{'rounds':1,'stop_reason':'sufficient'}}
    monkeypatch.setattr(agentic, 'bounded_retrieve', loop)
    team=DietTeam({'user_id':'synthetic','message':'nutrition evidence'}, model_factory=lambda:None,
                  db=object(), repository=AsyncMock())
    r=await team.search_evidence(Query(query='nutrition evidence'))
    assert r['evidence'][0]['source']=='guide.pdf'
    assert team.budget.model_calls==1
    assert captured['retrieve'] is retriever.retrieve
    assert team.events[-1]['stop_reason']=='sufficient'

def test_progress_reports_actual_loop_stages():
    from app.agents.execution_stream import progress_for_runtime_event
    for stage in ['retrieve','evaluate','rewrite','research']:
        assert progress_for_runtime_event('agentic_rag_stage',stage=stage)['phase']=='evidence_'+stage
    assert progress_for_runtime_event('agentic_rag_stage',stage='invented') is None

@pytest.mark.asyncio
async def test_only_exact_assessed_excerpt_can_reach_answer():
    from langchain_core.documents import Document
    doc=Document(page_content='A'*7000+'UNASSESSED',metadata={'source_file':'guide','page':3})
    async def assessor(question, value):
        assert len(value['context'])<=6000
        assert 'UNASSESSED' not in value['docs'][0].page_content
        return Assessment(sufficient=True)
    r=await bounded_retrieve('question',retrieve=AsyncMock(return_value={**result(),
        'docs':[doc],'context_docs':[doc],'context':'A'*6000}),assess=assessor)
    assert r['grounded']
    assert 'UNASSESSED' not in r['docs'][0].page_content
    assert r['docs'][0].metadata==doc.metadata

@pytest.mark.asyncio
async def test_retrieval_failure_is_distinct_from_controller_failure():
    r=await bounded_retrieve('question',retrieve=AsyncMock(side_effect=OSError('private')),assess=AsyncMock())
    assert r['agentic']['stop_reason']=='retrieval_error'

@pytest.mark.asyncio
@pytest.mark.parametrize('reason',['retrieval_error','controller_error','timeout'])
async def test_team_outage_suppresses_distinct_followup_queries(monkeypatch,reason):
    from app.core.config import get_settings
    from app.agents.team import DietTeam, Query
    from app.rag import agentic
    monkeypatch.setattr(get_settings(),'agentic_rag_enabled',True)
    loop=AsyncMock(return_value={'grounded':False,'docs':[],
        'agentic':{'stop_reason':reason,'rounds':1}})
    monkeypatch.setattr(agentic,'bounded_retrieve',loop)
    team=DietTeam({'user_id':'synthetic','message':'evidence'},model_factory=lambda:None,
                  db=object(),repository=AsyncMock())
    first=await team.search_evidence(Query(query='first'))
    second=await team.search_evidence(Query(query='different'))
    assert first['status']==second['status']=='search_unavailable'
    assert loop.await_count==1

@pytest.mark.asyncio
async def test_controller_trace_pins_own_prompt_version(monkeypatch):
    from app.rag.agentic import model_assessment, PROMPT_SHA256, PROMPT_VERSION
    from app.core import llm
    class Model:
        def with_structured_output(self,*args,**kwargs): return self
        async def ainvoke(self,messages,config):
            assert config['metadata']['agentic_prompt_sha256']==PROMPT_SHA256
            assert config['metadata']['agentic_prompt_version']==PROMPT_VERSION
            assert config['metadata']['request_id']=='synthetic'
            return {'parsed':Assessment(sufficient=True),'parsing_error':None}
    monkeypatch.setattr(llm,'get_chat_model',lambda **kwargs:Model())
    assert (await model_assessment('question',result(),config={'metadata':{'request_id':'synthetic'}})).sufficient

@pytest.mark.asyncio
async def test_research_preserves_initial_grounded_documents_and_adds_new_evidence():
    from langchain_core.documents import Document
    original=[Document(page_content=f'original-{i}',metadata={'source_file':'original.pdf','page':i}) for i in range(4)]
    fresh=[Document(page_content=f'new-{i}',metadata={'source_file':'new.pdf','page':i}) for i in range(4)]
    fetch=AsyncMock(side_effect=[{**result(),'docs':original,'context_docs':original},
                               {**result(),'docs':fresh,'context_docs':fresh}])
    assess=AsyncMock(side_effect=[Assessment(sufficient=False,rewrite='rewrite'),Assessment(sufficient=True)])
    r=await bounded_retrieve('question',retrieve=fetch,assess=assess)
    assert [d.page_content for d in r['docs']][:4]==[d.page_content for d in original]
    assert any(d.page_content=='new-0' for d in r['docs'])
    assert len(r['context'])<=6000
    assert r['agentic']['retained_initial_documents']==4

@pytest.mark.asyncio
async def test_low_score_research_cannot_replace_initial_grounded_evidence():
    from langchain_core.documents import Document
    initial=Document(page_content='supported',metadata={'source_file':'good.pdf','page':1})
    unsafe=Document(page_content='low score',metadata={'source_file':'bad.pdf','page':1})
    fetch=AsyncMock(side_effect=[{**result(),'docs':[initial]}, {**result(False),'docs':[unsafe]}])
    r=await bounded_retrieve('question',retrieve=fetch,
        assess=AsyncMock(side_effect=[Assessment(sufficient=False,rewrite='rewrite'),Assessment(sufficient=True)]))
    assert r['grounded'] and [d.page_content for d in r['docs']]==['supported']
