"""Explicit, provenance-preserving resumption of only unfinished paired grades."""
import argparse,asyncio,hashlib,json,re,sys,time
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'backend'))
from scripts.eval.clarification_execution import FOLDER,judge_binding,pair_payload,read_cases,runtime_code,CONDITIONS,RUBRIC,RUBRIC_SHA,digest,price_usage
from scripts.eval.cache_artifacts import save_json
SOURCE_HASHES={'paired.json':'a6195964d8a644c181c111eb78c3417dc47c2f013252de86525ebf9e88757620','judges.json':'a1e1806c41229f1009ebf903b48df26db880ac6b71b9174915ba567e9984bfb6','frozen.json':'28110f43ff8cbe63f1461b6f3bf00c815fa6f96ff0ae75d24e65f4fe6f5396fb'}

def quota_details(exc):
    texts=[];current=exc
    for _ in range(5):
        if current is None:break
        texts.append(str(current));current=current.__cause__ or current.__context__
    text=' '.join(texts)
    metrics=sorted(set(re.findall(r'generativelanguage\.googleapis\.com/[A-Za-z0-9_/]+',text)))
    ids=sorted(set(re.findall(r'(?:quotaId|quota_id)[\s\"\x27:]+([A-Za-z][A-Za-z0-9_-]+)',text)))
    dimensions=set()
    for value in metrics+ids:
        value=value.lower().replace('_','')
        if 'perday' in value and 'request' in value:dimensions.add('RPD')
        elif 'perminute' in value and 'token' in value:dimensions.add('TPM')
        elif 'perminute' in value and 'request' in value:dimensions.add('RPM')
    return {'exception_type':type(exc).__name__,'status_codes':sorted(set(re.findall(r'\b(?:402|429|403|503)\b',text))),'quota_metrics':metrics,'quota_ids':ids,'dimension':','.join(sorted(dimensions)) or 'unknown','raw_error_stored':False}

