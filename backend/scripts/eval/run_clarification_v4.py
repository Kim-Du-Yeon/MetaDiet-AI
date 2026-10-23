"""v4 experiment adapter over the unchanged, tested v3 Batch/transport core.
Only this single-process evaluation CLI temporarily binds experiment functions;
production modules and previous artifacts are never modified.
"""
import argparse,asyncio,copy,hashlib,json,math,sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'backend'));sys.path.insert(0,str(Path(__file__).resolve().parent))
from scripts.eval import run_clarification_v3 as core
from scripts.eval import clarification_v4 as policy
from app.core.prompt_release_control import _snapshot,digest
from scripts.eval.clarification_cases import request_key
from scripts.eval.clarification_execution import request_spec
from scripts.eval.cache_artifacts import save_json
read=policy.read


def runner_sha():return digest(policy.code_sha())
def stage_labels(dev):return ['v3','v4'] if dev else ['v1','v3','v4']


def initialize(root,dev):
    root=Path(root);policy.validate(root);folder=core.stagefolder(root,dev);folder.mkdir(exist_ok=True)
    old=policy.reused_report(root);snapshots={**old['prompt_snapshots'],'v4':read(root/'candidate.json')};cases=read(root/('development.json' if dev else 'frozen.json'));labels=stage_labels(dev)
    initial={'experiment':'clarification-v4-'+('development' if dev else 'exposed100'),'labels':labels,'snapshots':{k:snapshots[k] for k in labels},'conditions':policy.CONDITIONS,'runner_sha256':runner_sha(),'protocol_sha256':digest(read(root/'protocol.json')),'cases_sha256':digest(cases),'rows':[] if dev else old['rows']}
    path=folder/'answers.json'
    if not path.exists():save_json(path,initial);return initial
    saved=read(path)
    if any(saved[k]!=initial[k] for k in initial if k!='rows'):raise ValueError('Frozen execution changed')
    keys=[(r['case_id'],r['condition']) for r in saved['rows']];by={c['id']:c for c in cases}
    if len(keys)!=len(set(keys)) or any(cid not in by or label not in labels for cid,label in keys):raise ValueError('Duplicate/unknown answers')
    for row in saved['rows']:
        snapshot=snapshots[row['condition']]
        if row['input_key']!=request_key(by[row['case_id']],request_spec(snapshot)) or any(row.get('prompt_metadata',{}).get(k)!=_snapshot(snapshot).metadata().get(k) for k in ['prompt_commit_ids','prompt_hashes','prompt_bundle_sha256']):raise ValueError('Saved input/prompt identity changed')
    if not dev:
        reused={(r['case_id'],r['condition']):r for r in saved['rows']}
        if any(reused.get((r['case_id'],r['condition']))!=r for r in old['rows']):raise ValueError('Reused200 answers changed')
    return saved


_original_install=core.install

def install(root,stage):
    path=Path(root)/'budget-before.json';new=not path.exists();budget=_original_install(root,stage)
    if new:
        value=read(path);value.update(planned_new_calls='48 dev v3/v4 case generations +100 v4 case generations +24 pair/100 triple Batch judges',expected_usage_estimate_usd=[.7,1.3]);save_json(path,value)
    return budget


async def audit_routes(root):
    root=Path(root);policy.validate(root);snapshots={'v3':policy.reused_report(root)['prompt_snapshots']['v3'],'v4':read(root/'candidate.json')};rows=[]
    for c in read(root/'development.json'):
        for label,snapshot in snapshots.items():
            r=await core.attempt(c,snapshot,lambda:core.OfflineModel());rows.append({'case_id':c['id'],'condition':label,'status':r['status'],'no_write':r['no_write'],'route':r['route']})
    passed=len(rows)==48 and all(r['status']=='completed' and r['no_write'] for r in rows)
    save_json(root/'offline-route-audit.json',{'scope':'fake model route/no-write contract, never reusable paid answers','passed':passed,'code_sha256':policy.code_sha(),'rows':rows})
    if not passed:raise ValueError('Offline route contract failed')


