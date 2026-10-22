"""Batch transport for the unchanged unfinished clarification judge payloads."""
import argparse,hashlib,json,sys
from pathlib import Path
from pydantic import BaseModel,ConfigDict
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'backend'));sys.path.insert(0,str(ROOT/'backend/scripts/eval'))
from scripts.eval import eval_budget
from scripts.eval.resume_clarification_judging import prepare,validate_resume,quota_details
from scripts.eval.clarification_execution import FOLDER,RUBRIC,pair_payload,digest,read_cases
from scripts.eval.cache_artifacts import save_json
from scripts.eval.run_clarification_comparison import install_budget,summarize_folder
from batch_agentic_judges import submit_once,native_usage,batch_usage_cost,batch_cost

class Grade(BaseModel):
    model_config=ConfigDict(strict=True,extra='forbid')
    correct:bool;faithful:bool;fresh_current_values:bool;unnecessary_request:bool;focused_required_question:bool;unsafe_commitment:bool;reason:str
class Pair(BaseModel):
    model_config=ConfigDict(strict=True,extra='forbid')
    a:Grade;b:Grade
MODEL='gemini-3.1-pro-preview'


def parse_grade(text):
    value=json.loads(text)
    if isinstance(value,dict) and set(value)=={'a','b'}:return Pair.model_validate(value)
    fields=set(Grade.model_fields)
    expected={'a','b'}|{side+'_'+key for side in ['a','b'] for key in fields}
    shared={'a','b','reason'}|{side+'_'+key for side in ['a','b'] for key in fields-{'reason'}}
    if isinstance(value,dict) and set(value)==shared:
        # The original shared rationale stays verbatim; no score is derived from it.
        if any(value[side] is not None and type(value[side]) is not bool for side in ['a','b']):raise ValueError('Unrecognized root summary flag')
        return Pair.model_validate({side:{**{key:value[side+'_'+key] for key in fields-{'reason'}},'reason':value['reason']} for side in ['a','b']})
    if not isinstance(value,dict) or set(value)!=expected or any(value[side] is not None and type(value[side]) is not bool for side in ['a','b']):raise ValueError('Unrecognized batch grade shape')
    # Root a/b are redundant provider summary flags, never used as metric grades.
    # Only complete, strictly typed per-field grades are mapped; no values inferred.
    return Pair.model_validate({side:{key:value[side+'_'+key] for key in fields} for side in ['a','b']})

def build(folder):
    folder=Path(folder);validate_resume(folder)
    r=json.loads((folder/'paired.json').read_text(encoding='utf-8'));j=json.loads((folder/'judges.json').read_text(encoding='utf-8'))
    done={x['case_id'] for x in j['rows']};reserved=set()
    for p in folder.glob('batch-*.json'):
        job=json.loads(p.read_text(encoding='utf-8'));reserved.update(e['key'] for e in job['entries'])
    entries=[];requests=[]
    for i,c in enumerate(read_cases()):
        if c['id'] in done or c['id'] in reserved:continue
        payload,mapping=pair_payload(c,r['rows'],i);e={'key':c['id'],'case_id':c['id'],'mapping':mapping,'answer_binding':digest(payload)}
        entries.append(e);requests.append({'contents':[{'role':'user','parts':[{'text':json.dumps(payload,ensure_ascii=False)}]}],'metadata':{'key':c['id']},'config':{'system_instruction':RUBRIC,'temperature':0,'max_output_tokens':2048,'thinking_config':{'thinking_level':'low'},'response_mime_type':'application/json','response_json_schema':{'type':'object','properties':{side:Grade.model_json_schema() for side in ['a','b']},'required':['a','b'],'additionalProperties':False}}})
    return entries,requests

def submit(client,folder,budget,chunks=1):
    folder=Path(folder)
    if (folder/'accounting-stop.json').exists():raise ValueError('Unresolved batch accounting stop; no new submissions')
    entries,requests=build(folder)
    for offset in range(0,min(len(entries),chunks*8),8):
        es=entries[offset:offset+8];rs=requests[offset:offset+8];bound=batch_cost(client,MODEL,rs)
        if bound>budget.available('judge'):
            print(json.dumps({'state':'waiting_for_settlement','pending_unsubmitted':len(entries)-offset,'next_bound_usd':bound}));return
        path=folder/('batch-'+hashlib.sha256(json.dumps(es,sort_keys=True).encode()).hexdigest()[:16]+'.json')
        try:
            with patch('batch_agentic_judges.BATCH_RESERVATION',eval_budget.BATCH_RESERVATION):
                job=submit_once(client,path,MODEL,rs,es,budget=budget)
        except Exception as exc:save_json(folder/'batch-submit-error.json',quota_details(exc));raise
        print(json.dumps({'batch':path.name,'state':job['state'],'pairs':len(es),'reserved_bound_usd':bound}))

