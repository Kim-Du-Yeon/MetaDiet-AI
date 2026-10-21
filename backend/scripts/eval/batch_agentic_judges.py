"""Native Pro Batch fallback for quota-blocked offline grading. No serving writes."""
import argparse,hashlib,json,uuid
from pathlib import Path
from benchmark_agentic_rag import ROOT,Grade,safe_error
from rejudge_agentic_rag import SYSTEM as SINGLE_SYSTEM,valid_prior_grades
from judge_agentic_pairs import SYSTEM as PAIR_SYSTEM,PairGrade,paired_payload,payload_hash
from model_routing_support import estimate_cost, PRICES
from eval_budget import Budget, BATCH_RESERVATION, micros, request_bound


def requests_digest(client, model, requests):
    """SDK serialization only; never performs a network request."""
    from google.genai.batches import _CreateBatchJobParameters_to_mldev
    from google.genai import _common
    body = _CreateBatchJobParameters_to_mldev(client._api_client, {'model':model,'src':requests})
    body.pop('_url',None)
    return json.dumps(_common.encode_unserializable_types(_common.convert_to_dict(body)),sort_keys=True,ensure_ascii=False)


def batch_cost(client, model, requests):
    return request_bound('models/'+model+':batchGenerateContent',json.loads(requests_digest(client,model,requests)))


def batch_usage_cost(model, usage):
    standard=estimate_cost(model,usage)
    if standard is None:return None
    # Pro Batch halves input/output, but cached input keeps the Standard rate.
    # Freeze the same published rate table used by the experiment.
    cached=(usage.get('input_token_details') or {}).get('cache_read',0)
    cached_cost=cached*PRICES[model][2]/1e6
    return (standard-cached_cost)*.5+cached_cost


def read_rows(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines()]


def write_grades(path, records):
    temporary=path.with_suffix('.'+uuid.uuid4().hex+'.tmp')
    temporary.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records),encoding='utf-8')
    temporary.replace(path)

def pending_old_entries(cases,attempts,prior):
    valid={(r['attempt_id'],r['condition']) for r in valid_prior_grades(prior)}
    by={c['attempt_id']:c for c in cases}; entries=[]
    for row in attempts:
        key=(row['attempt_id'],row['condition'])
        if row['status']!='completed' or key in valid: continue
        case=by[key[0]]
        entries.append({'key':'old|'+key[0]+'|'+key[1],'kind':'single','attempt_id':key[0],'condition':key[1],
            'payload':{'question':case['question'],'gold':case['gold_answer'],'answer':row['answer'],'context':row['context']}})
    return entries

def submit_once(client,path,model,requests,entries,*,budget=None):
    path=Path(path)
    if path.exists(): raise ValueError('Batch submission already entered; do not duplicate')
    intent={'state':'submission_entered','model':model,'entries':entries,
            'entries_sha256':hashlib.sha256(json.dumps(entries,sort_keys=True,ensure_ascii=False).encode()).hexdigest()}
    with path.open('x',encoding='utf-8') as file:
        file.write(json.dumps(intent,ensure_ascii=False,indent=2))
    token=None
    try:
        if budget is not None:
            bound=batch_cost(client,model,requests)
            ticket=budget.reserve('judge',bound)
            intent['budget']={'ledger':budget.path,'ticket':ticket,'reserved_usd':bound}
            path.write_text(json.dumps(intent,ensure_ascii=False,indent=2),encoding='utf-8')
            token=BATCH_RESERVATION.set({'ledger':budget.path,'ticket':ticket,'micros':micros(bound),'used':False})
        job=client.batches.create(model=model,src=requests,config={'display_name':'metadiet-rag-'+intent['entries_sha256'][:12]})
    except Exception as exc:
        intent['submission_error']=safe_error(exc)
        path.write_text(json.dumps(intent,ensure_ascii=False,indent=2),encoding='utf-8')
        raise
    finally:
        if token is not None:BATCH_RESERVATION.reset(token)
    if budget is not None:budget.bind_batch(ticket,job.name)
    intent.update(name=job.name,state=job.state.value)
    path.write_text(json.dumps(intent,ensure_ascii=False,indent=2),encoding='utf-8')
    return intent

