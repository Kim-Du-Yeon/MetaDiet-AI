"""Read-only v3 development and diagnostic100 runner. No serving writes or promotion."""
import argparse,asyncio,copy,hashlib,json,math,sqlite3,sys
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'backend'));sys.path.insert(0,str(Path(__file__).resolve().parent))
from scripts.eval.clarification_v3 import *
from app.core.prompt_release_control import _snapshot
from scripts.eval.clarification_execution import price_usage
from scripts.eval.clarification_cases import request_key
from scripts.eval.run_clarification_comparison import attempt,OfflineModel
from scripts.eval.cache_artifacts import save_json
from scripts.eval import eval_budget
from scripts.eval.batch_agentic_judges import submit_once,native_usage,batch_usage_cost,requests_digest
MODEL='gemini-3.1-pro-preview'


def runner_sha():return hashlib.sha256(Path(__file__).read_text(encoding='utf-8-sig').encode()).hexdigest()
def stagefolder(root,dev):return Path(root)/('development' if dev else 'main')


def initialize(root,dev):
    root=Path(root);validate(root);folder=stagefolder(root,dev);folder.mkdir(exist_ok=True)
    old=reused_report(root);snapshots={**old['prompt_snapshots'],'v3':read(root/'candidate.json')};cases=read(root/('development.json' if dev else 'frozen.json'));labels=['v2','v3'] if dev else ['v1','v2','v3']
    initial={'experiment':'clarification-v3-'+('development' if dev else 'exposed100'),'labels':labels,'snapshots':{k:snapshots[k] for k in labels},'conditions':CONDITIONS,'runner_sha256':runner_sha(),'protocol_sha256':digest(read(root/'protocol.json')),'cases_sha256':digest(cases),'rows':[] if dev else old['rows']}
    path=folder/'answers.json'
    if path.exists():
        saved=read(path)
        if any(saved[k]!=initial[k] for k in initial if k!='rows'):raise ValueError('Frozen execution changed')
        keys=[(r['case_id'],r['condition']) for r in saved['rows']]
        if len(keys)!=len(set(keys)) or any(cid not in {c['id'] for c in cases} or label not in labels for cid,label in keys):raise ValueError('Duplicate/unknown answers')
        cases_by_id={c['id']:c for c in cases}
        for row in saved['rows']:
            snap=snapshots[row['condition']]
            if row.get('input_key')!=request_key(cases_by_id[row['case_id']],request_spec(snap)) or any(row.get('prompt_metadata',{}).get(k)!=_snapshot(snap).metadata().get(k) for k in ['prompt_commit_ids','prompt_hashes','prompt_bundle_sha256']):raise ValueError('Saved input/prompt identity changed')
        if not dev:
            by={(r['case_id'],r['condition']):r for r in saved['rows']}
            if any(by.get((r['case_id'],r['condition']))!=r for r in old['rows']):raise ValueError('Reused200 answers changed')
        return saved
    save_json(path,initial);return initial


def install(root,stage):
    # Existing ledger and historical caps remain on disk; prior user waiver allows this new experiment.
    original=read(FOLDER/'complete100/budget-after.json');eval_budget.TOTAL=17.139139
    eval_budget.LIMITS={**original['stages']}
    for key,extra in [('development',1.),('comparison',2.),('judge',4.)]:eval_budget.LIMITS[key]+=extra
    b=eval_budget.Budget('D:/AX/diet_agent/tmp/eval-budget.sqlite')
    path=Path(root)/'budget-before.json'
    if not path.exists():
        with b.connect() as db:rows=list(db.execute('SELECT id,stage,amount,settled FROM costs ORDER BY id'))
        save_json(path,{'snapshot':b.summary(),'prior_cost_rows':rows,'historical_incremental_cap_waived':True,'planned_new_calls':'48 dev generations +100 v3 generations +24 pair/100 triple Batch judge requests','expected_usage_estimate_usd':[1,2],'stage_caps_this_experiment':eval_budget.LIMITS})
    else:
        with b.connect() as db:now={r[0]:list(r) for r in db.execute('SELECT id,stage,amount,settled FROM costs')}
        if any(now.get(r[0])!=r for r in read(path)['prior_cost_rows']):raise ValueError('Historical cost rows changed')
    eval_budget.install_transport_guard(b,stage);return b


def save_budget(root,b):
    before=read(Path(root)/'budget-before.json')['snapshot']['committed_usd'];save_json(Path(root)/'budget-after.json',{**b.summary(),'incremental_committed_usd':round(b.summary()['committed_usd']-before,6)})


def ensure_running(root,dev):
    folder=stagefolder(root,dev)
    for name in ['capacity-stop.json','accounting-stop.json','submission-error.json']:
        if (folder/name).exists():raise ValueError('Saved failure requires explicit review: '+name)