def collect(client,folder,budget):
    folder=Path(folder);validate_resume(folder);jp=folder/'judges.json';j=json.loads(jp.read_text(encoding='utf-8'))
    for path in sorted(folder.glob('batch-*.json')):
        saved=json.loads(path.read_text(encoding='utf-8'))
        if saved.get('collected') and saved.get('parser_version')==3:continue
        if not saved.get('name'):raise ValueError('Uncertain batch submission; no duplicate allowed')
        if saved['budget']['ledger']!=budget.path:raise ValueError('Batch ledger changed')
        job=client.batches.get(name=saved['name']);saved['state']=job.state.value;save_json(path,saved)
        print(json.dumps({'batch':path.name,'state':saved['state']}))
        if saved['state'] not in {'JOB_STATE_SUCCEEDED','JOB_STATE_PARTIALLY_SUCCEEDED','JOB_STATE_FAILED','JOB_STATE_EXPIRED','JOB_STATE_CANCELLED'}:continue
        responses=list(job.dest.inlined_responses or []) if job.dest else []
        by={(x.metadata or {}).get('key'):x for x in responses};expected={e['key'] for e in saved['entries']}
        if len(by)!=len(responses) or set(by)!=expected:
            save_json(folder/'accounting-stop.json',{'batch':path.name,'reason':'Incomplete key/usage coverage; reservation retained'})
            raise ValueError('Incomplete batch key/usage coverage; reservation retained')
        costs=[];usages=[];rows=[]
        for e in saved['entries']:
            response=by[e['key']];body=response.response;usage=native_usage(body.usage_metadata if body else None)
            cost=batch_usage_cost(MODEL,usage);costs.append(cost);usages.append({'key':e['key'],'usage':usage})
            row={**e,'status':'failed','usage':[usage] if usage else [],'transport':'batch','batch_cost_usd':cost}
            try:
                if body is None or any('MAX_TOKENS' in str(c.finish_reason) for c in body.candidates or []):raise ValueError('Missing/truncated batch grade')
                row.update(status='completed',grades=parse_grade(body.text).model_dump())
            except Exception as exc:row['error']={'type':type(exc).__name__,'reason':'batch_parse_or_response_error'}
            rawdir=folder/'raw-grades';rawdir.mkdir(exist_ok=True)
            raw={'text':body.text if body else None,'finish_reasons':[str(c.finish_reason) for c in body.candidates or []] if body else [],'usage':usage}
            save_json(rawdir/(e['key']+'.json'),raw);row['raw_sha256']=digest(raw)
            rows.append(row)
        actual=sum(costs) if all(v is not None for v in costs) else None
        budget.settle_batch(saved['budget']['ticket'],saved['name'],actual,digest(usages))
        if actual is None:
            save_json(folder/'accounting-stop.json',{'batch':path.name,'reason':'Unknown usage; reservation retained'})
            raise ValueError('Unknown batch usage; reservation retained')
        existing={x['case_id']:x for x in j['rows']}
        for row in rows:
            if row['case_id'] in existing and existing[row['case_id']]!=row:
                prior=existing[row['case_id']]
                if prior.get('transport')!='batch' or prior['status']!='failed' or prior.get('answer_binding')!=row['answer_binding'] or prior.get('usage')!=row['usage']:raise ValueError('Conflicting saved batch grade')
                history=folder/'parse-history.json';records=json.loads(history.read_text(encoding='utf-8')) if history.exists() else [];records.append({'prior':prior,'replacement_sha256':digest(row),'reason':'Strict lossless JSON shape normalization; no new model call'});save_json(history,records)
            existing[row['case_id']]=row
        j['rows']=list(existing.values());save_json(jp,j)
        saved.update(collected=True,parser_version=3,actual_batch_cost_usd=actual,usage_hash=digest(usages));save_json(path,saved)
    save_json(folder/'budget-after.json',budget.summary());summarize_folder(folder)

def main(args):
    from dotenv import load_dotenv
    load_dotenv(ROOT/'backend/.env',override=True);folder=Path(args.folder)
    if args.action=='prepare':print(json.dumps(prepare(FOLDER/'run-final',folder)));return
    if not args.allow_paid:raise ValueError('Explicit paid authorization required')
    validate_resume(folder)
    if (folder/'batch-submit-error.json').exists():raise ValueError('Saved submission failure; review before more calls')
    from app.core.config import get_settings
    from google import genai
    budget=install_budget(args.budget,'judge');client=genai.Client(api_key=get_settings().gemini_api_key,http_options={'retry_options':{'attempts':1},'timeout':60000})
    if args.action=='submit':submit(client,folder,budget,args.chunks)
    else:collect(client,folder,budget)
    save_json(folder/'budget-after.json',budget.summary())

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','submit','collect']);p.add_argument('--folder',required=True);p.add_argument('--budget',default=str(FOLDER/'resume-budget.json'));p.add_argument('--chunks',type=int,default=1);p.add_argument('--allow-paid',action='store_true');main(p.parse_args())
