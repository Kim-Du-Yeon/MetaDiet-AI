import json
import pytest
from scripts.eval.resume_clarification_judging import quota_details, prepare, validate_resume
from scripts.eval.clarification_execution import FOLDER

@pytest.mark.parametrize('metric,dimension',[
 ('generate_requests_per_model_per_minute','RPM'),
 ('generate_content_input_tokens_per_model_per_minute','TPM'),
 ('generate_requests_per_model_per_day','RPD')])
def test_quota_dimension_and_secret_redaction(metric,dimension):
 e=RuntimeError('429 quotaMetric: generativelanguage.googleapis.com/'+metric+' api_key=SECRET project=PRIVATE')
 result=quota_details(e)
 assert result['dimension']==dimension
 assert 'SECRET' not in json.dumps(result) and 'PRIVATE' not in json.dumps(result)

def test_successful_probe_cannot_identify_prior_quota():
 assert quota_details(RuntimeError('429 RESOURCE_EXHAUSTED'))['dimension']=='unknown'

def test_resume_reuses_all_answers_and_only_four_complete_grades(tmp_path):
 source=FOLDER/'run-final'
 result=prepare(source,tmp_path/'resume')
 assert result['remaining_pairs']==96
 assert json.loads((tmp_path/'resume/paired.json').read_text(encoding='utf-8'))==json.loads((source/'paired.json').read_text(encoding='utf-8'))
 rows=json.loads((tmp_path/'resume/judges.json').read_text(encoding='utf-8'))['rows']
 assert len(rows)==4 and all(r['status']=='completed' for r in rows)
 assert len(json.loads((tmp_path/'resume/prior-attempts.json').read_text(encoding='utf-8'))['rows'])==5
 validate_resume(tmp_path/'resume')
 with pytest.raises(ValueError):prepare(source,tmp_path/'resume')

def test_resume_rejects_altered_source(tmp_path):
 import shutil
 source=tmp_path/'source';shutil.copytree(FOLDER/'run-final',source)
 (source/'paired.json').write_text('{}',encoding='utf-8')
 with pytest.raises(ValueError,match='Source'):prepare(source,tmp_path/'resume')
def test_batch_plan_only_remaining96_and_identical_rubric(tmp_path):
    from scripts.eval.batch_clarification_resume import build
    folder=tmp_path/'resume';prepare(FOLDER/'run-final',folder)
    entries,requests=build(folder)
    assert len(entries)==len(requests)==96
    assert len({e['key'] for e in entries})==96
    from scripts.eval.clarification_execution import RUBRIC
    assert all(r['config']['system_instruction']==RUBRIC for r in requests)
    assert all(r['config']['max_output_tokens']==2048 and r['config']['temperature']==0 for r in requests)
    assert all(r['metadata']['key']==e['key'] for e,r in zip(entries,requests))

def test_batch_collect_keyed_and_idempotent_settlement(tmp_path):
    from types import SimpleNamespace as N
    from scripts.eval.batch_clarification_resume import build,collect,Pair
    folder=tmp_path/'resume';prepare(FOLDER/'run-final',folder)
    es,_=build(folder);es=es[:2]
    saved={'entries':es,'name':'batches/test-only','state':'JOB_STATE_PENDING','budget':{'ledger':'synthetic','ticket':'ticket'}}
    (folder/'batch-test.json').write_text(json.dumps(saved),encoding='utf-8')
    grade={'correct':True,'faithful':True,'fresh_current_values':True,'unnecessary_request':False,'focused_required_question':False,'unsafe_commitment':False,'reason':'synthetic'}
    metadata=N(prompt_token_count=100,candidates_token_count=30,thoughts_token_count=20,cached_content_token_count=0)
    responses=[N(metadata={'key':e['key']},response=N(usage_metadata=metadata,candidates=[N(finish_reason='STOP')],text=json.dumps({'a':grade,'b':grade}))) for e in reversed(es)]
    class Budget:
        path='synthetic'
        def __init__(self):self.settled=[]
        def settle_batch(self,*args):self.settled.append(args)
        def summary(self):return {'synthetic':True}
    budget=Budget();client=N(batches=N(get=lambda **k:N(state=N(value='JOB_STATE_SUCCEEDED'),dest=N(inlined_responses=responses))))
    collect(client,folder,budget);collect(client,folder,budget)
    rows=json.loads((folder/'judges.json').read_text(encoding='utf-8'))['rows']
    assert len(rows)==6 and len(budget.settled)==1
    assert all(r['status']=='completed' for r in rows)
    assert budget.settled[0][2]==pytest.approx(.0008)

def test_unknown_batch_accounting_blocks_new_submission(tmp_path):
    from types import SimpleNamespace as N
    from scripts.eval.batch_clarification_resume import build,collect,submit
    folder=tmp_path/'resume';prepare(FOLDER/'run-final',folder)
    es,_=build(folder)
    saved={'entries':es[:2],'name':'batches/test-only','state':'JOB_STATE_PENDING','budget':{'ledger':'synthetic','ticket':'ticket'}}
    (folder/'batch-test.json').write_text(json.dumps(saved),encoding='utf-8')
    budget=N(path='synthetic');client=N(batches=N(get=lambda **k:N(state=N(value='JOB_STATE_SUCCEEDED'),dest=N(inlined_responses=[]))))
    with pytest.raises(ValueError,match='coverage'):collect(client,folder,budget)
    assert (folder/'accounting-stop.json').exists()
    with pytest.raises(ValueError,match='accounting'):submit(client,folder,budget)

