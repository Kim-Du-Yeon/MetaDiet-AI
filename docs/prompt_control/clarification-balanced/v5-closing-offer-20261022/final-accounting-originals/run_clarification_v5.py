"""Single-process v5 development; reuse strict Batch and read-only runtime fixture."""
import argparse,asyncio,copy,json,sys
from pathlib import Path
from contextlib import contextmanager
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'backend'));sys.path.insert(0,str(Path(__file__).resolve().parent))
from scripts.eval import run_clarification_v3 as core,run_clarification_v4 as prior,clarification_v5 as policy
from scripts.eval.clarification_execution import request_spec
from scripts.eval.clarification_cases import request_key
from scripts.eval.cache_artifacts import save_json
from app.core.prompt_release_control import _snapshot,digest
read=policy.read


def stage_labels(dev):
    if dev:raise ValueError('No tuning on prospective holdout')
    return ['v4','v5']


def runner_sha():return digest(policy.code_sha())


def initialize(root,dev):
    stage_labels(dev);root=Path(root);policy.validate(root);candidate=read(root/'candidate.json');folder=core.stagefolder(root,False);folder.mkdir(exist_ok=True)
    cases=read(root/'frozen.json');initial={'experiment':policy.SUITE,'labels':['v4','v5'],'snapshots':{'v4':candidate['baseline'],'v5':candidate['snapshot']},'conditions':policy.CONDITIONS,'runner_sha256':runner_sha(),'protocol_sha256':digest(read(root/'protocol.json')),'cases_sha256':digest(cases),'rows':[policy.reuse_regression(cases[0],candidate['baseline'])]}
    p=folder/'answers.json'
    if not p.exists():save_json(p,initial);return initial
    saved=read(p)
    if any(saved[k]!=initial[k] for k in initial if k!='rows'):raise ValueError('Holdout execution changed')
    keys=[(r['case_id'],r['condition']) for r in saved['rows']];by={c['id']:c for c in cases}
    if len(keys)!=len(set(keys)) or any(c not in by or l not in initial['labels'] for c,l in keys):raise ValueError('Duplicate/unknown attempts')
    for r in saved['rows']:
        snap=initial['snapshots'][r['condition']]
        if r['input_key']!=request_key(by[r['case_id']],request_spec(snap)) or any(r['prompt_metadata'].get(k)!=_snapshot(snap).metadata().get(k) for k in ['prompt_commit_ids','prompt_hashes','prompt_bundle_sha256']):raise ValueError('Attempt identity changed')
    return saved


async def audit_routes(root):
    r=initialize(root,False);rows=[]
    for c in read(Path(root)/'frozen.json'):
        for label,snap in r['snapshots'].items():
            v=await core.attempt(c,snap,lambda:core.OfflineModel());rows.append({'case_id':c['id'],'condition':label,'status':v['status'],'no_write':v['no_write'],'route':v['route'],'compact_used':v['compact_used']})
    # Observe routes, never force them from gold. Both routes must be exercised.
    passed=len(rows)==200 and all(x['status']=='completed' and x['no_write'] for x in rows) and {x['route'] for x in rows}=={'followup_direct','supervisor'}
    save_json(Path(root)/'offline-route-audit.json',{'passed':passed,'code_sha256':policy.code_sha(),'rows':rows,'scope':'fake model contract only, not quality or paid answers'})
    if not passed:raise ValueError('Offline route audit failed')


def trace_metadata(case_id,label,snapshot):
    return {**_snapshot(snapshot).metadata(),'experiment_id':policy.SUITE,'case_id':case_id,'condition':label,'synthetic':True,'scope':'read_only_development_not_users'}


