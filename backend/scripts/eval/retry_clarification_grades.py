"""Explicit 2-pair smoke then remaining43; same ledger, additional USD0.25 cap."""
import argparse,hashlib,json,sys
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'backend'))
from scripts.eval.clarification_execution import FOLDER,digest,pair_payload,read_cases
from scripts.eval.resume_clarification_judging import prepare as prepare_original,validate_resume
from scripts.eval.batch_clarification_resume import build,collect,Pair,MODEL,batch_cost,submit_once,eval_budget,quota_details
from scripts.eval.run_clarification_comparison import install_budget
from scripts.eval.cache_artifacts import save_json
BASELINE=9.533327
SMOKE_IDS=['cb2-eval-known_choices-11','cb2-eval-known_label-06']

def increment_ceiling(plan):
    if plan.get('baseline_usd')!=BASELINE or type(plan.get('additional_cap_usd')) not in (float,int) or not 0<plan['additional_cap_usd']<=.25:raise ValueError('Authorized additional ceiling changed')
    return round(BASELINE+plan['additional_cap_usd'],6)

def prepare(folder):
    folder=Path(folder);source=FOLDER/'offline-recovery'
    old=json.loads((source/'judges.json').read_text(encoding='utf-8'));summary=json.loads((source/'summary.json').read_text(encoding='utf-8'))
    hashes={n:hashlib.sha256((source/n).read_bytes()).hexdigest() for n in ['paired.json','judges.json','frozen.json']}
    if summary['source_hashes']!=hashes:raise ValueError('Source evidence changed')
    complete=[r for r in old['rows'] if r['status']=='completed'];failed=[r for r in old['rows'] if r['status']!='completed']
    if len(complete)!=55 or len(failed)!=45 or not set(SMOKE_IDS)<={r['case_id'] for r in failed}:raise ValueError('Expected55 preserved and45 pending pairs')
    prepare_original(FOLDER/'run-final',folder)
    if (source/'paired.json').read_bytes()!=(folder/'paired.json').read_bytes():raise ValueError('Original answers differ')
    save_json(folder/'judges.json',{**old,'rows':complete});save_json(folder/'previous-failed-grades.json',failed)
    plan={'baseline_usd':BASELINE,'additional_cap_usd':.25,'original_campaign_cap_usd':10.324354,'original_overall_cap_usd':17.139139,'reused_answers':200,'reused_complete_pairs':55,'pending_pairs':45,'smoke_ids':SMOKE_IDS,'source_hashes':hashes,'source_complete_sha256':digest(complete),'module_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'no_generation':True}
    save_json(folder/'retry-plan.json',plan);return plan

def validate(folder):
    folder=Path(folder);plan=json.loads((folder/'retry-plan.json').read_text(encoding='utf-8'));increment_ceiling(plan);validate_resume(folder)
    if plan.get('smoke_ids')!=SMOKE_IDS:raise ValueError('Fixed two smoke cases changed')
    if plan['module_sha256']!=hashlib.sha256(Path(__file__).read_bytes()).hexdigest():raise ValueError('Retry implementation changed')
    source=FOLDER/'offline-recovery'
    if any(hashlib.sha256((source/n).read_bytes()).hexdigest()!=h for n,h in plan['source_hashes'].items()):raise ValueError('Source changed')
    prior=json.loads((source/'judges.json').read_text(encoding='utf-8'));current=json.loads((folder/'judges.json').read_text(encoding='utf-8'));by={r['case_id']:r for r in current['rows']}
    if any(by.get(r['case_id'])!=r for r in prior['rows'] if r['status']=='completed'):raise ValueError('Existing55 grades changed')
    return plan

def smoke_passed(folder):
    folder=Path(folder);plan=json.loads((folder/'retry-plan.json').read_text(encoding='utf-8'));j=json.loads((folder/'judges.json').read_text(encoding='utf-8'));r=json.loads((folder/'paired.json').read_text(encoding='utf-8'));by={x['case_id']:x for x in j['rows']};cases=read_cases()
    if plan.get('smoke_ids')!=SMOKE_IDS:return False
    for cid in SMOKE_IDS:
        g=by.get(cid,{})
        if g.get('status')!='completed' or not g.get('usage'):return False
        try:Pair.model_validate(g.get('grades'))
        except ValueError:return False
        c=next(c for c in cases if c['id']==cid);payload,mapping=pair_payload(c,r['rows'],cases.index(c))
        if g.get('mapping')!=mapping or g.get('answer_binding')!=digest(payload):return False
    return True

def submit(client,folder,budget,phase):
    folder=Path(folder);plan=validate(folder)
    if any((folder/n).exists() for n in ['accounting-stop.json','batch-submit-error.json','retry-stop.json']):raise ValueError('Saved accounting/submission/budget stop; no calls')
    if phase=='rest' and not smoke_passed(folder):raise ValueError('Both smoke pairs must pass format validation before43 calls')
    entries,requests=build(folder)
    chosen=[(e,r) for e,r in zip(entries,requests) if (e['key'] in plan['smoke_ids'])==(phase=='smoke')]
    if not chosen:print('No unsubmitted pairs; collect existing jobs, never duplicate.');return
    limit=2 if phase=='smoke' else 8
    size=min(limit,len(chosen))
    while size and batch_cost(client,MODEL,[r for _,r in chosen[:size]])>budget.available('judge'):size-=1
    if size==0 or (phase=='smoke' and size!=2):
        print(json.dumps({'state':'reservation_does_not_fit','unsubmitted_pairs':len(chosen),'additional_ceiling_usd':increment_ceiling(plan)}));return
    es=[e for e,_ in chosen[:size]];rs=[r for _,r in chosen[:size]]
    path=folder/('batch-'+digest(es)[:16]+'.json')
    try:
        with patch('batch_agentic_judges.BATCH_RESERVATION',eval_budget.BATCH_RESERVATION):job=submit_once(client,path,MODEL,rs,es,budget=budget)
    except Exception as exc:save_json(folder/'batch-submit-error.json',quota_details(exc));raise
    print(json.dumps({'phase':phase,'pairs':len(es),'state':job['state'],'reservation_usd':job['budget']['reserved_usd']}))

def main(args):
    folder=Path(args.folder)
    if args.action=='prepare':print(json.dumps(prepare(folder)));return
    plan=validate(folder)
    if args.action=='rest' and not smoke_passed(folder):raise ValueError('Smoke failed or unfinished;43 pairs forbidden')
    if not args.allow_paid:raise ValueError('Explicit paid authorization required')
    from dotenv import load_dotenv
    load_dotenv(ROOT/'backend/.env',override=True)
    budget=install_budget(FOLDER/'resume-budget.json','judge')
    current=budget.summary()['committed_usd'];ceiling=increment_ceiling(plan)
    if not BASELINE<=current<=ceiling:raise ValueError('Prior usage reset or additional budget exceeded')
    # The same atomic reservation transaction enforces this narrower execution cap.
    eval_budget.TOTAL=min(eval_budget.TOTAL,ceiling)
    from app.core.config import get_settings
    from google import genai
    client=genai.Client(api_key=get_settings().gemini_api_key,http_options={'retry_options':{'attempts':1},'timeout':60000})
    try:
        if args.action=='collect':
            collect(client,folder,budget)
            save_json(folder/'smoke-check.json',{'smoke_ids':plan['smoke_ids'],'format_passed':smoke_passed(folder),'gate':'both pairs strictly parsed with answer binding; quality scores never inferred'})
        else:submit(client,folder,budget,args.action)
    finally:save_json(folder/'budget-after.json',{**budget.summary(),'additional_committed_usd':round(budget.summary()['committed_usd']-BASELINE,6),'original_campaign_cap_usd':10.324354})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','smoke','rest','collect']);p.add_argument('--folder',required=True);p.add_argument('--allow-paid',action='store_true');main(p.parse_args())
