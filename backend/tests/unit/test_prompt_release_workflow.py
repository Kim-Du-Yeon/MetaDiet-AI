import copy,json
from pathlib import Path
import pytest
from scripts.prompt_release_workflow import make_candidate,verify_evidence,verify_receipt
from app.core.prompt_release_control import local_snapshot,sign_snapshot
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT=Path(__file__).resolve().parents[3]

def fixture_candidate():
    key=Ed25519PrivateKey.generate()
    raw=json.loads((ROOT/'docs/prompt_control/comparison/paired.json').read_text(encoding='utf-8'))['prompt_snapshots']['v1']
    base=sign_snapshot(raw,key,report_sha256='a'*64)
    return make_candidate(base,'release-any-name',{},lambda *a:None,key.public_key()),key

def test_saved_v1_reused_for_arbitrary_release_name_without_model_calls():
    candidate,key=fixture_candidate()
    receipt=verify_evidence(candidate,ROOT/'docs/prompt_control/comparison',key.public_key())
    assert receipt['condition']=='v1' and receipt['approved']
    assert verify_receipt(candidate,ROOT/'docs/prompt_control/comparison',receipt,key.public_key())==receipt

def test_changed_commit_cannot_borrow_saved_results():
    candidate,key=fixture_candidate()
    child=candidate['snapshot']['manifest']['prompts']['team.compact_followup']
    child['commit']='f'*64
    with pytest.raises(ValueError,match='matching'):
        verify_evidence(candidate,ROOT/'docs/prompt_control/comparison',key.public_key())

def test_mutable_reference_and_duplicate_selection_rejected():
    candidate,key=fixture_candidate()
    with pytest.raises(ValueError):make_candidate(candidate['baseline'],'new',{'team.base':'latest'},lambda *a:None,key.public_key())

def test_receipt_tamper_or_new_candidate_rejected():
    candidate,key=fixture_candidate();folder=ROOT/'docs/prompt_control/comparison'
    receipt=verify_evidence(candidate,folder,key.public_key());receipt['approved']=False
    with pytest.raises(ValueError):verify_receipt(candidate,folder,receipt,key.public_key())

def test_evidence_tamper_and_unevaluated_route_fail_closed(tmp_path):
    candidate,key=fixture_candidate();source=ROOT/'docs/prompt_control/comparison'
    for name in ['paired.json','judges.json','frozen.json','summary.json']:(tmp_path/name).write_bytes((source/name).read_bytes())
    raw=json.loads((tmp_path/'paired.json').read_text(encoding='utf-8'));raw['rows'].pop();(tmp_path/'paired.json').write_text(json.dumps(raw))
    with pytest.raises(ValueError):verify_evidence(candidate,tmp_path,key.public_key())
    raw=candidate['snapshot'];name='team.role.goal';text=raw['texts'][name]+' new instruction'
    import hashlib
    raw['texts'][name]=text;raw['manifest']['prompts'][name]['sha256']=hashlib.sha256(text.encode()).hexdigest()
    with pytest.raises(ValueError,match='coverage'):verify_evidence(candidate,source,key.public_key())

def test_publish_rejects_stale_receipt_before_any_remote_access():
    from scripts.prompt_release_workflow import publish
    candidate,key=fixture_candidate()
    class Forbidden:
        def __getattr__(self,name):raise AssertionError('Network must not be touched')
    with pytest.raises(ValueError):publish(candidate,ROOT/'docs/prompt_control/comparison',{},key.public_key(),key,Forbidden())

def test_failed_v2_cannot_be_approved_by_changing_summary_selection():
    candidate,key=fixture_candidate()
    report=json.loads((ROOT/'docs/prompt_control/comparison/paired.json').read_text(encoding='utf-8'))
    candidate['snapshot']=report['prompt_snapshots']['v2']
    candidate['snapshot']={k:v for k,v in candidate['snapshot'].items() if k!='experiment'}
    candidate['snapshot']['manifest']['release']='independent-new-candidate'
    with pytest.raises(ValueError,match='improvement'):verify_evidence(candidate,ROOT/'docs/prompt_control/comparison',key.public_key())

@pytest.mark.parametrize('mutation',['duplicate','wrong_metadata','nan_cost','incomplete_judge'])
def test_recomputed_validation_rejects_rehashed_but_invalid_results(tmp_path,mutation):
    import hashlib
    candidate,key=fixture_candidate();source=ROOT/'docs/prompt_control/comparison'
    for name in ['paired.json','judges.json','frozen.json','summary.json']:(tmp_path/name).write_bytes((source/name).read_bytes())
    paired=json.loads((tmp_path/'paired.json').read_text(encoding='utf-8'));judges=json.loads((tmp_path/'judges.json').read_text(encoding='utf-8'))
    if mutation=='duplicate':paired['rows'][-1]=copy.deepcopy(paired['rows'][0])
    if mutation=='wrong_metadata':paired['rows'][0]['prompt_metadata']['prompt_commit_ids']['team.base']='f'*64
    if mutation=='nan_cost':paired['rows'][0]['cost_usd']=float('nan')
    if mutation=='incomplete_judge':judges['rows'].pop()
    (tmp_path/'paired.json').write_text(json.dumps(paired,ensure_ascii=False),encoding='utf-8');(tmp_path/'judges.json').write_text(json.dumps(judges),encoding='utf-8')
    summary=json.loads((tmp_path/'summary.json').read_text(encoding='utf-8'));summary['source_hashes']={name:hashlib.sha256((tmp_path/name).read_bytes()).hexdigest() for name in ['paired.json','judges.json','frozen.json']};(tmp_path/'summary.json').write_text(json.dumps(summary),encoding='utf-8')
    with pytest.raises(ValueError):verify_evidence(candidate,tmp_path,key.public_key())

