from unittest.mock import Mock
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts/eval'))
from batch_agentic_judges import pending_old_entries, submit_once


def test_frozen_evaluation_sources_rejected_before_paid_calls(tmp_path):
    import hashlib
    from benchmark_agentic_rag import verify_frozen_sources
    candidate=tmp_path/'candidate.py';candidate.write_text('frozen')
    runner=tmp_path/'runner.py';runner.write_text('runner')
    neighbor=tmp_path/'neighbor.py';neighbor.write_text('neighbor')
    paths={'candidate_source_sha256':candidate,'benchmark_source_sha256':runner,'neighbor_source_sha256':neighbor}
    protocol={key:hashlib.sha256(path.read_bytes()).hexdigest() for key,path in paths.items()}
    verify_frozen_sources(protocol,paths)
    for key,path in paths.items():
        original=path.read_bytes()
        path.write_text('changed')
        with pytest.raises(ValueError,match=key):verify_frozen_sources(protocol,paths)
        path.write_bytes(original)


def test_provider_circuit_stops_credits_and_daily_quota_but_not_transient_rate_limit():
    from benchmark_agentic_rag import ProviderCircuit,safe_error
    for text in ['402 prepaid depleted','401 invalid key','429 RequestsPerDay exhausted']:
        circuit=ProviderCircuit()
        circuit.observe(safe_error(RuntimeError(text)))
        assert circuit.blocked
    circuit=ProviderCircuit()
    circuit.observe(safe_error(RuntimeError('429 RequestsPerMinute exhausted')))
    assert not circuit.blocked


@pytest.mark.asyncio
async def test_model_error_callback_preserves_provider_cause_without_secret():
    from benchmark_agentic_rag import Usage,active
    row={};token=active.set(row)
    try:
        await Usage().on_llm_error(RuntimeError('402 private key details'),run_id=None)
        assert row['provider_error']['reason']=='credits'
        assert 'private key details' not in str(row)
    finally:
        active.reset(token)


@pytest.mark.asyncio
@pytest.mark.parametrize('failure_phase',['retrieval','judge'])
async def test_paid_comparison_stops_queued_cases_after_credit_failure(tmp_path,monkeypatch,failure_phase):
    import hashlib,json
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    import dotenv
    import benchmark_agentic_rag as benchmark
    from app.core import config,llm
    from app.rag import retriever,qa,agentic
    from google import genai
    from google.genai import _api_client
    cases=[{'attempt_id':f'ag-{i:03}','question':'q','gold_answer':'synthetic','acceptable_evidence':[]} for i in range(100)]
    raw=json.dumps(cases).encode()
    (tmp_path/'cases.json').write_bytes(raw)
    (tmp_path/'protocol.json').write_text(json.dumps({'dataset_sha256':hashlib.sha256(raw).hexdigest()}))
    chunks=tmp_path/'chunks.pkl';chunks.write_bytes(b'synthetic')
    settings=SimpleNamespace(rag_chunks_path=str(chunks),get_chunks_path=lambda:str(chunks),
        pinecone_namespace='synthetic',embedding_model='test',gemini_model='test',
        gemini_simple_model='test',gemini_eval_model='test',model_routing_enabled=False)
    monkeypatch.setattr(dotenv,'load_dotenv',lambda *a,**kw:None)
    monkeypatch.setattr(config,'get_settings',lambda:settings)
    judge=Mock()
    judge.with_structured_output.return_value.ainvoke=AsyncMock(side_effect=RuntimeError('402 prepaid depleted'))
    monkeypatch.setattr(llm,'get_chat_model',lambda **kw:judge)
    monkeypatch.setattr(retriever,'get_vector_store',lambda:None)
    fetch=(AsyncMock(side_effect=RuntimeError('402 prepaid depleted')) if failure_phase=='retrieval' else
           AsyncMock(return_value={'grounded':True,'docs':[],'context':'source','max_score':.9}))
    monkeypatch.setattr(retriever,'retrieve',fetch)
    monkeypatch.setattr(qa,'answer_from_knowledge',AsyncMock(return_value={'answer':'synthetic','context':'source'}))
    monkeypatch.setattr(agentic,'model_assessment',AsyncMock(return_value=agentic.Assessment(sufficient=True,missing_core=[])))
    original_sleep=benchmark.asyncio.sleep
    async def fast_sleep(delay):await original_sleep(0)
    monkeypatch.setattr(benchmark.asyncio,'sleep',fast_sleep)
    original=(retriever._translate_llm,genai.models.Models.embed_content,_api_client.BaseApiClient.request)
    try:
        with pytest.raises(SystemExit) as stopped:
            await benchmark.main(SimpleNamespace(output=str(tmp_path),baseline_source=None,defer_judge=failure_phase!='judge'))
        assert stopped.value.code==2
        assert 1<=fetch.await_count<=3
        rows=[json.loads(v) for v in (tmp_path/'attempts.jsonl').read_text().splitlines()]
        error_field='error' if failure_phase=='retrieval' else 'judge_error'
        assert len(rows)<200 and all(r[error_field]['reason']=='credits' for r in rows)
        status=json.loads((tmp_path/'run-status.json').read_text())
        assert status['provider_blocked'] and status['unstarted_slots']>=197
    finally:
        retriever._translate_llm,genai.models.Models.embed_content,_api_client.BaseApiClient.request=original