def native_usage(metadata):
    if metadata is None or metadata.prompt_token_count is None or metadata.candidates_token_count is None: return None
    values=[metadata.prompt_token_count,metadata.candidates_token_count,metadata.thoughts_token_count or 0,metadata.cached_content_token_count or 0]
    if any(type(v) is not int or v<0 for v in values) or values[3]>values[0]:return None
    return {'input_tokens':metadata.prompt_token_count or 0,
            'output_tokens':(metadata.candidates_token_count or 0)+(metadata.thoughts_token_count or 0),
            'input_token_details':{'cache_read':metadata.cached_content_token_count or 0}}

def collect(client,path,*,budget=None):
    path=Path(path); saved=json.loads(path.read_text(encoding='utf-8'))
    if budget is not None and saved.get('budget') and budget.path!=saved['budget']['ledger']:
        raise ValueError('Wrong budget ledger for collection')
    if not saved.get('name'): raise ValueError('Unknown create outcome: inspect provider before any retry')
    job=client.batches.get(name=saved['name']); state=job.state.value
    saved['state']=state
    path.write_text(json.dumps(saved,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'batch':path.name,'state':state,'requests':len(saved['entries'])}))
    if state not in {'JOB_STATE_SUCCEEDED','JOB_STATE_PARTIALLY_SUCCEEDED','JOB_STATE_FAILED','JOB_STATE_EXPIRED','JOB_STATE_CANCELLED'}: return {'terminal':False,'budget_settled':False}
    output=path.with_suffix('.grades.jsonl')
    responses=list(job.dest.inlined_responses or []) if job.dest else []
    if responses and len(responses)!=len(saved['entries']): raise ValueError('Batch response count mismatch')
    # Providers may return inline results out of order. Settlement requires full,
    # unambiguous key coverage; never refund a missing/duplicate response.
    strict='budget' in saved
    if strict and responses:
        keys=[(r.metadata or {}).get('key') for r in responses]
        expected=[e['key'] for e in saved['entries']]
        if len(set(keys))!=len(keys) or set(keys)!=set(expected):raise ValueError('Batch key coverage mismatch')
        by_key=dict(zip(keys,responses))
        responses=[by_key[k] for k in expected]
    records=[];costs=[];usages=[]
    for index,entry in enumerate(saved['entries']):
        response=responses[index] if responses else None
        if response and response.metadata and response.metadata.get('key')!=entry['key']:
            raise ValueError('Batch key mismatch')
        body=response.response if response else None
        usage=native_usage(body.usage_metadata if body else None)
        known=batch_usage_cost(saved['model'],usage)
        costs.append(known);usages.append({'key':entry['key'],'usage':usage})
        parsed=None; error=None
        try:
            if body is None: raise ValueError('Missing batch response')
            if any('MAX_TOKENS' in str(c.finish_reason) for c in body.candidates or []):
                raise ValueError('Truncated batch response')
            schema=Grade if entry['kind']=='single' else PairGrade
            parsed=schema.model_validate_json(body.text)
        except Exception as exc: error=safe_error(exc)
        mapping={'single':entry.get('condition')} if entry['kind']=='single' else entry['mapping']
        for side,condition in mapping.items():
            grade=parsed if entry['kind']=='single' else getattr(parsed,side) if parsed is not None else None
            row={'attempt_id':entry['attempt_id'],'condition':condition,'status':'completed' if grade is not None else 'failed',
                 'correct':False,'faithful':False,'reason':'','transport':'batch','known_cost_usd':(known or 0)/len(mapping),
                 'cost_complete':known is not None,'usage':usage,'batch_key':entry['key'],
                 'payload_sha256':payload_hash(entry['payload']),
                 'rubric_sha256':hashlib.sha256((SINGLE_SYSTEM if entry['kind']=='single' else PAIR_SYSTEM).encode()).hexdigest(),
                 'judge_model':saved['model'],'judge_tokens':2048,'judge_thinking':'low'}
            if grade is not None: row.update(grade.model_dump())
            else: row['error']=error
            if entry['kind']=='pair':
                row['side']=side
                if entry['payload'][side]['serving_status']!='completed':
                    row.update(status='not_applicable_serving_failed',correct=False,faithful=False)
            records.append(row)
    if output.exists():
        # Only accounting fields may be refreshed after initially missing usage.
        # A corrupt or changed saved grade must not silently permit more spending.
        accounting={'known_cost_usd','cost_complete','usage'}
        immutable=lambda rows:[{k:v for k,v in r.items() if k not in accounting} for r in rows]
        if immutable(read_rows(output))!=immutable(records):raise ValueError('Saved grades differ; preserve and inspect')
    else:write_grades(output,records)
    settled=False
    if strict:
        reservation=saved['budget']
        if budget is not None and budget.path!=reservation['ledger']:raise ValueError('Wrong budget ledger for collection')
        budget=budget or Budget(reservation['ledger'])
        budget.bind_batch(reservation['ticket'],saved['name'])
        complete=bool(costs) and all(c is not None for c in costs)
        usage_hash=hashlib.sha256(json.dumps(usages,sort_keys=True).encode()).hexdigest()
        settled=budget.settle_batch(reservation['ticket'],saved['name'],sum(costs) if complete else None,usage_hash)
        saved['budget_settled']=settled
        if settled:saved['actual_batch_cost_usd']=sum(costs)
        path.write_text(json.dumps(saved,ensure_ascii=False,indent=2),encoding='utf-8')
        if settled:write_grades(output,records)
    print(json.dumps({'grades':len(records),'valid':sum(r['status']=='completed' for r in records)}))
    return {'terminal':True,'budget_settled':settled}