async def audit_routes(root):
    root=Path(root);validate(root);old=reused_report(root)
    snapshots={'v2':old['prompt_snapshots']['v2'],'v3':read(root/'candidate.json')};rows=[]
    for case in read(root/'development.json'):
        for label,snapshot in snapshots.items():
            row=await attempt(case,snapshot,lambda:OfflineModel())
            rows.append({'case_id':case['id'],'condition':label,'status':row['status'],'route':row.get('route'),'no_write':row.get('no_write')})
    save_json(root/'offline-route-audit.json',{'scope':'fake model route contract only; not quality, latency, cost or reusable paid answers','rows':rows})


async def generate(root,dev):
    ensure_running(root,dev)
    root=Path(root);folder=stagefolder(root,dev);r=initialize(root,dev);cases=read(root/('development.json' if dev else 'frozen.json'))
    if not dev:
        gate=read(root/'development/summary.json')
        if not gate.get('development_passed'):raise ValueError('Development candidate not selected; inspect before100')
    done={(x['case_id'],x['condition']) for x in r['rows']};labels=['v2','v3'] if dev else ['v3']
    for i,c in enumerate(cases):
        for label in (labels if i%2==0 else list(reversed(labels))):
            if (c['id'],label) in done:continue
            traces=[]
            from app.agents import model_delivery
            actual=model_delivery.invoke_model
            async def recording(model,messages,config,**kw):
                traces.append(json.loads(json.dumps([{'type':m.type,'content':m.content,'tool_calls':getattr(m,'tool_calls',None),'tool_call_id':getattr(m,'tool_call_id',None)} for m in messages],ensure_ascii=False,default=str)))
                return await actual(model,messages,config,**kw)
            with patch.object(model_delivery,'invoke_model',recording):row=await attempt(c,r['snapshots'][label])
            row['condition']=label;r['rows'].append(row);save_json(folder/'answers.json',r)
            tracedir=folder/'model-inputs';tracedir.mkdir(exist_ok=True);save_json(tracedir/(c['id']+'-'+label+'.json'),{'case_id':c['id'],'condition':label,'input_key':row['input_key'],'model_inputs':traces,'fixture_truth':fixture_truth(c),'synthetic_only':True})
            print(c['id'],label,row['status'],flush=True)
            if row.get('error',{}).get('reason') in ['credits_depleted','quota_exhausted']:
                save_json(folder/'capacity-stop.json',{'case_id':c['id'],'error':row['error'],'no_automatic_retry':True});return
            if row.get('cost_usd') is None:
                save_json(folder/'accounting-stop.json',{'case_id':c['id'],'reason':'unknown generation usage'});return
    return r


def build_judges(root,dev):
    root=Path(root);folder=stagefolder(root,dev);r=initialize(root,dev);cases=read(root/('development.json' if dev else 'frozen.json'));labels=r['labels'];by={(x['case_id'],x['condition']):x for x in r['rows']}
    if len(by)!=len(cases)*len(labels):raise ValueError('Complete all generation attempts before judging')
    saved=read(folder/'judges.json')['rows'] if (folder/'judges.json').exists() else [];done={x['case_id'] for x in saved};reserved=set()
    for path in folder.glob('batch-*.json'):reserved.update(e['key'] for e in read(path)['entries'])
    es=[];requests=[];system=format_system(len(labels))
    for i,c in enumerate(cases):
        if c['id'] in done or c['id'] in reserved:continue
        order=labels[i%len(labels):]+labels[:i%len(labels)];mapping=dict(zip('abc'[:len(labels)],order))
        payload={'case':c,'fixture_truth':fixture_truth(c),'historical_trace_limit':'Old answers have no full tool transcript; fixture facts are deterministic available truth, not proof of a tool read.',**{s:by[(c['id'],label)]['answer'] for s,label in mapping.items()}}
        e={'key':c['id'],'case_id':c['id'],'mapping':mapping,'answer_binding':digest(payload),'system_sha256':hashlib.sha256(system.encode()).hexdigest(),'n_conditions':len(labels)}
        req={'contents':[{'role':'user','parts':[{'text':json.dumps(payload,ensure_ascii=False)}]}],'metadata':{'key':c['id']},'config':{'system_instruction':system,'temperature':0,'thinking_config':{'thinking_level':'low'},'max_output_tokens':2048,'response_mime_type':'application/json','response_json_schema':grade_schema(len(labels))}}
        es.append(e);requests.append(req)
    return es,requests


