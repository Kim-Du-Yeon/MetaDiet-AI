"""Resumable, budgeted real DietTeam clarification runner. Offline by default."""
import argparse,asyncio,hashlib,json,sys,time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'backend'))
from scripts.eval.clarification_execution import (SUITE,FOLDER,CONDITIONS,RUBRIC,RUBRIC_SHA,read_cases,new_report,request_spec,judge_binding,pair_payload,analyze,validate_budget,runtime_code,assert_ledger,price_usage)
from scripts.eval.clarification_cases import request_key
from app.core.prompt_release_control import _snapshot,using_snapshot,digest
from scripts.eval.model_routing_support import estimate_cost
from scripts.eval.cache_artifacts import save_json


def versions():
    import importlib.metadata
    return {k:importlib.metadata.version(k) for k in CONDITIONS['packages']}


def settings():
    from app.core.config import get_settings
    return get_settings().model_copy(update={'gemini_model':CONDITIONS['model'],'gemini_eval_model':'gemini-3.1-pro-preview','model_max_retries':0,'agent_max_model_calls':3,'agent_max_tool_calls':8,'agent_timeout_seconds':65,'first_coaching_mode':'off','compact_followup_prompt':True,'brief_followup_answer':False,'coaching_thinking_level':'low','coaching_delivery':'invoke','followup_tools_enabled':False,'followup_model':'default','model_routing_enabled':False,'gemini_explicit_cache_enabled':False,'gemini_private_cache_enabled':False})


async def attempt(case,snapshot,model_factory=None):
    from scripts.eval.benchmark_model_routing import Usage,safe_error
    from app.agents.team import DietTeam
    from app.core.llm import get_chat_model
    from datetime import date
    fixture_date=date.fromisoformat(CONDITIONS['fixture_date'])
    class Track(Usage):
        compact=False
        async def on_chat_model_start(self,serialized,messages,**kwargs):
            self.compact |= any(getattr(m,'content',None)==snapshot['texts']['team.compact_followup'] for group in messages for m in group if getattr(m,'type',None)=='system')
    usage=Track();repo=AsyncMock();cfg=settings();started=time.perf_counter()
    row={'case_id':case['id'],'status':'failed','answer':'','model':CONDITIONS['model'],'input_key':request_key(case,request_spec(snapshot)),'prompt_metadata':_snapshot(snapshot).metadata(),'no_write':False,'compact_used':False,'route':None}
    history=case['recent_messages']+[{'role':'user','content':'이 상담에 제공한 정보: '+json.dumps(case['verified_context'],ensure_ascii=False)}]
    config={'callbacks':[usage],'metadata':{**_snapshot(snapshot).metadata(),'evaluation':SUITE,'case_id':case['id']}}
    factory=model_factory or (lambda:get_chat_model(task='agent',model_name=CONDITIONS['model'],temperature=0,max_tokens=1024,thinking_level='low'))
    with using_snapshot(_snapshot(snapshot)),patch('app.agents.team.get_settings',lambda:cfg),patch('app.core.llm.get_settings',lambda:cfg),patch('app.agents.team.service_today',lambda:fixture_date):
        team=DietTeam({'user_id':'synthetic-clarification','message':case['question'],'messages':history},repository=repo,db=object(),model_factory=factory,config=config,simple_meals_enabled=False)
        team.allowed={'read_profile','read_intake'}
        async def rows(table,**filters):
            if table=='users':return [{'goal':'diet'}]
            if table=='diet_strategies':return [{'daily_calories':case['verified_context']['target']}]
            if table=='meal_logs':return [{'calories':case['verified_context']['calories'],'food_name':'synthetic confirmed row','meal_type':'lunch','log_date':fixture_date.isoformat()}]
            raise AssertionError('External fixture read prohibited')
        team.rows=AsyncMock(side_effect=rows)
        team.prepare_requested_evidence=AsyncMock(return_value=None) # Fixed no-retrieval comparison condition, not routing override.
        try:
            result=await asyncio.wait_for(team.execute(),65)
            row.update(status=result['execution_status'],answer=result['response'],model_calls=result['execution_usage']['model_calls'],no_write=not repo.create.called and not repo.resolve.called and not result.get('pending_proposal'))
        except Exception as e:row['error']=safe_error(e)
    costs=[estimate_cost(CONDITIONS['model'],u) for u in usage.calls]
    row.update(ms=(time.perf_counter()-started)*1000,usage=usage.calls,cost_usd=sum(costs) if costs and all(v is not None for v in costs) else None,compact_used=usage.compact,route=(team.config or {}).get('metadata',{}).get('route'))
    return row