def test_old_batch_retries_only_unjudged_successful_answers():
    cases=[{'attempt_id':'a','question':'q','gold_answer':'g'}]
    attempts=[{'attempt_id':'a','condition':c,'status':status,'answer':'answer','context':'evidence'} for c,status in [('baseline','completed'),('agentic','failed')]]
    valid=[{'attempt_id':'a','condition':'baseline','status':'completed','correct':False,'faithful':True,'reason':'valid negative'}]
    assert pending_old_entries(cases,attempts,valid)==[]
    assert len(pending_old_entries(cases,attempts,[]))==1

def test_unknown_submission_outcome_cannot_create_duplicate(tmp_path):
    client=Mock(); client.batches.create.side_effect=TimeoutError()
    path=tmp_path/'job.json'
    with pytest.raises(TimeoutError): submit_once(client,path,'model',[],[])
    with pytest.raises(ValueError): submit_once(client,path,'model',[],[])
    assert client.batches.create.call_count==1

def test_submission_claim_is_atomic_even_if_exists_check_races(tmp_path,monkeypatch):
    path=tmp_path/'job.json'; path.write_text('already claimed')
    original=Path.exists
    monkeypatch.setattr(Path,'exists',lambda self:False if self==path else original(self))
    client=Mock()
    with pytest.raises((FileExistsError,ValueError)): submit_once(client,path,'model',[],[])
    client.batches.create.assert_not_called()

def test_batch_cannot_credit_failed_serving_side(tmp_path):
    from types import SimpleNamespace as NS
    from batch_agentic_judges import collect
    import json
    payload={'A':{'serving_status':'failed'},'B':{'serving_status':'completed'}}
    path=tmp_path/'job.json'
    path.write_text(json.dumps({'name':'batches/synthetic','model':'gemini-3.1-pro-preview',
        'entries':[{'key':'pair|ag-000','kind':'pair','attempt_id':'ag-000','payload':payload,'mapping':{'A':'baseline','B':'agentic'}}]}))
    body=NS(text=json.dumps({'A':{'correct':True,'faithful':True,'reason':'wrong credit'},'B':{'correct':True,'faithful':True,'reason':'valid'}}),
            candidates=[],usage_metadata=NS(prompt_token_count=10,candidates_token_count=20,thoughts_token_count=5,cached_content_token_count=0))
    job=NS(state=NS(value='JOB_STATE_SUCCEEDED'),dest=NS(inlined_responses=[NS(metadata={'key':'pair|ag-000'},response=body)]))
    client=Mock(); client.batches.get.return_value=job
    collect(client,path)
    rows=[json.loads(v) for v in path.with_suffix('.grades.jsonl').read_text().splitlines()]
    assert rows[0]['status']=='not_applicable_serving_failed' and rows[0]['correct'] is False
    assert rows[1]['correct'] is True
    assert rows[1]['known_cost_usd']==pytest.approx(.00008)