def submit_budgeted(client,path,model,requests,entries,budget):
    # Patch the defining globals, not another import alias of the same helper.
    with patch.dict(submit_once.__globals__,{'BATCH_RESERVATION':eval_budget.BATCH_RESERVATION}):
        return submit_once(client,path,model,requests,entries,budget=budget)


def submit(root,dev,client,budget):
    ensure_running(root,dev)
    folder=stagefolder(root,dev)
    if any(not read(p).get('collected') for p in folder.glob('batch-*.json')):raise ValueError('Pending batch; never duplicate')
    if (folder/'accounting-stop.json').exists() or (folder/'submission-error.json').exists():raise ValueError('Saved failure requires explicit review')
    es,requests=build_judges(root,dev)
    if not es:print('Nothing unsubmitted');return
    # Pair contract is already live-validated; three-answer layout gets2 actual pilot requests included in100.
    if not dev:
        prior=read(folder/'judges.json')['rows'] if (folder/'judges.json').exists() else []
        if not list(folder.glob('batch-*.json')):es,requests=es[:2],requests[:2]
        elif len(prior)<2 or any(r['status']!='completed' for r in prior[:2]):raise ValueError('Threeway format pilot not passed; preserve before more calls')
    wire=json.loads(requests_digest(client,MODEL,requests));actual=wire['batch']['inputConfig']['requests']['requests']
    if len(actual)!=len(requests) or any(e['request']['generationConfig'].get('responseJsonSchema')!=grade_schema(len(stage_labels(dev))) for e in actual):raise ValueError('Native schema serialization changed')
    path=folder/('batch-'+digest(es)[:16]+'.json')
    try:
        job=submit_budgeted(client,path,MODEL,requests,es,budget)
    except Exception as exc:save_json(folder/'submission-error.json',{'type':type(exc).__name__});raise
    print(json.dumps({'state':job['state'],'requests':len(es),'maximum_reservation_usd':job['budget']['reserved_usd']}))


def stage_labels(dev):return ['v2','v3'] if dev else ['v1','v2','v3']


def collect(root,dev,client,budget):
    folder=stagefolder(root,dev);path=folder/'judges.json';j=read(path) if path.exists() else {'rows':[]};by_old={x['case_id']:x for x in j['rows']}
    for jobpath in folder.glob('batch-*.json'):
        saved=read(jobpath)
        if saved.get('collected'):continue
        if not saved.get('name'):raise ValueError('Unknown submit outcome; no retry')
        job=client.batches.get(name=saved['name']);saved['state']=job.state.value;save_json(jobpath,saved);print(json.dumps({'batch':jobpath.name,'state':saved['state']}))
        if saved['state'] not in ['JOB_STATE_SUCCEEDED','JOB_STATE_PARTIALLY_SUCCEEDED','JOB_STATE_FAILED','JOB_STATE_EXPIRED','JOB_STATE_CANCELLED']:continue
        responses=list(job.dest.inlined_responses or []) if job.dest else [];by={(x.metadata or {}).get('key'):x for x in responses}
        if len(by)!=len(responses) or set(by)!={e['key'] for e in saved['entries']}:save_json(folder/'accounting-stop.json',{'reason':'missing/duplicate keys; full reservation retained'});raise ValueError('Incomplete key coverage')
        report=initialize(root,dev);cases_by_id={c['id']:c for c in read(Path(root)/('development.json' if dev else 'frozen.json'))};answers={(r['case_id'],r['condition']):r for r in report['rows']}
        costs=[];usages=[]
        for e in saved['entries']:
            case=cases_by_id[e['case_id']]
            payload={'case':case,'fixture_truth':fixture_truth(case),'historical_trace_limit':'Old answers have no full tool transcript; fixture facts are deterministic available truth, not proof of a tool read.',**{side:answers[(case['id'],label)]['answer'] for side,label in e['mapping'].items()}}
            if digest(payload)!=e['answer_binding'] or e['system_sha256']!=hashlib.sha256(format_system(len(report['labels'])).encode()).hexdigest():raise ValueError('Submitted answer/rubric binding changed')
            body=by[e['key']].response;usage=native_usage(body.usage_metadata if body else None);cost=batch_usage_cost(MODEL,usage);costs.append(cost);usages.append({'key':e['key'],'usage':usage});raw={'text':body.text if body else None,'finish_reasons':[str(c.finish_reason) for c in body.candidates or []] if body else [],'usage':usage}
            row={**e,'status':'failed','usage':usage,'batch_cost_usd':cost,'raw_sha256':digest(raw)}
            try:
                if body is None or any('MAX_TOKENS' in f for f in raw['finish_reasons']):raise ValueError('Missing/truncated output')
                row.update(status='completed',grades=parse_grades(raw['text'],e['n_conditions']))
            except Exception as exc:row['error']={'type':type(exc).__name__,'reason':'strict_schema_or_response'}
            rawdir=folder/'raw-judges';rawdir.mkdir(exist_ok=True);save_json(rawdir/(e['case_id']+'.json'),raw)
            if e['case_id'] in by_old and by_old[e['case_id']]!=row:raise ValueError('Conflicting saved grade')
            by_old[e['case_id']]=row
        actual=sum(costs) if all(x is not None for x in costs) else None
        budget.settle_batch(saved['budget']['ticket'],saved['name'],actual,digest(usages))
        if actual is None:save_json(folder/'accounting-stop.json',{'reason':'unknown usage; reservation retained'});raise ValueError('Unknown usage')
        j['rows']=list(by_old.values());save_json(path,j);saved.update(collected=True,actual_batch_cost_usd=actual);save_json(jobpath,saved)
    summarize_stage(root,dev)


