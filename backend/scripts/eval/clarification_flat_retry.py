"""Authorized31-pair flat-contract retry;2 strict smoke checks, unchanged ledger/caps."""
import argparse,hashlib,json,sys
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'backend'))
from scripts.eval import batch_clarification_resume as base
from scripts.eval import clarification_grade_contract as contract
from scripts.eval.clarification_execution import FOLDER,digest,pair_payload,read_cases
from scripts.eval.resume_clarification_judging import prepare as original_prepare,validate_resume
from scripts.eval.run_clarification_comparison import install_budget
from scripts.eval.cache_artifacts import save_json
SOURCE=FOLDER/'retry-025'
BASELINE=9.674849
ALLOWANCE=.108478
CEILING=9.783327
SMOKE_IDS=['cb2-eval-generic_menu-09','cb2-eval-generic_menu-11']


def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare(folder):
    folder=Path(folder);old=read(SOURCE/'judges.json')
    completed=[r for r in old['rows'] if r['status']=='completed']
    unresolved=[r for r in old['rows'] if r['status']!='completed']
    if len(completed)!=69 or len(unresolved)!=31 or not set(SMOKE_IDS)<={r['case_id'] for r in unresolved}:raise ValueError('Expected immutable69/31 source')
    verified=read(FOLDER/'format-contract-offline/verified/contract.json')
    if verified['module_sha256']!=sha(Path(contract.__file__)):raise ValueError('Offline verified contract changed')
    original_prepare(FOLDER/'run-final',folder)
    save_json(folder/'judges.json',{**old,'rows':completed})
    save_json(folder/'previous-failed-grades.json',unresolved)
    plan={'baseline_usd':BASELINE,'additional_cap_usd':ALLOWANCE,'ceiling_usd':CEILING,'smoke_ids':SMOKE_IDS,'source_hashes':{n:sha(SOURCE/n) for n in ['paired.json','judges.json','frozen.json']},'runner_sha256':sha(__file__),'contract_sha256':sha(contract.__file__),'contract_version':contract.CONTRACT_VERSION,'system_instruction_sha256':digest(base.RUBRIC+contract.FORMAT_INSTRUCTION),'remaining_pairs':31,'reused_complete_pairs':69,'reused_answers':200,'paid_generation':False}
    save_json(folder/'flat-plan.json',plan);validate(folder);return plan


def validate(folder):
    folder=Path(folder);plan=read(folder/'flat-plan.json');validate_resume(folder)
    if (plan['baseline_usd']!=BASELINE or plan['additional_cap_usd']!=ALLOWANCE or plan['ceiling_usd']!=CEILING or plan['smoke_ids']!=SMOKE_IDS or plan['runner_sha256']!=sha(__file__) or plan['contract_sha256']!=sha(contract.__file__)):raise ValueError('Fixed contract, smoke or ceiling changed')
    if any(sha(SOURCE/n)!=h for n,h in plan['source_hashes'].items()):raise ValueError('Original evidence changed')
    old=read(SOURCE/'judges.json');by={r['case_id']:r for r in read(folder/'judges.json')['rows']}
    if any(by.get(r['case_id'])!=r for r in old['rows'] if r['status']=='completed'):raise ValueError('Existing69 grades changed')
    return plan


def build(folder):
    validate(folder);es,old_requests=base.build(folder);out=[]
    for e,r in zip(es,old_requests):
        payload=json.loads(r['contents'][0]['parts'][0]['text']);req=contract.request(payload,e['key']);out.append(req)
        e.update(format_contract=contract.CONTRACT_VERSION,system_instruction_sha256=digest(base.RUBRIC+contract.FORMAT_INSTRUCTION),request_sha256=digest(req))
    return es,out


def smoke_passed(folder):
    folder=Path(folder);plan=validate(folder);by={r['case_id']:r for r in read(folder/'judges.json')['rows']}
    cases=read_cases();answers=read(folder/'paired.json')['rows']
    for cid in SMOKE_IDS:
        r=by.get(cid,{})
        if r.get('status')!='completed' or not r.get('usage') or r.get('format_contract')!=contract.CONTRACT_VERSION or r.get('system_instruction_sha256')!=plan['system_instruction_sha256']:return False
        try:base.Pair.model_validate(r.get('grades'))
        except ValueError:return False
        c=next(c for c in cases if c['id']==cid);payload,mapping=pair_payload(c,answers,cases.index(c))
        if r.get('mapping')!=mapping or r.get('answer_binding')!=digest(payload) or r.get('request_sha256')!=digest(contract.request(payload,cid)):return False
    return True