class OfflineModel:
    def bind_tools(self,tools):return self
    async def ainvoke(self,messages,config=None):
        from langchain_core.messages import AIMessage
        response=AIMessage(content='오프라인 경로 확인용 응답이며 품질 평가가 아닙니다.',usage_metadata={'input_tokens':10,'output_tokens':5,'total_tokens':15})
        for cb in (config or {}).get('callbacks',[]):
            await cb.on_chat_model_start({},[messages]);await cb.on_llm_end(SimpleNamespace(generations=[[SimpleNamespace(message=response)]]))
        return response


async def audit(candidate):
    rows=[]
    for case in read_cases():
        for label,snapshot in [('v1',candidate['baseline']),('v2',candidate['snapshot'])]:
            row=await attempt(case,snapshot,lambda:OfflineModel());rows.append({'case_id':case['id'],'condition':label,'expected':case['expected'],'route':row['route'],'compact_used':row['compact_used'],'no_write':row['no_write'],'status':row['status']})
    passed=all(r['status']=='completed' and r['no_write'] and r['compact_used']==(r['expected']=='answer_now') and r['route']==('followup_direct' if r['expected']=='answer_now' else 'supervisor') for r in rows)
    return {'type':'offline_actual_DietTeam_route_audit_with_fake_model_not_provider_performance','binding':audit_binding(candidate),'passed':passed,'checks':len(rows),'rows':rows}


def audit_binding(candidate):
    from scripts.prompt_release_workflow import identity
    return digest({'v1':identity(candidate['baseline']),'v2':identity(candidate['snapshot']),'cases':digest(read_cases()),'code':runtime_code()})


def ensure_running(folder):
    folder=Path(folder)
    if (folder/'stop.json').exists():raise ValueError('Campaign stopped; preserve and review before a new run')
    for name in ['paired.json','judges.json']:
        if not (folder/name).exists():continue
        value=json.loads((folder/name).read_text(encoding='utf-8'))
        for row in value['rows']:
            if row.get('error',{}).get('reason') in {'credits_depleted','quota_exhausted'}:raise ValueError('Saved fatal capacity stop; no resume calls')
            if name=='paired.json' and row.get('cost_usd') is None:raise ValueError('Saved unknown accounting stop')
            if name=='judges.json' and row.get('error',{}).get('reason')!='generation_failed':
                price_usage('gemini-3.1-pro-preview',row.get('usage'))


def require_audit(candidate,folder):
    path=Path(folder)/'route-audit.json'
    if not path.exists():raise ValueError('Passing offline actual-route audit required before any paid call')
    value=json.loads(path.read_text(encoding='utf-8'));cases=read_cases();by={c['id']:c for c in cases}
    expected={(c['id'],k) for c in cases for k in ['v1','v2']};rows=value.get('rows',[])
    if value.get('passed') is not True or value.get('binding')!=audit_binding(candidate) or len(rows)!=200 or {(r['case_id'],r['condition']) for r in rows}!=expected:raise ValueError('Offline audit identity/coverage changed')
    if any(r.get('status')!='completed' or r.get('no_write') is not True or r.get('compact_used')!=(by[r['case_id']]['expected']=='answer_now') or r.get('route')!=('followup_direct' if by[r['case_id']]['expected']=='answer_now' else 'supervisor') for r in rows):raise ValueError('Offline actual route audit failed')
    return value


