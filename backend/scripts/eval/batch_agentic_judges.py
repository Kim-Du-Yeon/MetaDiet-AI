"""Native Pro Batch fallback for quota-blocked offline grading. No serving writes."""
import argparse,hashlib,json
from pathlib import Path
from benchmark_agentic_rag import ROOT,Grade,safe_error
from rejudge_agentic_rag import SYSTEM as SINGLE_SYSTEM,valid_prior_grades
from judge_agentic_pairs import SYSTEM as PAIR_SYSTEM,PairGrade,paired_payload,payload_hash
from model_routing_support import estimate_cost


def read_rows(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines()]

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

def submit_once(client,path,model,requests,entries):
    path=Path(path)
    if path.exists(): raise ValueError('Batch submission already entered; do not duplicate')
    intent={'state':'submission_entered','model':model,'entries':entries,
            'entries_sha256':hashlib.sha256(json.dumps(entries,sort_keys=True,ensure_ascii=False).encode()).hexdigest()}
    with path.open('x',encoding='utf-8') as file:
        file.write(json.dumps(intent,ensure_ascii=False,indent=2))
    try:
        job=client.batches.create(model=model,src=requests,config={'display_name':'metadiet-rag-'+intent['entries_sha256'][:12]})
    except Exception as exc:
        intent['submission_error']=safe_error(exc)
        path.write_text(json.dumps(intent,ensure_ascii=False,indent=2),encoding='utf-8')
        raise
    intent.update(name=job.name,state=job.state.value)
    path.write_text(json.dumps(intent,ensure_ascii=False,indent=2),encoding='utf-8')
    return intent

def native_usage(metadata):
    if metadata is None or metadata.prompt_token_count is None or metadata.candidates_token_count is None: return None
    return {'input_tokens':metadata.prompt_token_count or 0,
            'output_tokens':(metadata.candidates_token_count or 0)+(metadata.thoughts_token_count or 0),
            'input_token_details':{'cache_read':metadata.cached_content_token_count or 0}}

def collect(client,path):
    path=Path(path); saved=json.loads(path.read_text(encoding='utf-8'))
    if not saved.get('name'): raise ValueError('Unknown create outcome: inspect provider before any retry')
    job=client.batches.get(name=saved['name']); state=job.state.value
    saved['state']=state
    path.write_text(json.dumps(saved,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'batch':path.name,'state':state,'requests':len(saved['entries'])}))
    if state not in {'JOB_STATE_SUCCEEDED','JOB_STATE_PARTIALLY_SUCCEEDED','JOB_STATE_FAILED','JOB_STATE_EXPIRED','JOB_STATE_CANCELLED'}: return
    output=path.with_suffix('.grades.jsonl')
    if output.exists(): return
    responses=list(job.dest.inlined_responses or []) if job.dest else []
    if responses and len(responses)!=len(saved['entries']): raise ValueError('Batch response count mismatch')
    records=[]
    for index,entry in enumerate(saved['entries']):
        response=responses[index] if responses else None
        if response and response.metadata and response.metadata.get('key')!=entry['key']:
            raise ValueError('Batch key mismatch')
        body=response.response if response else None
        usage=native_usage(body.usage_metadata if body else None)
        known=estimate_cost(saved['model'],usage)
        known=known*.5 if known is not None else None
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
    output.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records),encoding='utf-8')
    print(json.dumps({'grades':len(records),'valid':sum(r['status']=='completed' for r in records)}))

def main(args):
    from dotenv import load_dotenv
    load_dotenv(ROOT/'backend/.env',override=True)
    from app.core.config import get_settings
    from google import genai
    from google.genai import types
    settings=get_settings()
    client=genai.Client(api_key=settings.gemini_api_key,http_options=types.HttpOptions(timeout=60000,retry_options=types.HttpRetryOptions(attempts=1)))
    if args.action=='collect':
        collect(client,args.job); return
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
    requests=[]
    for entry in entries:
        schema=Grade if entry['kind']=='single' else PairGrade
        system=SINGLE_SYSTEM if entry['kind']=='single' else PAIR_SYSTEM
        requests.append(types.InlinedRequest(contents=[types.Content(role='user',parts=[types.Part.from_text(text=json.dumps(entry['payload'],ensure_ascii=False))])],
            config=types.GenerateContentConfig(system_instruction=system,temperature=0,max_output_tokens=2048,
                thinking_config=types.ThinkingConfig(thinking_level='LOW'),response_mime_type='application/json',response_schema=schema),metadata={'key':entry['key']}))
    job=submit_once(client,args.job,settings.gemini_eval_model,requests,entries)
    print(json.dumps({'state':job['state'],'requests':len(entries),'job_record':args.job}))

if __name__=='__main__':
    from eval_budget import add_budget_args, activate_budget
    p=argparse.ArgumentParser(); p.add_argument('action',choices=['old','pairs','collect']); p.add_argument('--directory'); p.add_argument('--prior',default='judges-20261021.jsonl'); p.add_argument('--job',required=True)
    add_budget_args(p)
    args=p.parse_args()
    activate_budget(args,'judge')
    try: main(args)
    except Exception as exc:
        print(json.dumps(safe_error(exc))); raise SystemExit(1)
