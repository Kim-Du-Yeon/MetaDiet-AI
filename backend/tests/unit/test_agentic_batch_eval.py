from unittest.mock import Mock
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts/eval'))
from batch_agentic_judges import pending_old_entries, submit_once

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