def stop(folder,stage,reason,case_id):
    save_json(Path(folder)/'stop.json',{'stage':stage,'reason':reason,'case_id':case_id,'timestamp':time.time(),'instruction':'No automatic resume; preserve original failures/reservations for explicit accounting/capacity review.'})
    raise RuntimeError(reason)


def initialize(candidate,folder,development=False):
    ensure_running(folder)
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True);cases=read_cases(development)
    path=folder/'paired.json';report=new_report(candidate,cases)
    if path.exists():
        prior=json.loads(path.read_text(encoding='utf-8'))
        from scripts.prompt_release_workflow import identity
        if prior.get('suite')!=SUITE or prior.get('scope')!='synthetic_actual_DietTeam_readonly_not_users' or prior.get('model')!=CONDITIONS['model'] or prior.get('execution_code')!=runtime_code() or prior['conditions']!=CONDITIONS or prior['cases_sha256']!=digest(cases) or any(identity(prior['prompt_snapshots'][k])!=identity(report['prompt_snapshots'][k]) for k in ['v1','v2']):raise ValueError('Resume input/candidate/settings changed')
        if json.loads((folder/'frozen.json').read_text(encoding='utf-8'))!=cases:raise ValueError('Saved frozen input changed')
        keys=[(r['case_id'],r['condition']) for r in prior['rows']]
        expected={(c['id'],k) for c in cases for k in ['v1','v2']}
        if len(keys)!=len(set(keys)) or any(k not in expected for k in keys):raise ValueError('Duplicate/unknown saved generation')
        for row in prior['rows']:
            case=next(c for c in cases if c['id']==row['case_id'])
            if row.get('input_key')!=request_key(case,request_spec(prior['prompt_snapshots'][row['condition']])):raise ValueError('Saved input/settings changed')
        report=prior
    else:
        for name,value in [('frozen.json',cases),('paired.json',report)]:
            with (folder/name).open('x',encoding='utf-8') as f:f.write(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    return cases,report


async def generate(candidate,folder,development=False,attempt_fn=attempt):
    cases,r=initialize(candidate,folder,development);path=Path(folder)/'paired.json';done={(x['case_id'],x['condition']) for x in r['rows']}
    for i,c in enumerate(cases):
        for label in (['v1','v2'] if i%2==0 else ['v2','v1']):
            if (c['id'],label) in done:continue
            row=await attempt_fn(c,r['prompt_snapshots'][label]);row['condition']=label;r['rows'].append(row);save_json(path,r)
            print(c['id'],label,row['status'],flush=True)
            if row.get('error',{}).get('reason') in {'credits_depleted','quota_exhausted'}:stop(folder,'generation','Capacity stop; no further calls',c['id'])
            if row.get('cost_usd') is None:stop(folder,'generation','Unknown accounting; no further calls',c['id'])
    return r


async def judge(folder,development=False):
    ensure_running(folder)
    from pydantic import BaseModel,ConfigDict
    from scripts.eval.benchmark_model_routing import Usage,safe_error
    from app.core.llm import get_chat_model
    class Grade(BaseModel):
        model_config=ConfigDict(strict=True,extra='forbid')
        correct:bool;faithful:bool;fresh_current_values:bool;unnecessary_request:bool;focused_required_question:bool;unsafe_commitment:bool;reason:str
    class Pair(BaseModel):
        model_config=ConfigDict(strict=True,extra='forbid')
        a:Grade;b:Grade
    folder=Path(folder);r=json.loads((folder/'paired.json').read_text(encoding='utf-8'));cases=json.loads((folder/'frozen.json').read_text(encoding='utf-8'));path=folder/'judges.json'
    if cases!=read_cases(development) or r.get('execution_code')!=runtime_code() or r.get('conditions')!=CONDITIONS or r.get('model')!=CONDITIONS['model']:raise ValueError('Unrecognized judging cohort/settings')
    expected={(c['id'],k) for c in cases for k in ['v1','v2']}
    if len(r['rows'])!=len(expected) or {(x['case_id'],x['condition']) for x in r['rows']}!=expected:raise ValueError('Incomplete/duplicate generations')
    for x in r['rows']:
        case=next(c for c in cases if c['id']==x['case_id'])
        if x.get('input_key')!=request_key(case,request_spec(r['prompt_snapshots'][x['condition']])):raise ValueError('Generation input changed')
    j=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'model':'gemini-3.1-pro-preview','rubric':RUBRIC,'rubric_sha256':RUBRIC_SHA,'generation_binding':judge_binding(r),'rows':[]}
    if j['generation_binding']!=judge_binding(r) or j['rubric']!=RUBRIC or j['rubric_sha256']!=RUBRIC_SHA:raise ValueError('Saved judge evidence belongs to another execution/rubric')
    for g in j['rows']:
        case=next(c for c in cases if c['id']==g['case_id']);payload,mapping=pair_payload(case,r['rows'],cases.index(case))
        if g.get('mapping')!=mapping or g.get('answer_binding')!=digest(payload):raise ValueError('Saved judge answer binding changed')
    done={g['case_id'] for g in j['rows']};cfg=settings()
    for i,c in enumerate(cases):
        if c['id'] in done:continue
        rows=[x for x in r['rows'] if x['case_id']==c['id']]
        if len(rows)!=2:raise ValueError('Wait for complete generation pair')
        payload,mapping=pair_payload(c,rows,i);u=Usage();row={'case_id':c['id'],'mapping':mapping,'answer_binding':digest(payload),'status':'failed'}
        if any(x['status']!='completed' for x in rows):row['error']={'reason':'generation_failed'}
        else:
            try:
                with patch('app.core.llm.get_settings',lambda:cfg):
                    model=get_chat_model(role='eval',temperature=0,max_tokens=2048,thinking_level='low')
                    result=await asyncio.wait_for(model.with_structured_output(Pair).ainvoke([{'role':'system','content':RUBRIC},{'role':'user','content':json.dumps(payload,ensure_ascii=False)}],config={'callbacks':[u],'metadata':{'evaluation':SUITE,'experiment_id':r['experiment_id'],'case_id':c['id'],'rubric_sha256':RUBRIC_SHA}}),90)
                row.update(status='completed',grades=result.model_dump())
            except Exception as e:row['error']=safe_error(e)
        row['usage']=u.calls;j['rows'].append(row);save_json(path,j);print(c['id'],row['status'],flush=True)
        if row.get('error',{}).get('reason') in {'credits_depleted','quota_exhausted'}:stop(folder,'judge','Pro capacity stop; preserved',c['id'])
        if row.get('error',{}).get('reason')!='generation_failed':
            try:price_usage('gemini-3.1-pro-preview',row['usage'])
            except ValueError:stop(folder,'judge','Unknown judge usage; stop',c['id'])
    return j