async def generate(root,dev):
    stage_labels(dev);root=Path(root);core.ensure_running(root,False);audit=read(root/'offline-route-audit.json')
    if not audit['passed'] or audit['code_sha256']!=policy.code_sha():raise ValueError('Offline audit required')
    r=initialize(root,False);done={(x['case_id'],x['condition']) for x in r['rows']}
    from app.agents import model_delivery
    from app.core.langsmith_prompts import make_client
    from langsmith import trace,tracing_context
    client=make_client(timeout_ms=10000);project='metadiet-v5-closing-offer-20261022'
    try:
        for i,c in enumerate(read(root/'frozen.json')):
            for label in (stage_labels(False) if i%2==0 else list(reversed(stage_labels(False)))):
                if (c['id'],label) in done:continue
                from scripts.eval.v5_evidence_contract import reservations
                before_tickets=reservations();traces=[];actual=model_delivery.invoke_model
                async def record(model,messages,config,**kw):
                    traces.append(json.loads(json.dumps([{'type':m.type,'content':m.content,'tool_calls':getattr(m,'tool_calls',None),'tool_call_id':getattr(m,'tool_call_id',None)} for m in messages],ensure_ascii=False,default=str)));return await actual(model,messages,config,**kw)
                with tracing_context(project_name=project,enabled=True,client=client):
                    with trace('clarification-v5-case',client=client,project_name=project,inputs={'case_id':c['id'],'condition':label},metadata=trace_metadata(c['id'],label,r['snapshots'][label])) as span:
                        with patch.object(model_delivery,'invoke_model',record):row=await core.attempt(c,r['snapshots'][label])
                        row['langsmith_trace_id']=str(span.id)
                        span.end(outputs={'status':row['status'],'no_write':row['no_write'],'model_calls':row.get('model_calls')},error=None if row['status']=='completed' else 'serving_'+row['status'])
                row['condition']=label;r['rows'].append(row);save_json(root/'main/answers.json',r)
                d=root/'main/model-inputs';d.mkdir(exist_ok=True);save_json(d/(c['id']+'-'+label+'.json'),{'case_id':c['id'],'condition':label,'input_key':row['input_key'],'model_inputs':traces,'fixture_truth':core.fixture_truth(c),'synthetic_only':True})
                print(c['id'],label,row['status'],flush=True)
                if row.get('cost_usd') is None and label=='v4' and row.get('error',{}).get('reason')=='timeout':
                    path=root/'bounded-timeouts.json';pending=read(path) if path.exists() else {'cases':{}}
                    tickets={k:v for k,v in reservations().items() if k not in before_tickets and v['stage']=='comparison'}
                    if tickets and len(pending['cases'])<2:
                        pending['cases'][c['id']]={'input_key':row['input_key'],'tickets':tickets,'billing':'unknown; reservation retained, not zero/actual settled cost'};save_json(path,pending);continue
                if row.get('error',{}).get('reason') in ['credits_depleted','quota_exhausted'] or row.get('cost_usd') is None:
                    save_json(root/'main/accounting-stop.json',{'case_id':c['id'],'error':row.get('error',{}),'reason':'capacity or unknown usage; preserve before retry'});return
    finally:client.close()


def summarize_stage(root,dev):
    stage_labels(dev)
    with patch.object(prior,'initialize',initialize),patch.object(prior,'stage_labels',stage_labels),patch.object(prior.policy,'select',lambda values: {}):
        v=prior.summarize_stage(root,False)
    from scripts.eval.v5_evidence_contract import bounded_costs
    bounds=bounded_costs(root,read(Path(root)/'main/answers.json')['rows'])
    a=v['conditions']['v4'];a.update(cost_lower_bound_usd=a['cost_usd'],cost_upper_bound_usd=a['cost_usd']+sum(bounds.values()),usage_accounted=a['usage_complete'] or len(bounds)==sum(x['cost_usd'] is None for x in read(Path(root)/'main/answers.json')['rows'] if x['condition']=='v4'),unknown_usage_cases=len(bounds))
    v.update(policy.select(v['conditions']))
    v.update(suite=policy.SUITE,not_independent_holdout=True,scope='Separate synthetic development: known regression replay +99 new cases, not independent/users',old_answers_reused=True)
    save_json(Path(root)/'main/summary.json',v);return v


_native_submit=core.submit_budgeted

def submit_recorded(client,path,model,requests,entries,budget):
    body=json.loads(core.requests_digest(client,model,requests))
    directory=Path(path).parent/'batch-requests';directory.mkdir(exist_ok=True)
    target=directory/Path(path).name
    if target.exists() and read(target)!=body:raise ValueError('Changed Batch request intent')
    if not target.exists():save_json(target,body)
    return _native_submit(client,path,model,requests,entries,budget)


@contextmanager
def bound():
    with patch.multiple(core,validate=policy.validate,runner_sha=runner_sha,initialize=initialize,audit_routes=audit_routes,generate=generate,summarize_stage=summarize_stage,stage_labels=stage_labels,submit_budgeted=submit_recorded):yield


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['offline','generate','submit','collect','summary']);p.add_argument('--folder',required=True);p.add_argument('--allow-paid',action='store_true');a=p.parse_args();a.development=False
    with bound():asyncio.run(core.main(a))