def submit(client,folder,budget,phase):
    folder=Path(folder);validate(folder)
    if any(not read(p).get('collected') for p in folder.glob('batch-*.json')):raise ValueError('Pending batch must be collected and settled first')
    if any((folder/n).exists() for n in ['accounting-stop.json','batch-submit-error.json','budget-stop.json']):raise ValueError('Saved stop; no additional calls')
    if phase=='rest' and not smoke_passed(folder):raise ValueError('Smoke incomplete or failed')
    es,rs=build(folder);chosen=[(e,r) for e,r in zip(es,rs) if (e['key'] in SMOKE_IDS)==(phase=='smoke')]
    if not chosen:print('No unsubmitted pairs; never duplicate');return
    size=min(2 if phase=='smoke' else 5,len(chosen))
    while size and base.batch_cost(client,base.MODEL,[r for _,r in chosen[:size]])>budget.available('judge'):size-=1
    if size==0 or (phase=='smoke' and size!=2):
        stop={'reason':'next maximum reservation does not fit remaining allowance','unsubmitted':len(chosen),'ceiling_usd':CEILING};save_json(folder/'budget-stop.json',stop);print(json.dumps(stop));return
    entries=[e for e,_ in chosen[:size]];requests=[r for _,r in chosen[:size]]
    from scripts.eval.batch_agentic_judges import requests_digest
    contract.validate_wire(json.loads(requests_digest(client,base.MODEL,requests)),requests)
    path=folder/('batch-'+digest(entries)[:16]+'.json')
    try:
        with patch('batch_agentic_judges.BATCH_RESERVATION',base.eval_budget.BATCH_RESERVATION):job=base.submit_once(client,path,base.MODEL,requests,entries,budget=budget)
    except Exception as exc:save_json(folder/'batch-submit-error.json',base.quota_details(exc));raise
    print(json.dumps({'phase':phase,'pairs':size,'state':job['state'],'reserved_usd':job['budget']['reserved_usd']}))


def check_old_ledger(folder,budget):
    jobs=[read(p) for p in Path(folder).glob('batch-*.json')];tickets={j['budget']['ticket'] for j in jobs if j.get('budget')}
    with budget.connect() as db:rows=[r for r in db.execute('SELECT id,stage,amount,settled FROM costs ORDER BY id') if r[0] not in tickets]
    expected=read(FOLDER/'format-contract-offline/verified/preservation.json')['before']
    if digest(rows)!=expected['rows_sha256']:raise ValueError('Historical ledger rows changed')


def main(args):
    folder=Path(args.folder)
    if args.action=='prepare':print(json.dumps(prepare(folder)));return
    validate(folder)
    if args.action=='rest' and not smoke_passed(folder):raise ValueError('Smoke incomplete or failed; no transport')
    if not args.allow_paid:raise ValueError('Explicit paid authorization required')
    from dotenv import load_dotenv
    load_dotenv(ROOT/'backend/.env',override=True)
    budget=install_budget(FOLDER/'resume-budget.json','judge');check_old_ledger(folder,budget)
    current=budget.summary()['committed_usd']
    if not BASELINE<=current<=CEILING:raise ValueError('Prior costs reset or narrow cap exceeded')
    base.eval_budget.TOTAL=min(base.eval_budget.TOTAL,CEILING)
    from app.core.config import get_settings
    from google import genai
    client=genai.Client(api_key=get_settings().gemini_api_key,http_options={'retry_options':{'attempts':1},'timeout':60000})
    try:
        if args.action=='collect':
            with patch.object(base,'parse_grade',contract.parse):base.collect(client,folder,budget)
            save_json(folder/'smoke-check.json',{'smoke_ids':SMOKE_IDS,'format_passed':smoke_passed(folder)})
        else:submit(client,folder,budget,args.action)
    finally:
        save_json(folder/'budget-after.json',{**budget.summary(),'additional_committed_usd':round(budget.summary()['committed_usd']-BASELINE,6),'additional_cap_usd':ALLOWANCE,'original_campaign_cap_usd':10.324354})
        client.close()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','smoke','collect','rest']);p.add_argument('--folder',required=True);p.add_argument('--allow-paid',action='store_true');main(p.parse_args())
