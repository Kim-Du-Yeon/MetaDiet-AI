import json
import pytest


def test_prepare_disjoint_dev24_and_preserves_old_sources(tmp_path):
    from scripts.eval.clarification_v3 import prepare,read,ROOT
    p=tmp_path/'experiment';prepare(p)
    cases=read(p/'development.json');frozen=read(p/'frozen.json')
    assert len(cases)==24 and len(frozen)==100
    assert not {c['id'] for c in cases}&{c['id'] for c in frozen}
    assert not {json.dumps(c,sort_keys=True) for c in cases}&{json.dumps(c,sort_keys=True) for c in frozen}
    candidate=read(p/'candidate.json');old=read(p/'source-paired.json')
    changed=[k for k,v in candidate['texts'].items() if v!=old['prompt_snapshots']['v2']['texts'][k]]
    assert set(changed)=={'team.base','team.compact_followup'}
    assert candidate['kind']=='evaluation_only' and candidate['origin_commit'] is None
    from app.core.prompt_release_control import validate_snapshot
    with pytest.raises(ValueError):validate_snapshot(candidate)
    assert read(p/'protocol.json')['old_100_exposed'] is True
    with pytest.raises(ValueError):prepare(p)


def test_full_fixture_truth_distinguishes_daily_and_meal_fields():
    from scripts.eval.clarification_v3 import fixture_truth
    c={'verified_context':{'calories':814,'target':2122}}
    truth=fixture_truth(c)
    assert truth['intake']['calories']==814
    assert truth['intake']['meals'][0]['meal_type']=='lunch'
    assert truth['profile']['strategy']['daily_calories']==2122


def test_three_side_flat_contract_is_strict_and_lossless():
    from scripts.eval.clarification_v3 import grade_schema,parse_grades,format_system,FIELDS
    value={s+'_'+k:('verbatim '+s if k=='reason' else (i+(s=='b'))%2==0) for s in ['a','b','c'] for i,k in enumerate(FIELDS)}
    got=parse_grades(json.dumps(value),3)
    assert set(got)=={'a','b','c'} and len(grade_schema(3)['properties'])==21
    assert got['b']['correct']==value['b_correct'] and got['c']['reason']=='verbatim c'
    assert 'c_correct' in format_system(3)
    for bad in [{**value,'a_correct':None},{**value,'c_faithful':'true'},list(value.values()),{k:v for k,v in value.items() if k!='c_reason'}]:
        with pytest.raises(ValueError):parse_grades(json.dumps(bad),3)
    with pytest.raises(ValueError):parse_grades(json.dumps(value)[:-1]+',"a_correct":false}',3)


def test_reuse_requires_exact_input_and_identity(tmp_path):
    from scripts.eval.clarification_v3 import prepare,reused_report
    p=tmp_path/'experiment';prepare(p);r=reused_report(p)
    assert len(r['rows'])==200
    assert {a['condition'] for a in r['rows']}=={'v1','v2'}
    candidate=json.loads((p/'candidate.json').read_text(encoding='utf-8'));candidate['texts']['team.base']+='changed'
    (p/'candidate.json').write_text(json.dumps(candidate),encoding='utf-8')
    with pytest.raises(ValueError):reused_report(p)


def test_new_gate_rejects_ungraded_and_unsafe_and_is_not_old_gate():
    from scripts.eval.clarification_v3 import select
    def row():return {'expected':100,'judged':100,'passed':100,'unsafe_commitments':0,'required_recall_numerator':50,'fresh':100,'no_write':100,'correct_faithful':100,'unnecessary_requests':0,'unnecessary_all':0,'generation_failures':0,'usage_complete':True,'p95_ms':100,'cost_usd':.1}
    values={k:row() for k in ['v1','v2','v3']};values['v1']['passed']=98;values['v2']['passed']=95
    assert select(values)['evaluation_preferred']=='v3'
    values['v3']['unsafe_commitments']=1
    assert select(values)['evaluation_preferred']=='v1'
    values['v3']=row();values['v3']['judged']=99
    assert select(values)['evaluation_preferred']=='v1'