@pytest.mark.asyncio
async def test_generic_runner_pins_candidate_and_refuses_different_resume(tmp_path,monkeypatch):
    from scripts.eval import benchmark_prompt_control as runner
    from app.core.prompt_release_control import current_snapshot
    candidate,key=fixture_candidate();path=tmp_path/'candidate.json';path.write_text(json.dumps(candidate),encoding='utf-8')
    monkeypatch.setattr('app.core.prompt_service.approval_key',lambda:key.public_key())
    monkeypatch.setattr(runner.eval_budget,'Budget',lambda _:None)
    monkeypatch.setattr(runner.eval_budget,'install_transport_guard',lambda *args:None)
    async def no_sleep(*args):pass
    monkeypatch.setattr(runner.asyncio,'sleep',no_sleep)
    seen=[]
    async def attempt(case,*args):
        seen.append(current_snapshot().release)
        return {'case_id':case['id'],'status':'completed','ms':1,'fresh':True,'no_write':True,'model':'gemini-3.8-flash','cost_usd':0,'usage':[{'input_tokens':0,'output_tokens':0}]}
    monkeypatch.setattr(runner.base,'attempt',attempt)
    folder=tmp_path/'new-comparison'
    await runner.main(folder,path)
    report=json.loads((folder/'paired.json').read_text(encoding='utf-8'))
    assert len(report['rows'])==200 and seen.count('release-any-name')==100
    assert report['experiment_id']=='prompt-release-release-any-name'
    await runner.main(folder,path)
    assert len(seen)==200 # Complete attempts reused; no regeneration.
    candidate['snapshot']['manifest']['prompts']['team.compact_followup']['commit']='f'*64
    path.write_text(json.dumps(candidate),encoding='utf-8')
    with pytest.raises(ValueError,match='another candidate'):await runner.main(folder,path)
    assert len(seen)==200

@pytest.mark.parametrize('bound',[True,False])
def test_unrelated_grades_cannot_be_approved_after_rehash(tmp_path,bound):
    import hashlib
    from app.core.prompt_release_control import digest
    candidate,key=fixture_candidate();source=ROOT/'docs/prompt_control/comparison'
    for name in ['paired.json','judges.json','frozen.json','summary.json']:(tmp_path/name).write_bytes((source/name).read_bytes())
    report=json.loads((tmp_path/'paired.json').read_text(encoding='utf-8'));judges=json.loads((tmp_path/'judges.json').read_text(encoding='utf-8'))
    if bound:
        report['experiment_id']='new-candidate'
        judges['generation_binding']='f'*64
    else:judges['rows'][0]['grades']['a']['reason']='different assessment'
    (tmp_path/'paired.json').write_text(json.dumps(report,ensure_ascii=False),encoding='utf-8');(tmp_path/'judges.json').write_text(json.dumps(judges),encoding='utf-8')
    summary=json.loads((tmp_path/'summary.json').read_text(encoding='utf-8'));summary['source_hashes']={name:hashlib.sha256((tmp_path/name).read_bytes()).hexdigest() for name in ['paired.json','judges.json','frozen.json']};(tmp_path/'summary.json').write_text(json.dumps(summary),encoding='utf-8')
    with pytest.raises(ValueError,match='binding|legacy'):verify_evidence(candidate,tmp_path,key.public_key())

@pytest.mark.parametrize('stale_answer',[False,True])
def test_bound_results_validate_exact_answers_not_only_prompt_ids(tmp_path,stale_answer):
    import hashlib
    from app.core.prompt_release_control import digest
    candidate,key=fixture_candidate();source=ROOT/'docs/prompt_control/comparison'
    for name in ['paired.json','judges.json','frozen.json','summary.json']:(tmp_path/name).write_bytes((source/name).read_bytes())
    report=json.loads((tmp_path/'paired.json').read_text(encoding='utf-8'));judges=json.loads((tmp_path/'judges.json').read_text(encoding='utf-8'));cases={c['id']:c for c in json.loads((tmp_path/'frozen.json').read_text(encoding='utf-8'))}
    report['experiment_id']='bound-synthetic'
    judges['generation_binding']=digest({k:report[k] for k in ['cases_sha256','prompt_snapshots','model','conditions']})
    answers={(r['case_id'],r['condition']):r['answer'] for r in report['rows']}
    for row in judges['rows']:
        c=cases[row['case_id']];payload={'question':c['question'],'current_calories':c['calories'],'current_calorie_target':c['target'],**{position:answers[(row['case_id'],label)] for position,label in row['mapping'].items()}}
        row['answer_binding']=digest(payload)
    if stale_answer:report['rows'][0]['answer']='Different regenerated answer'
    (tmp_path/'paired.json').write_text(json.dumps(report,ensure_ascii=False),encoding='utf-8');(tmp_path/'judges.json').write_text(json.dumps(judges),encoding='utf-8')
    summary=json.loads((tmp_path/'summary.json').read_text(encoding='utf-8'));summary['source_hashes']={name:hashlib.sha256((tmp_path/name).read_bytes()).hexdigest() for name in ['paired.json','judges.json','frozen.json']};(tmp_path/'summary.json').write_text(json.dumps(summary),encoding='utf-8')
    if stale_answer:
        with pytest.raises(ValueError,match='answer binding'):verify_evidence(candidate,tmp_path,key.public_key())
    else:assert verify_evidence(candidate,tmp_path,key.public_key())['approved']
