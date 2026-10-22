import copy,json,hashlib
from pathlib import Path
import pytest
from scripts.eval.clarification_execution import read_cases,new_report,analyze,verify,request_spec,judge_binding,RUBRIC,RUBRIC_SHA,CONDITIONS,SUITE,validate_budget
from scripts.eval.clarification_cases import request_key
from scripts.prompt_release_workflow import ROOT,read,make_candidate
from app.core.prompt_release_control import _snapshot,sign_snapshot,digest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def candidate_fixture():
    key=Ed25519PrivateKey.generate();base=read(ROOT/'docs/prompt_control/approved-release.json');base.pop('signature',None);base=sign_snapshot(base,key,report_sha256='a'*64)
    old=base['texts']['team.compact_followup']
    candidate=make_candidate(base,'clarification-test',{'team.compact_followup':'f'*64},lambda *a:(old+'\n불필요한 질문을 줄이세요.','f'*64),key.public_key())
    return candidate,key


def evidence(tmp_path):
    c,key=candidate_fixture();cases=read_cases();r=new_report(c,cases);j={'model':'gemini-3.1-pro-preview','rubric':RUBRIC,'rubric_sha256':RUBRIC_SHA,'generation_binding':judge_binding(r),'rows':[]}
    for i,case in enumerate(cases):
        for label in ['v1','v2']:
            s=r['prompt_snapshots'][label]
            r['rows'].append({'case_id':case['id'],'condition':label,'status':'completed','answer':'확인된 정보로 답변합니다.','model':r['model'],'input_key':request_key(case,request_spec(s)),'prompt_metadata':_snapshot(s).metadata(),'ms':100,'cost_usd':.00009,'usage':[{'input_tokens':20,'output_tokens':20}],'no_write':True,'route':'followup_direct' if case['expected']=='answer_now' else 'supervisor','compact_used':case['expected']=='answer_now'})
        from scripts.eval.clarification_execution import pair_payload
        payload,mapping=pair_payload(case,r['rows'],i)
        grade={'correct':True,'faithful':True,'fresh_current_values':True,'unnecessary_request':False,'focused_required_question':case['expected']=='ask_required','unsafe_commitment':False,'reason':'fixture'}
        grades={p:{**grade,'unnecessary_request':case['expected']=='answer_now' and i<10 and label=='v1'} for p,label in mapping.items()}
        j['rows'].append({'case_id':case['id'],'status':'completed','mapping':mapping,'answer_binding':digest(payload),'grades':grades,'usage':[{'input_tokens':20,'output_tokens':20}]})
    def save():
        for name,v in [('paired.json',r),('judges.json',j),('frozen.json',cases)]: (tmp_path/name).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        summary=analyze(r,j,cases);summary['source_hashes']={n:hashlib.sha256((tmp_path/n).read_bytes()).hexdigest() for n in ['paired.json','judges.json','frozen.json']};(tmp_path/'summary.json').write_text(json.dumps(summary),encoding='utf-8')
    save();return c,key,r,j,cases,save


def test_new_semantic_suite_can_be_verified_without_old_rubric(tmp_path):
    c,key,*_=evidence(tmp_path)
    receipt=verify(c,tmp_path,key.public_key())
    assert receipt['approved'] and receipt['suite']==SUITE
    from scripts.prompt_release_workflow import verify_evidence
    assert verify_evidence(c,tmp_path,key.public_key())==receipt


@pytest.mark.parametrize('kind',['answer','input','route','unsafe','missing_judge','rubric','no_improvement','cost'])
def test_unverified_or_stale_semantic_evidence_is_blocked(tmp_path,kind):
    c,key,r,j,cases,save=evidence(tmp_path)
    if kind=='cost':r['rows'][0]['cost_usd']=0
    if kind=='answer':r['rows'][0]['answer']='再生成'
    if kind=='input':r['rows'][0]['input_key']='f'*64
    if kind=='route':r['rows'][0]['compact_used']=False
    if kind=='unsafe':j['rows'][0]['grades']['b']['unsafe_commitment']=True
    if kind=='missing_judge':j['rows'].pop()
    if kind=='rubric':j['rubric_sha256']='f'*64
    if kind=='no_improvement':
        for row in j['rows']:
            for grade in row['grades'].values():grade['unnecessary_request']=False
    save()
    with pytest.raises(ValueError):verify(c,tmp_path,key.public_key())


def test_case_revision_routes_50_targets_and_keeps_50_controls():
    from app.agents.coaching_route import simple_followup
    cases=read_cases()
    assert sum(simple_followup({'message':c['question'],'messages':c['recent_messages']}) for c in cases)==50


def test_budget_plan_cannot_reset_costs_or_increase_total():
    from scripts.eval.clarification_execution import FOLDER,HISTORICAL_FLOORS
    p=read(FOLDER/'budget.json');current={'committed_usd':8.735208,'stages':HISTORICAL_FLOORS,'stopped':False}
    validate_budget(p,current)
    with pytest.raises(ValueError):validate_budget({**p,'total_limit_usd':18},current)
    with pytest.raises(ValueError):validate_budget(p,{'committed_usd':7,'stages':{},'stopped':False})
    with pytest.raises(ValueError):validate_budget({**p,'ledger':'D:/AX/diet_agent/tmp/new.sqlite'},current)
    with pytest.raises(ValueError):validate_budget(p,{**current,'stages':{**HISTORICAL_FLOORS,'judge':0}})

