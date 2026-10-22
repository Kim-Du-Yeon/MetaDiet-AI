"""Single-process holdout adapter; reuse strict Batch and original runtime fixture."""
import argparse,asyncio,copy,json,sys
from pathlib import Path
from contextlib import contextmanager
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'backend'));sys.path.insert(0,str(Path(__file__).resolve().parent))
from scripts.eval import run_clarification_v3 as core,run_clarification_v4 as prior,clarification_holdout as policy
from scripts.eval.clarification_execution import request_spec
from scripts.eval.clarification_cases import request_key
from scripts.eval.cache_artifacts import save_json
from app.core.prompt_release_control import _snapshot,digest
read=policy.read


def stage_labels(dev):
    if dev:raise ValueError('No tuning on prospective holdout')
    return ['v1','v4']


def runner_sha():return digest(policy.code_sha())


def initialize(root,dev):
    stage_labels(dev);root=Path(root);policy.validate(root);candidate=read(root/'candidate.json');folder=core.stagefolder(root,False);folder.mkdir(exist_ok=True)
    cases=read(root/'frozen.json');initial={'experiment':policy.SUITE,'labels':['v1','v4'],'snapshots':{'v1':candidate['baseline'],'v4':candidate['snapshot']},'conditions':policy.CONDITIONS,'runner_sha256':runner_sha(),'protocol_sha256':digest(read(root/'protocol.json')),'cases_sha256':digest(cases),'rows':[]}
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


async def generate(root,dev):
    stage_labels(dev);root=Path(root);core.ensure_running(root,False);audit=read(root/'offline-route-audit.json')
    if not audit['passed'] or audit['code_sha256']!=policy.code_sha():raise ValueError('Offline audit required')
    r=initialize(root,False);done={(x['case_id'],x['condition']) for x in r['rows']}
    from app.agents import model_delivery
    for i,c in enumerate(read(root/'frozen.json')):
        for label in (stage_labels(False) if i%2==0 else list(reversed(stage_labels(False)))):
            if (c['id'],label) in done:continue
            traces=[];actual=model_delivery.invoke_model
            async def record(model,messages,config,**kw):
                traces.append(json.loads(json.dumps([{'type':m.type,'content':m.content,'tool_calls':getattr(m,'tool_calls',None),'tool_call_id':getattr(m,'tool_call_id',None)} for m in messages],ensure_ascii=False,default=str)));return await actual(model,messages,config,**kw)
            with patch.object(model_delivery,'invoke_model',record):row=await core.attempt(c,r['snapshots'][label])
            row['condition']=label;r['rows'].append(row);save_json(root/'main/answers.json',r)
            d=root/'main/model-inputs';d.mkdir(exist_ok=True);save_json(d/(c['id']+'-'+label+'.json'),{'case_id':c['id'],'condition':label,'input_key':row['input_key'],'model_inputs':traces,'fixture_truth':core.fixture_truth(c),'synthetic_only':True})
            print(c['id'],label,row['status'],flush=True)
            if row.get('error',{}).get('reason') in ['credits_depleted','quota_exhausted'] or row.get('cost_usd') is None:
                save_json(root/'main/accounting-stop.json',{'case_id':c['id'],'error':row.get('error',{}),'reason':'capacity or unknown usage; preserve before retry'});return


def summarize_stage(root,dev):
    stage_labels(dev)
    with patch.object(prior,'initialize',initialize),patch.object(prior,'stage_labels',stage_labels),patch.object(prior.policy,'select',policy.select):
        v=prior.summarize_stage(root,False)
    v.update(suite=policy.SUITE,not_independent_holdout=False,scope='Prospective new synthetic holdout after v4 freeze; same author/families, not external clinical/user study',old_answers_reused=False)
    save_json(Path(root)/'main/summary.json',v);return v


@contextmanager
def bound():
    with patch.multiple(core,validate=policy.validate,runner_sha=runner_sha,initialize=initialize,audit_routes=audit_routes,generate=generate,summarize_stage=summarize_stage,stage_labels=stage_labels):yield


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['offline','generate','submit','collect','summary']);p.add_argument('--folder',required=True);p.add_argument('--allow-paid',action='store_true');a=p.parse_args();a.development=False
    with bound():asyncio.run(core.main(a))