def prepare(source,folder):
    source=Path(source);folder=Path(folder)
    if folder.exists():raise ValueError('Resume destination exists; never overwrite')
    for name,sha in SOURCE_HASHES.items():
        if hashlib.sha256((source/name).read_bytes()).hexdigest()!=sha:raise ValueError('Source evidence changed')
    r=json.loads((source/'paired.json').read_text(encoding='utf-8'));j=json.loads((source/'judges.json').read_text(encoding='utf-8'))
    if r['execution_code']!=runtime_code() or j['generation_binding']!=judge_binding(r) or j['rubric_sha256']!=RUBRIC_SHA or j['rubric']!=RUBRIC:raise ValueError('Source execution/rubric changed')
    completed=[x for x in j['rows'] if x['status']=='completed']
    if len(completed)!=4:raise ValueError('Expected four complete source pairs')
    folder.mkdir(parents=True)
    for name in ['paired.json','frozen.json']:(folder/name).write_bytes((source/name).read_bytes())
    save_json(folder/'prior-attempts.json',j)
    save_json(folder/'judges.json',{**j,'rows':completed})
    plan={'source_hashes':SOURCE_HASHES,'remaining_pairs':96,'reused_answers':200,'reused_complete_pairs':4,'old_failed_pairs_preserved':1,'source_stop_preserved':True,'generation_repeated':False,'minimum_spacing_seconds':20,'module_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    save_json(folder/'resumption.json',plan);validate_resume(folder);return plan

def validate_resume(folder):
    folder=Path(folder);plan=json.loads((folder/'resumption.json').read_text(encoding='utf-8'))
    if plan['source_hashes']!=SOURCE_HASHES or plan['module_sha256']!=hashlib.sha256(Path(__file__).read_bytes()).hexdigest():raise ValueError('Resume implementation/provenance changed')
    for name in ['paired.json','frozen.json']:
        if hashlib.sha256((folder/name).read_bytes()).hexdigest()!=SOURCE_HASHES[name]:raise ValueError('Generation evidence changed')
    old=json.loads((folder/'prior-attempts.json').read_text(encoding='utf-8'))
    if hashlib.sha256((folder/'prior-attempts.json').read_bytes()).hexdigest()!=SOURCE_HASHES['judges.json']:raise ValueError('Prior attempts changed')
    j=json.loads((folder/'judges.json').read_text(encoding='utf-8'));r=json.loads((folder/'paired.json').read_text(encoding='utf-8'))
    if r['execution_code']!=runtime_code() or j['generation_binding']!=judge_binding(r) or j['rubric']!=RUBRIC or j['rubric_sha256']!=RUBRIC_SHA:raise ValueError('Judge settings changed')
    if len({x['case_id'] for x in j['rows']})!=len(j['rows']):raise ValueError('Duplicate grade')
    by={x['case_id']:x for x in j['rows']}
    for x in old['rows']:
        if x['status']=='completed' and by.get(x['case_id'])!=x:raise ValueError('Completed source grade changed')
    for i,c in enumerate(read_cases()):
        if c['id'] not in by:continue
        row=by[c['id']];payload,mapping=pair_payload(c,r['rows'],i)
        if row['mapping']!=mapping or row['answer_binding']!=digest(payload):raise ValueError('Answer binding changed')
        if row['status']=='completed':price_usage('gemini-3.1-pro-preview',row['usage'])
    return plan

class PacedModel:
    def __init__(self,model,clock,folder):self.model=model;self.clock=clock;self.folder=folder
    def with_structured_output(self,schema):return PacedModel(self.model.with_structured_output(schema),self.clock,self.folder)
    async def ainvoke(self,*args,**kwargs):
        delay=max(0,20-(time.monotonic()-self.clock[0]))
        if delay:await asyncio.sleep(delay)
        self.clock[0]=time.monotonic()
        try:return await self.model.ainvoke(*args,**kwargs)
        except Exception as exc:
            p=self.folder/'quota-diagnostics.json';events=json.loads(p.read_text(encoding='utf-8')) if p.exists() else []
            events.append({'timestamp':time.time(),**quota_details(exc)});save_json(p,events);raise

async def main(args):
    from dotenv import load_dotenv
    load_dotenv(ROOT/'backend/.env',override=True)
    folder=Path(args.folder)
    if args.action=='prepare':print(json.dumps(prepare(FOLDER/'run-final',folder)));return
    validate_resume(folder)
    if args.action=='summary':
        from scripts.eval.run_clarification_comparison import summarize_folder
        print(json.dumps(summarize_folder(folder)));return
    if not args.allow_paid:raise ValueError('Explicit paid authorization required')
    from scripts.eval.run_clarification_comparison import judge,install_budget,settings,initialize,versions
    from scripts.prompt_release_workflow import read,validate_candidate,supported_changes
    from app.core.prompt_service import approval_key
    candidate=read(ROOT/'docs/prompt_control/followup-question-candidate/candidate.json');validate_candidate(candidate,approval_key());supported_changes(candidate)
    if versions()!=CONDITIONS['packages']:raise ValueError('SDK environment changed')
    initialize(candidate,folder) # Fail closed on a saved stop, unknown accounting or another candidate.
    from app.core.llm import get_chat_model
    clock=[0.]
    def factory(*a,**kw):return PacedModel(get_chat_model(*a,**kw),clock,folder)
    budget=install_budget(args.budget,'judge');save_json(folder/'budget-before.json',budget.summary())
    try:
        with patch('app.core.llm.get_chat_model',factory):await judge(folder)
    finally:
        save_json(folder/'budget-after.json',budget.summary())
        from scripts.eval.run_clarification_comparison import summarize_folder
        summarize_folder(folder)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','judge','summary']);p.add_argument('--folder',required=True);p.add_argument('--budget',default=str(FOLDER/'resume-budget.json'));p.add_argument('--allow-paid',action='store_true');asyncio.run(main(p.parse_args()))
