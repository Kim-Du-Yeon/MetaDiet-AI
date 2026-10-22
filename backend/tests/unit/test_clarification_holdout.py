import copy
import pytest


def test_new100_disjoint_balanced_and_frozen():
    from scripts.eval.clarification_holdout import cases,assert_novel,cohort_sha,COHORT_SHA
    rows=cases();assert len(rows)==len({c['question'] for c in rows})==100
    assert sum(c['expected']=='ask_required' for c in rows)==50
    assert_novel(rows);assert cohort_sha(rows)==COHORT_SHA
    assert all('calculation_mode' not in c['verified_context'] for c in rows)


def test_two_prompt_scope_fail_closed():
    from scripts.eval.clarification_holdout import supported
    from scripts.eval.clarification_v3 import read
    from pathlib import Path
    root=Path(__file__).resolve().parents[3]
    base=read(root/'docs/prompt_control/approved-release.json')
    snap=read(root/'docs/prompt_control/clarification-balanced/v4-calculation-mode-20261022/candidate.json')
    supported({'baseline':base,'snapshot':snap})
    snap=copy.deepcopy(snap);snap['texts']['team.role.goal']+='changed'
    with pytest.raises(ValueError):supported({'baseline':base,'snapshot':snap})


def test_holdout_gate_preserves_quality_and_required_questions():
    from scripts.eval.clarification_holdout import select
    def row():return dict(expected=100,judged=100,generation_failures=0,usage_complete=True,correct=100,faithful=100,passed=100,required_recall_numerator=50,unsafe_commitments=0,fresh=100,no_write=100,unnecessary_all=0,p95_ms=100,cost_usd=.1)
    v={'v1':row(),'v4':row()};assert select(v)['holdout_passed']
    v['v4']['required_recall_numerator']=48;assert not select(v)['holdout_passed']
    v['v4']=row();v['v4']['unnecessary_all']=1;assert not select(v)['holdout_passed']
    v['v4']=row();v['v4']['faithful']=97;assert not select(v)['holdout_passed']


def _approval_fixture(tmp_path):
    import json
    from pathlib import Path
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from app.core.prompt_release_control import sign_snapshot,digest,_snapshot
    from scripts.eval import clarification_holdout as h,run_clarification_holdout as runner
    from scripts.eval.clarification_execution import request_spec,price_usage
    from scripts.eval.clarification_cases import request_key
    from scripts.eval.clarification_v3 import fixture_truth,format_system
    from scripts.eval.cache_artifacts import save_json
    import hashlib
    key=Ed25519PrivateKey.generate();base=h.read(h.ROOT/'docs/prompt_control/approved-release.json')
    base=sign_snapshot(_snapshot(base),key,report_sha256='a'*64)
    candidate={'schema_version':1,'baseline':base,'snapshot':h.read(h.SOURCE/'candidate.json')}
    candidate['snapshot']['kind']='evaluation'
    save_json(tmp_path/'candidate.json',candidate);save_json(tmp_path/'frozen.json',h.cases())
    save_json(tmp_path/'protocol.json',{'suite':h.SUITE,'code_sha256':h.code_sha(),'cases_sha256':h.COHORT_SHA,'candidate_sha256':digest(candidate),'historical_sha256':{n:h.sha(h.SOURCE/n) for n in ['main/summary.json']}})
    r=runner.initialize(tmp_path,False);(tmp_path/'main/model-inputs').mkdir();(tmp_path/'main/raw-judges').mkdir();grades=[];usage={'input_tokens':10,'output_tokens':5};system=format_system(2)
    for i,c in enumerate(h.cases()):
        mapping=dict(zip('ab',['v1','v4'][i%2:]+['v1','v4'][:i%2]));answer='Synthetic unit-test answer; not an evaluation result.'
        for label,snap in r['snapshots'].items():
            r['rows'].append({'case_id':c['id'],'condition':label,'status':'completed','answer':answer,'model':h.CONDITIONS['model'],'input_key':request_key(c,request_spec(snap)),'prompt_metadata':_snapshot(snap).metadata(),'no_write':True,'compact_used':c['expected']=='answer_now','route':'followup_direct' if c['expected']=='answer_now' else 'supervisor','ms':100,'cost_usd':price_usage(h.CONDITIONS['model'],[usage]),'usage':[usage]})
            trace={'input_key':r['rows'][-1]['input_key'],'fixture_truth':fixture_truth(c),'model_inputs':[[{'type':'system','content':snap['texts']['team.compact_followup' if c['expected']=='answer_now' else 'team.base']+'\nCode-owned role/evidence instructions'}]]}
            save_json(tmp_path/'main/model-inputs'/(c['id']+'-'+label+'.json'),trace)
        flat={side+'_'+k:v for side in 'ab' for k,v in {'correct':True,'faithful':True,'fresh_current_values':True,'unnecessary_request':False,'focused_required_question':True,'unsafe_commitment':False,'reason':'synthetic unit fixture'}.items()}
        raw={'text':json.dumps(flat),'finish_reasons':['FinishReason.STOP'],'usage':usage}
        save_json(tmp_path/'main/raw-judges'/(c['id']+'.json'),raw)
        payload={'case':c,'fixture_truth':fixture_truth(c),'historical_trace_limit':'Old answers have no full tool transcript; fixture facts are deterministic available truth, not proof of a tool read.','a':answer,'b':answer}
        from scripts.eval.clarification_v3 import parse_grades
        grades.append({'case_id':c['id'],'mapping':mapping,'answer_binding':digest(payload),'system_sha256':hashlib.sha256(system.encode()).hexdigest(),'n_conditions':2,'status':'completed','raw_sha256':digest(raw),'usage':usage,'grades':parse_grades(raw['text'],2)})
    save_json(tmp_path/'main/answers.json',r);save_json(tmp_path/'main/judges.json',{'rows':grades})
    return candidate,key