def make_requests(entries):
    from google.genai import types
    requests=[]
    for entry in entries:
        schema=Grade if entry['kind']=='single' else PairGrade
        system=SINGLE_SYSTEM if entry['kind']=='single' else PAIR_SYSTEM
        requests.append(types.InlinedRequest(contents=[types.Content(role='user',parts=[types.Part.from_text(text=json.dumps(entry['payload'],ensure_ascii=False))])],
            config=types.GenerateContentConfig(system_instruction=system,temperature=0,max_output_tokens=2048,
                thinking_config=types.ThinkingConfig(thinking_level='LOW'),response_mime_type='application/json',response_schema=schema),metadata={'key':entry['key']}))
    return requests


def main(args):
    from dotenv import load_dotenv
    load_dotenv(ROOT/'backend/.env',override=True)
    from app.core.config import get_settings
    from google import genai
    from google.genai import types
    settings=get_settings()
    client=genai.Client(api_key=settings.gemini_api_key,http_options=types.HttpOptions(timeout=60000,retry_options=types.HttpRetryOptions(attempts=1)))
    if args.action in {'collect','advance'}:
        saved=json.loads(Path(args.job).read_text(encoding='utf-8'))
        if saved.get('type')=='split_batch_campaign':
            from batch_campaign import advance
            state=advance(client,args.job,saved['identity']['model'],saved['entries'],make_requests(saved['entries']),args.budget,max_entries=saved['identity']['max_entries'],submit_next=args.action=='advance')
            print(json.dumps({'state':state,'job_record':args.job}))
        else:collect(client,args.job,budget=args.budget)
        return
    directory=Path(args.directory)
    cases=json.loads((directory/'cases.json').read_text(encoding='utf-8'))
    attempts=read_rows(directory/'attempts.jsonl')
    if args.action=='old':
        entries=pending_old_entries(cases,attempts,read_rows(directory/args.prior))
    else:
        grouped={}
        for row in attempts: grouped.setdefault(row['attempt_id'],[]).append(row)
        if len(attempts)!=2*len(cases) or len(cases)<100: raise ValueError('Wait for complete100 pairs before batch submission')
        entries=[]
        for case in cases:
            payload,mapping=paired_payload(case,grouped[case['attempt_id']])
            entries.append({'key':'pair|'+case['attempt_id'],'kind':'pair','attempt_id':case['attempt_id'],'payload':payload,'mapping':mapping})
    from batch_campaign import advance
    state=advance(client,args.job,settings.gemini_eval_model,entries,make_requests(entries),args.budget,max_entries=args.chunk_size)
    print(json.dumps({'state':state,'requests':len(entries),'job_record':args.job}))

if __name__=='__main__':
    from eval_budget import add_budget_args, activate_budget
    p=argparse.ArgumentParser(); p.add_argument('action',choices=['old','pairs','collect','advance']); p.add_argument('--directory'); p.add_argument('--prior',default='judges-20261021.jsonl'); p.add_argument('--job',required=True)
    p.add_argument('--chunk-size',type=int,choices=range(1,101),default=10)
    add_budget_args(p)
    args=p.parse_args()
    args.budget=activate_budget(args,'judge')
    try: main(args)
    except Exception as exc:
        print(json.dumps(safe_error(exc))); raise SystemExit(1)
