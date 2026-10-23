"""Complete exactly seven preserved pairs after explicit incremental-cap waiver."""
import argparse,hashlib,json,sys,sqlite3
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'backend'))
from scripts.eval import batch_clarification_resume as base
from scripts.eval import clarification_grade_contract as contract
from scripts.eval.clarification_execution import FOLDER,digest
from scripts.eval.resume_clarification_judging import prepare as original_prepare,validate_resume
from scripts.eval.run_clarification_comparison import install_budget
from scripts.eval.cache_artifacts import save_json
SOURCE=FOLDER/'flat-live'
legacy_build=base.build


def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def prior_ledger(folder=None):
    tickets={read(p)['budget']['ticket'] for p in Path(folder).glob('batch-*.json')} if folder else set()
    with sqlite3.connect('file:D:/AX/diet_agent/tmp/eval-budget.sqlite?mode=ro',uri=True) as db:
        return [r for r in db.execute('SELECT id,stage,amount,settled FROM costs ORDER BY id') if r[0] not in tickets]


def prepare(folder):
    folder=Path(folder);source=read(SOURCE/'judges.json')
    if len(source['rows'])!=93 or any(r['status']!='completed' for r in source['rows']):raise ValueError('Expected93 preserved completed pairs')
    original_prepare(FOLDER/'run-final',folder);save_json(folder/'judges.json',source)
    plan={'source_hashes':{n:sha(SOURCE/n) for n in ['paired.json','judges.json','frozen.json']},'runner_sha256':sha(__file__),'contract_sha256':sha(contract.__file__),'ledger_rows_sha256':digest(prior_ledger()),'reused_answers':200,'reused_complete_pairs':93,'remaining_pairs':7,'incremental_cap_waived_by_user':True,'scope':'Only finish seven existing pending pairs; no regenerated answers or repeated completed grades','historical_budget_files_preserved':True}
    save_json(folder/'completion-plan.json',plan);validate(folder);return plan


def validate(folder):
    folder=Path(folder);plan=read(folder/'completion-plan.json');validate_resume(folder)
    if plan['runner_sha256']!=sha(__file__) or plan['contract_sha256']!=sha(contract.__file__) or any(sha(SOURCE/n)!=h for n,h in plan['source_hashes'].items()):raise ValueError('Frozen source or contract changed')
    by={r['case_id']:r for r in read(folder/'judges.json')['rows']}
    if any(by.get(r['case_id'])!=r for r in read(SOURCE/'judges.json')['rows']):raise ValueError('Existing93 grades changed')
    if digest(prior_ledger(folder))!=plan['ledger_rows_sha256']:raise ValueError('Existing ledger rows changed')
    return plan


def build(folder):
    validate(folder);es,rs=legacy_build(folder);requests=[]
    for e,r in zip(es,rs):
        req=contract.request(json.loads(r['contents'][0]['parts'][0]['text']),e['key']);requests.append(req)
        e.update(format_contract=contract.CONTRACT_VERSION,system_instruction_sha256=digest(base.RUBRIC+contract.FORMAT_INSTRUCTION),request_sha256=digest(req))
    return es,requests


def submit(client,folder,budget):
    folder=Path(folder)
    if any(not read(p).get('collected') for p in folder.glob('batch-*.json')):raise ValueError('Pending batch must settle first')
    validate(folder)
    es,rs=build(folder)
    if len(es)>7:raise ValueError('Only seven authorized pairs')
    if not es:print('No unsubmitted pairs');return
    from scripts.eval.batch_agentic_judges import requests_digest
    contract.validate_wire(json.loads(requests_digest(client,base.MODEL,rs)),rs)
    with patch.object(base,'build',build):base.submit(client,folder,budget,chunks=1)


def main(args):
    folder=Path(args.folder)
    if args.action=='prepare':print(json.dumps(prepare(folder)));return
    validate(folder)
    if not args.allow_paid:raise ValueError('Explicit paid authorization required')
    from dotenv import load_dotenv
    load_dotenv(ROOT/'backend/.env',override=True)
    # Return to original campaign limits; never reset prior costs or edit old caps.
    budget=install_budget(FOLDER/'resume-budget.json','judge')
    from app.core.config import get_settings
    from google import genai
    client=genai.Client(api_key=get_settings().gemini_api_key,http_options={'retry_options':{'attempts':1},'timeout':60000})
    try:
        if args.action=='submit':submit(client,folder,budget)
        else:
            with patch.object(base,'parse_grade',contract.parse):base.collect(client,folder,budget)
    finally:save_json(folder/'budget-after.json',budget.summary());client.close()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','submit','collect']);p.add_argument('--folder',required=True);p.add_argument('--allow-paid',action='store_true');main(p.parse_args())