def test_blinded_threeway_requests_rotate_and_bind_truth(tmp_path):
    from scripts.eval.clarification_v3 import prepare,read
    from scripts.eval.run_clarification_v3 import initialize,build_judges
    from scripts.eval.clarification_execution import request_spec
    from scripts.eval.clarification_cases import request_key
    from app.core.prompt_release_control import _snapshot
    p=tmp_path/'experiment';prepare(p);folder=p/'main';report=initialize(p,False)
    old=read(p/'source-paired.json')
    cases={c['id']:c for c in read(p/'frozen.json')};candidate=read(p/'candidate.json')
    for row in old['rows']:
        if row['condition']=='v1':report['rows'].append({**row,'condition':'v3','input_key':request_key(cases[row['case_id']],request_spec(candidate)),'prompt_metadata':_snapshot(candidate).metadata()})
    (folder/'answers.json').write_text(json.dumps(report),encoding='utf-8')
    es,requests=build_judges(p,False)
    assert len(es)==len(requests)==100
    assert len(set(tuple(e['mapping'].values()) for e in es))==3
    assert all(set(e['mapping'].values())=={'v1','v2','v3'} for e in es)
    assert all(len(r['config']['response_json_schema']['properties'])==21 for r in requests)
    payload=json.loads(requests[0]['contents'][0]['parts'][0]['text'])
    assert payload['fixture_truth']['intake']['meals'][0]['meal_type']=='lunch'
    assert not es[0]['answer_binding']==es[1]['answer_binding']

    report['rows'][-1]['input_key']='wrong'
    (folder/'answers.json').write_text(json.dumps(report),encoding='utf-8')
    with pytest.raises(ValueError,match='input'):initialize(p,False)


@pytest.mark.asyncio
async def test_offline_audit_cannot_seed_paid_answers(tmp_path):
    from scripts.eval.clarification_v3 import prepare,read
    from scripts.eval.run_clarification_v3 import audit_routes
    p=tmp_path/'experiment';prepare(p)
    await audit_routes(p)
    assert not (p/'development/answers.json').exists()
    assert len(read(p/'offline-route-audit.json')['rows'])==48


def test_persistent_stop_prevents_resume(tmp_path):
    from scripts.eval.run_clarification_v3 import ensure_running
    folder=tmp_path/'development';folder.mkdir()
    (folder/'capacity-stop.json').write_text('{}')
    with pytest.raises(ValueError,match='review'):ensure_running(tmp_path,True)


def test_copied_historical_answer_bytes_are_immutable(tmp_path):
    from scripts.eval.clarification_v3 import prepare,reused_report,read
    p=tmp_path/'experiment';prepare(p)
    value=read(p/'source-paired.json');value['rows'][0]['answer']='tampered answer'
    (p/'source-paired.json').write_text(json.dumps(value),encoding='utf-8')
    with pytest.raises(ValueError,match='evidence'):reused_report(p)


def test_native_batch_prepaid_context_matches_transport(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from scripts.eval import eval_budget
    from scripts.eval import run_clarification_v3 as runner
    from scripts.eval import batch_agentic_judges as helper
    monkeypatch.setitem(helper.submit_once.__globals__,'batch_cost',lambda *args:.1)
    observed=[]
    class Budget:
        path='synthetic-ledger'
        def reserve(self,*args):return 'one-ticket'
        def bind_batch(self,*args):pass
    def create(**kw):
        observed.append(eval_budget.BATCH_RESERVATION.get())
        return SimpleNamespace(name='one-batch',state=SimpleNamespace(value='JOB_STATE_PENDING'))
    client=SimpleNamespace(batches=SimpleNamespace(create=create))
    runner.submit_budgeted(client,tmp_path/'job.json','gemini-3.1-pro-preview',[],[],Budget())
    assert observed[0]['ticket']=='one-ticket'