def summarize_stage(root,dev):
    folder=stagefolder(root,dev);r=initialize(root,dev);cases=read(Path(root)/('development.json' if dev else 'frozen.json'));j=read(folder/'judges.json') if (folder/'judges.json').exists() else {'rows':[]};conditions={}
    for label in stage_labels(dev):
        answers=[copy.deepcopy(x) for x in r['rows'] if x['condition']==label];grades=[]
        for row in j['rows']:
            side=next((s for s,v in row['mapping'].items() if v==label),None)
            if side:grades.append({'case_id':row['case_id'],'status':row['status'],**(row['grades'][side] if row['status']=='completed' else {})})
        by={x['case_id']:x for x in grades}
        for a in answers:a['fresh']=by.get(a['case_id'],{}).get('fresh_current_values') is True
        completed_ids={a['case_id'] for a in answers if a['status']=='completed'}
        counted=[g for g in grades if g['case_id'] in completed_ids and g['status']=='completed']
        v=summarize(cases,answers,grades);times=sorted(a['ms'] for a in answers)
        v.update(correct=sum(g.get('correct') is True for g in counted),faithful=sum(g.get('faithful') is True for g in counted),correct_faithful=sum(g.get('correct') is True and g.get('faithful') is True for g in counted),unnecessary_all=sum(g.get('unnecessary_request') is True for g in grades),generation_failures=sum(a['status']!='completed' for a in answers),generation_attempts=len(answers),p95_ms=times[max(0,math.ceil(len(times)*.95)-1)] if times else None,mean_ms=sum(times)/len(times) if times else None,cost_usd=sum(a.get('cost_usd') or 0 for a in answers),usage_complete=len(answers)==len(cases) and all(a.get('usage') and a.get('cost_usd') is not None for a in answers))
        conditions[label]=v
    decision=({'development_passed':all(v['judged']==24 and v['generation_failures']==0 and v['usage_complete'] for v in conditions.values()) and conditions['v3']['passed']>=conditions['v2']['passed'] and conditions['v3']['unsafe_commitments']<=conditions['v2']['unsafe_commitments']} if dev else select(conditions))
    result={'conditions':conditions,**decision,'judge_attempts':len(j['rows']),'judge_format_failed':sum(x['status']!='completed' for x in j['rows']),'old_judge_not_reused_because_context_changed':True,'old_answers_reused':not dev,'not_independent_holdout':True,'source_hashes':{'answers.json':sha(folder/'answers.json'),'judges.json':sha(folder/'judges.json') if (folder/'judges.json').exists() else None}}
    save_json(folder/'summary.json',result);return result


async def main(args):
    root=Path(args.folder)
    if args.action=='prepare':prepare(root);return
    validate(root)
    if args.action=='summary':print(json.dumps(summarize_stage(root,args.development)));return
    if args.action=='offline':
        await audit_routes(root);return
    if not args.allow_paid:raise ValueError('Explicit paid permission required')
    from dotenv import load_dotenv
    load_dotenv(ROOT/'backend/.env',override=True)
    b=install(root,'development' if args.development and args.action=='generate' else 'comparison' if args.action=='generate' else 'judge')
    try:
        if args.action=='generate':await generate(root,args.development)
        else:
            from app.core.config import get_settings
            from google import genai
            client=genai.Client(api_key=get_settings().gemini_api_key,http_options={'retry_options':{'attempts':1},'timeout':60000})
            try:
                if args.action=='submit':initialize(root,args.development);submit(root,args.development,client,b)
                else:collect(root,args.development,client,b)
            finally:client.close()
    finally:save_budget(root,b)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','offline','generate','submit','collect','summary']);p.add_argument('--folder',required=True);p.add_argument('--development',action='store_true');p.add_argument('--allow-paid',action='store_true');asyncio.run(main(p.parse_args()))