def summarize_folder(folder):
    folder=Path(folder);r=json.loads((folder/'paired.json').read_text(encoding='utf-8'));cases=json.loads((folder/'frozen.json').read_text(encoding='utf-8'))
    j=json.loads((folder/'judges.json').read_text(encoding='utf-8')) if (folder/'judges.json').exists() else {'rows':[]}
    result=analyze(r,j,cases);result['source_hashes']={n:hashlib.sha256((folder/n).read_bytes()).hexdigest() for n in ['paired.json','judges.json','frozen.json'] if (folder/n).exists()};save_json(folder/'summary.json',result);return result


def install_budget(path,stage):
    from scripts.eval import eval_budget
    p=json.loads(Path(path).read_text(encoding='utf-8'));assert_ledger(p);eval_budget.TOTAL=p['total_limit_usd'];eval_budget.LIMITS=p['stage_caps'];b=eval_budget.Budget(p['ledger']);validate_budget(p,b.summary());eval_budget.install_transport_guard(b,stage);return b


async def probe(path):
    import re
    from scripts.eval.benchmark_model_routing import Usage
    from app.core.llm import get_chat_model
    b=install_budget(path,'probe');u=Usage();out={'model':'gemini-3.1-pro-preview','timestamp':time.time(),'status':'failed','before_usd':b.summary()['committed_usd']}
    try:
        with patch('app.core.llm.get_settings',settings):
            value=await asyncio.wait_for(get_chat_model(role='eval',temperature=0,max_tokens=128,thinking_level='low').ainvoke('Reply only OK.',config={'callbacks':[u]}),45)
        out.update(status='completed',nonempty=bool(value.content))
    except Exception as e:
        texts=[];types=[];current=e
        for _ in range(4):
            if current is None:break
            texts.append(str(current));types.append(type(current).__name__);current=current.__cause__ or current.__context__
        text=' '.join(texts);out.update(exception_types=types,status_codes=sorted(set(re.findall(r'\b(?:402|429|403|503)\b',text))),quota_metrics=sorted(set(re.findall(r'generativelanguage\.googleapis\.com/[A-Za-z0-9_/]+',text))),quota_ids=sorted(set(re.findall(r'(?:quotaId|quota_id)[\s\"\x27:]+([A-Za-z][A-Za-z0-9_-]+)',text))),quota_limit_values=re.findall(r'limit[\s\"\x27:]+(\d+)',text,re.I),raw_error_stored=False)
    out.update(usage=u.calls,after_usd=b.summary()['committed_usd']);return out