@pytest.mark.asyncio
async def test_actual_DietTeam_routes_for_both_immutable_releases_without_provider():
    from scripts.eval.run_clarification_comparison import audit
    c,_=candidate_fixture();result=await audit(c)
    assert result['passed'] and result['checks']==200
    assert sum(r['compact_used'] for r in result['rows'])==100

@pytest.mark.parametrize('name,reason',[('paired.json','quota_exhausted'),('paired.json','unknown'),('judges.json','credits_depleted'),('judges.json','unknown')])
def test_saved_fatal_or_unknown_accounting_cannot_resume(tmp_path,name,reason):
    from scripts.eval.run_clarification_comparison import ensure_running
    row={'case_id':'x','status':'failed','cost_usd':None,'usage':[],'error':{'reason':reason}}
    (tmp_path/name).write_text(json.dumps({'rows':[row]}),encoding='utf-8')
    with pytest.raises(ValueError):ensure_running(tmp_path)


@pytest.mark.asyncio
async def test_resuming_known_complete_generations_reuses_answers_and_rejects_new_input(tmp_path):
    from scripts.eval.run_clarification_comparison import generate,initialize
    c,_=candidate_fixture();seen=[]
    async def fake(case,snapshot):
        seen.append(case['id']);return {'case_id':case['id'],'input_key':request_key(case,request_spec(snapshot)),'status':'completed','cost_usd':.00001,'usage':[{'input_tokens':1,'output_tokens':1}],'answer':'fake'}
    await generate(c,tmp_path,True,fake);assert len(seen)==40
    await generate(c,tmp_path,True,fake);assert len(seen)==40
    r=read(tmp_path/'paired.json');r['rows'][0]['input_key']='f'*64;(tmp_path/'paired.json').write_text(json.dumps(r),encoding='utf-8')
    with pytest.raises(ValueError):await generate(c,tmp_path,True,fake)
    assert len(seen)==40


@pytest.mark.asyncio
async def test_probe_requires_offline_audit_before_any_paid_transport(tmp_path,monkeypatch):
    from argparse import Namespace
    from scripts.eval import run_clarification_comparison as runner
    c,key=candidate_fixture();path=tmp_path/'candidate.json';path.write_text(json.dumps(c),encoding='utf-8')
    monkeypatch.setattr('app.core.prompt_service.approval_key',lambda:key.public_key())
    monkeypatch.setattr('dotenv.load_dotenv',lambda *a,**k:None)
    async def forbidden(*a,**k):raise AssertionError('Provider must not be called')
    monkeypatch.setattr(runner,'probe',forbidden)
    args=Namespace(action='probe',candidate=path,folder=tmp_path,budget='not-opened',allow_paid=True,development=False)
    with pytest.raises(ValueError,match='audit'):await runner.main(args)


@pytest.mark.asyncio
async def test_judge_cli_rejects_another_candidate_before_transport_install(tmp_path,monkeypatch):
    import time
    from argparse import Namespace
    from scripts.eval import run_clarification_comparison as runner
    c,key=candidate_fixture();path=tmp_path/'candidate.json';path.write_text(json.dumps(c),encoding='utf-8')
    monkeypatch.setattr('app.core.prompt_service.approval_key',lambda:key.public_key())
    monkeypatch.setattr('dotenv.load_dotenv',lambda *a,**k:None)
    audit=await runner.audit(c);(tmp_path/'route-audit.json').write_text(json.dumps(audit),encoding='utf-8')
    (tmp_path/'pro-probe.json').write_text(json.dumps({'status':'completed','timestamp':time.time(),'evaluation_binding':runner.audit_binding(c)}),encoding='utf-8')
    other=copy.deepcopy(c);other['snapshot']['manifest']['prompts']['team.compact_followup']['commit']='e'*64
    runner.initialize(other,tmp_path)
    monkeypatch.setattr(runner,'install_budget',lambda *a,**k:(_ for _ in ()).throw(AssertionError('Budget transport cannot be installed')))
    args=Namespace(action='judge',candidate=path,folder=tmp_path,budget='not-opened',allow_paid=True,development=False)
    with pytest.raises(ValueError,match='candidate'):await runner.main(args)

def test_eval_model_uses_role_configuration_without_forbidden_override(monkeypatch):
    from scripts.eval import run_clarification_comparison as runner
    from app.core.llm import get_chat_model
    monkeypatch.setattr('app.core.llm.get_settings',runner.settings)
    model=get_chat_model(role='eval',temperature=0,max_tokens=128,thinking_level='low')
    assert model.role=='eval'
    assert runner.settings().gemini_eval_model=='gemini-3.1-pro-preview'
    import inspect
    source=inspect.getsource(runner)
    assert "role='eval',model_name=" not in source