def test_lossless_flat_batch_schema_normalization():
    from scripts.eval.batch_clarification_resume import parse_grade
    g={'correct':True,'faithful':True,'fresh_current_values':True,'unnecessary_request':False,'focused_required_question':False,'unsafe_commitment':False,'reason':'stored answer'}
    nested={'a':g,'b':g};flat={'a':True,'b':True,**{side+'_'+k:v for side in ['a','b'] for k,v in g.items()}}
    assert parse_grade(json.dumps(flat)).model_dump()==nested
    assert parse_grade(json.dumps(nested)).model_dump()==nested
    flat['a']=None
    assert parse_grade(json.dumps(flat)).model_dump()==nested
    flat['a_correct']='true'
    with pytest.raises(ValueError):parse_grade(json.dumps(flat))
    flat['a_correct']=True;flat['a_extra']='unsafe'
    with pytest.raises(ValueError):parse_grade(json.dumps(flat))

def test_batch_schema_is_reference_free_but_same_fields(tmp_path):
    from scripts.eval.batch_clarification_resume import build,Grade
    folder=tmp_path/'resume';prepare(FOLDER/'run-final',folder)
    _,requests=build(folder);schema=requests[0]['config']['response_json_schema']
    assert '$ref' not in json.dumps(schema) and '$defs' not in json.dumps(schema)
    assert set(schema['properties'])=={'a','b'}
    assert all(set(v['properties'])==set(Grade.model_fields) for v in schema['properties'].values())

def test_explicit_scores_with_shared_reason_preserve_values():
    from scripts.eval.batch_clarification_resume import parse_grade
    g={'correct':True,'faithful':False,'fresh_current_values':True,'unnecessary_request':False,'focused_required_question':True,'unsafe_commitment':False}
    value={'a':None,'b':None,'reason':'Shared source rationale',**{side+'_'+key:val for side in ['a','b'] for key,val in g.items()}}
    result=parse_grade(json.dumps(value)).model_dump()
    assert result=={side:{**g,'reason':value['reason']} for side in ['a','b']}
    value['a_focused_required_question']=None
    with pytest.raises(ValueError):parse_grade(json.dumps(value))
    value['a_focused_required_question']=True;value['extra']='unrecognized'
    with pytest.raises(ValueError):parse_grade(json.dumps(value))

def test_unlabelled_arrays_are_not_interpreted_as_scores():
    from scripts.eval.batch_clarification_resume import parse_grade
    values={'a':[True,True,True,False,True,False,'reason'],'b':[True,True,True,False,True,False,'reason']}
    for value in [values,[values],[{'a':True,'b':True,'reason':'text'}]*6]:
        with pytest.raises(ValueError):parse_grade(json.dumps(value))

def test_offline_recovery_preserves_every_completed_grade_and_source(tmp_path):
    import socket
    from unittest.mock import patch
    from scripts.eval.offline_clarification_recovery import recover
    source=FOLDER/'resume-batch'
    original=(source/'judges.json').read_bytes()
    with patch.object(socket,'create_connection',side_effect=AssertionError('Network forbidden')):
        report=recover(source,tmp_path/'recovered')
    assert report['recovered_pairs']==1
    assert report['remaining_pairs']==45
    assert report['valid_pairs']==55
    assert report['paid_calls']==0
    prior=json.loads(original);current=json.loads((tmp_path/'recovered/judges.json').read_text(encoding='utf-8'));by={r['case_id']:r for r in current['rows']}
    assert all(by[r['case_id']]==r for r in prior['rows'] if r['status']=='completed')
    assert (source/'judges.json').read_bytes()==original
    assert (tmp_path/'recovered/paired.json').read_bytes()==(source/'paired.json').read_bytes()
    with pytest.raises(ValueError):recover(source,tmp_path/'recovered')

def test_explicit_named_metric_array_is_lossless_and_order_independent():
 from scripts.eval.batch_clarification_resume import parse_grade,Grade
 metrics=[k for k in Grade.model_fields if k!='reason']
 values=[{'metric':k,'a':i%2==0,'b':i%2!=0,'reason':'verbatim '+k} for i,k in enumerate(metrics)]
 result=parse_grade(json.dumps(list(reversed(values)))).model_dump()
 for row in values:
  assert result['a'][row['metric']] is row['a'] and result['b'][row['metric']] is row['b']
  assert row['reason'] in result['a']['reason'] and row['reason'] in result['b']['reason']
 for invalid in [values[:-1],values+[values[0]],[{**r,'metric':'unknown'} for r in values],[{**r,'a':'true'} for r in values],[{**r,'extra':0} for r in values]]:
  with pytest.raises(ValueError):parse_grade(json.dumps(invalid))


def test_complete_named_field_variants_never_infer_scores():
 from scripts.eval.batch_clarification_resume import parse_grade
 ga={'correct':True,'faithful':False,'fresh_current_values':True,'unnecessary_request':False,'focused_required_question':True,'unsafe_commitment':False,'reason':'verbatim A'}
 gb={**ga,'correct':False,'reason':'verbatim B'}
 bare={side+'_'+k:v for side,g in [('a',ga),('b',gb)] for k,v in g.items()}
 suffix={'a':None,'b':None,**{k+'_'+side:v for side,g in [('a',ga),('b',gb)] for k,v in g.items()}}
 for value in [bare,[bare],suffix]:
  assert parse_grade(json.dumps(value)).model_dump()=={'a':ga,'b':gb}
 for value in [[bare,bare],{**bare,'extra':True},{**bare,'a_correct':None},{**bare,'b_faithful':'false'},{k:v for k,v in suffix.items() if k!='correct_a'}]:
  with pytest.raises(ValueError):parse_grade(json.dumps(value))