async def main(args):
    from dotenv import load_dotenv
    load_dotenv(ROOT/'backend/.env',override=True)
    from scripts.prompt_release_workflow import read,validate_candidate,supported_changes
    from app.core.prompt_service import approval_key
    c=read(args.candidate);validate_candidate(c,approval_key());supported_changes(c)
    if versions()!=CONDITIONS['packages']:raise ValueError('Frozen SDK environment changed')
    folder=Path(args.folder);folder.mkdir(parents=True,exist_ok=True)
    if args.action=='audit':
        result=await audit(c);save_json(folder/'route-audit.json',result);print(json.dumps({'checks':result['checks'],'passed':result['passed']}));return
    if args.action=='summary':print(json.dumps(summarize_folder(folder),ensure_ascii=False));return
    if not args.allow_paid:raise ValueError('Paid calls require explicit authorization flag')
    ensure_running(folder);require_audit(c,folder)
    if args.action=='probe':
        if (folder/'pro-probe.json').exists():raise ValueError('Probe already recorded; use a new run folder, never loop retries')
        result=await probe(args.budget);result['evaluation_binding']=audit_binding(c);save_json(folder/'pro-probe.json',result);print(json.dumps(result,ensure_ascii=True));return
    audit_path=folder/'route-audit.json';probe_path=folder/'pro-probe.json'
    require_audit(c,folder)
    if not probe_path.exists() or read(probe_path).get('status')!='completed' or read(probe_path).get('evaluation_binding')!=audit_binding(c) or not 0<=time.time()-read(probe_path)['timestamp']<=3600:raise ValueError('Fresh successful Pro availability probe required before generation')
    if args.action=='judge':
        if not (folder/'paired.json').exists():raise ValueError('No generated evidence to judge')
        initialize(c,folder,args.development) # Candidate/cohort/code validation before judge transport guard.
        install_budget(args.budget,'development' if args.development else 'judge');await judge(folder,args.development);print(json.dumps(summarize_folder(folder),ensure_ascii=False));return
    install_budget(args.budget,'development' if args.development else 'comparison')
    await generate(c,folder,args.development)
    # Same persistent ledger, switch stage without stacking transport wrappers in this process.
    from scripts.eval import eval_budget
    # Transport guard receives a stage at install; judging runs as a separate CLI action/process.
    print('Generation saved. Run judge action in a separate process after checking budget.')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['audit','probe','generate','summary','judge']);p.add_argument('--candidate',default=str(ROOT/'docs/prompt_control/followup-question-candidate/candidate.json'));p.add_argument('--folder',required=True);p.add_argument('--budget',default=str(FOLDER/'budget.json'));p.add_argument('--allow-paid',action='store_true');p.add_argument('--development',action='store_true');a=p.parse_args()
    asyncio.run(main(a))