def test_verifier_accepts_full_bound_two_template_unit_fixture(tmp_path):
    from scripts.prompt_release_workflow import verify_evidence,verify_receipt
    candidate,key=_approval_fixture(tmp_path)
    receipt=verify_evidence(candidate,tmp_path,key.public_key())
    assert receipt['approved'] and receipt['coverage']['v4']['team.base']==50
    assert receipt['coverage']['v4']['team.compact_followup']==50
    assert verify_receipt(candidate,tmp_path,receipt,key.public_key())==receipt


@pytest.mark.parametrize('change',['answer','mapping','raw_grade','trace','usage','finish_reason','wrong_version'])
def test_verifier_rejects_changed_evidence(tmp_path,change):
    from scripts.prompt_release_workflow import verify_evidence
    from scripts.eval.cache_artifacts import save_json
    from scripts.eval.clarification_v3 import read
    from app.core.prompt_release_control import digest
    candidate,key=_approval_fixture(tmp_path)
    if change in ['answer','usage']:
        p=tmp_path/'main/answers.json';r=read(p)
        if change=='answer':r['rows'][0]['answer']='tampered answer'
        else:r['rows'][0]['cost_usd']+=.001
        save_json(p,r)
    elif change=='mapping':
        p=tmp_path/'main/judges.json';r=read(p);r['rows'][0]['mapping']={'a':'v4','b':'v1'};save_json(p,r)
    elif change=='wrong_version':
        p=tmp_path/'main/model-inputs/h5-portion-00-v1.json';r=read(p);r['model_inputs'][0][0]['content']=candidate['snapshot']['texts']['team.base']+'\nCode-owned role/evidence instructions';save_json(p,r)
    elif change=='trace':
        p=tmp_path/'main/model-inputs/h5-portion-00-v4.json';r=read(p);r['model_inputs'][0][0]['content']='not evaluated prompt';save_json(p,r)
    else:
        p=tmp_path/'main/raw-judges/h5-portion-00.json';r=read(p)
        if change=='raw_grade':r['text']='{}'
        else:r['finish_reasons']=['FinishReason.MAX_TOKENS']
        save_json(p,r)
        # Re-hash too: invalid evidence must fail semantically, not only on stale hashes.
        p=tmp_path/'main/judges.json';j=read(p);j['rows'][0]['raw_sha256']=digest(r);save_json(p,j)
    with pytest.raises(ValueError):verify_evidence(candidate,tmp_path,key.public_key())