async def generate(root,dev):
    root=Path(root);core.ensure_running(root,dev);audit=read(root/'offline-route-audit.json')
    if not audit.get('passed') or audit['code_sha256']!=policy.code_sha():raise ValueError('Passing bound offline audit required')
    if not dev and not read(root/'development/summary.json').get('development_passed'):raise ValueError('Development candidate not selected')
    r=initialize(root,dev);folder=core.stagefolder(root,dev);done={(x['case_id'],x['condition']) for x in r['rows']};labels=['v3','v4'] if dev else ['v4']
    from app.agents import model_delivery
    for i,c in enumerate(read(root/('development.json' if dev else 'frozen.json'))):
        for label in (labels if i%2==0 else list(reversed(labels))):
            if (c['id'],label) in done:continue
            traces=[];actual=model_delivery.invoke_model
            async def recording(model,messages,config,**kw):
                traces.append(json.loads(json.dumps([{'type':m.type,'content':m.content,'tool_calls':getattr(m,'tool_calls',None),'tool_call_id':getattr(m,'tool_call_id',None)} for m in messages],ensure_ascii=False,default=str)))
                return await actual(model,messages,config,**kw)
            with patch.object(model_delivery,'invoke_model',recording):row=await core.attempt(c,r['snapshots'][label])
            row['condition']=label;r['rows'].append(row);save_json(folder/'answers.json',r)
            tracefolder=folder/'model-inputs';tracefolder.mkdir(exist_ok=True);save_json(tracefolder/(c['id']+'-'+label+'.json'),{'case_id':c['id'],'condition':label,'input_key':row['input_key'],'model_inputs':traces,'fixture_truth':policy.fixture_truth(c),'synthetic_only':True})
            print(c['id'],label,row['status'],flush=True)
            if row.get('error',{}).get('reason') in ['credits_depleted','quota_exhausted']:
                save_json(folder/'capacity-stop.json',{'case_id':c['id'],'error':row['error'],'no_automatic_retry':True});return
            if row.get('cost_usd') is None:
                save_json(folder/'accounting-stop.json',{'case_id':c['id'],'reason':'unknown generation usage'});return
    return r


def summarize_stage(root,dev):
    root=Path(root);folder=core.stagefolder(root,dev);r=initialize(root,dev);cases=read(root/('development.json' if dev else 'frozen.json'));j=read(folder/'judges.json') if (folder/'judges.json').exists() else {'rows':[]};conditions={};family_results={}
    for label in stage_labels(dev):
        answers=[copy.deepcopy(x) for x in r['rows'] if x['condition']==label];grades=[]
        for row in j['rows']:
            side=next((s for s,v in row['mapping'].items() if v==label),None)
            if side:grades.append({'case_id':row['case_id'],'status':row['status'],**(row['grades'][side] if row['status']=='completed' else {})})
        by={g['case_id']:g for g in grades}
        for a in answers:a['fresh']=by.get(a['case_id'],{}).get('fresh_current_values') is True
        completed={a['case_id'] for a in answers if a['status']=='completed'};counted=[g for g in grades if g['case_id'] in completed and g['status']=='completed'];times=sorted(a['ms'] for a in answers)
        value=core.summarize(cases,answers,grades)
        value.update(correct=sum(g['correct'] for g in counted),faithful=sum(g['faithful'] for g in counted),correct_faithful=sum(g['correct'] and g['faithful'] for g in counted),unnecessary_all=sum(g.get('unnecessary_request') is True for g in grades),generation_failures=sum(a['status']!='completed' for a in answers),generation_attempts=len(answers),p95_ms=times[max(0,math.ceil(len(times)*.95)-1)] if times else None,mean_ms=sum(times)/len(times) if times else None,cost_usd=sum(a.get('cost_usd') or 0 for a in answers),usage_complete=len(answers)==len(cases) and all(a.get('usage') and a.get('cost_usd') is not None for a in answers))
        conditions[label]=value;family_results[label]={}
        for family in {c['family'] for c in cases}:
            ids={c['id'] for c in cases if c['family']==family};gs=[g for g in counted if g['case_id'] in ids]
            family_results[label][family]={'expected':len(ids),'judged':len(gs),'correct':sum(g['correct'] for g in gs),'faithful':sum(g['faithful'] for g in gs),'focused':sum(g['focused_required_question'] for g in gs),'unnecessary':sum(g['unnecessary_request'] for g in gs)}
    if dev:
        decision={'calculation_mode_controls_passed':policy.development_gate(conditions,family_results),'development_passed':policy.development_gate(conditions,family_results)}
    else:decision=policy.select(conditions)
    value={'conditions':conditions,'families':family_results,**decision,'judge_attempts':len(j['rows']),'judge_format_failed':sum(x['status']!='completed' for x in j['rows']),'old_answers_reused':not dev,'historical_grades_preserved_not_mixed_with_new':True,'not_independent_holdout':True,'source_hashes':{'answers.json':policy.sha(folder/'answers.json'),'judges.json':policy.sha(folder/'judges.json') if (folder/'judges.json').exists() else None}}
    save_json(folder/'summary.json',value);return value


@contextmanager
def bound():
    # Reuse strict Batch schemas, submission, collection, accounting and CLI.
    # Bind only evaluation globals; restore even on exception. Concurrency is1.
    with patch.multiple(core,prepare=policy.prepare,validate=policy.validate,reused_report=policy.reused_report,runner_sha=runner_sha,initialize=initialize,install=install,audit_routes=audit_routes,generate=generate,summarize_stage=summarize_stage,stage_labels=stage_labels):
        yield


async def main(args):
    with bound():await core.main(args)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','offline','generate','submit','collect','summary']);p.add_argument('--folder',required=True);p.add_argument('--development',action='store_true');p.add_argument('--allow-paid',action='store_true');asyncio.run(main(p.parse_args()))
