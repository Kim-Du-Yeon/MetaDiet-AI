"""Offline-only diagnostics, development fixtures, wire audit and cost planning."""
import argparse,hashlib,json,math,socket,sqlite3,statistics,sys
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'backend'));sys.path.insert(0,str(Path(__file__).resolve().parent))
from scripts.eval.clarification_grade_contract import FIELDS,KEYS,CONTRACT_VERSION,FORMAT_INSTRUCTION,parse,request,validate_wire
from scripts.eval.batch_clarification_resume import Grade,MODEL
from scripts.eval.batch_agentic_judges import batch_cost,requests_digest
from scripts.eval.clarification_execution import RUBRIC,RUBRIC_SHA,read_cases,pair_payload,digest
from scripts.eval.cache_artifacts import save_json

SOURCE=ROOT/'docs/prompt_control/clarification-balanced/execution-v2/retry-025'
LEDGER='file:D:/AX/diet_agent/tmp/eval-budget.sqlite?mode=ro'


def ledger_snapshot():
    with sqlite3.connect(LEDGER,uri=True) as db:
        rows=list(db.execute('SELECT id,stage,amount,settled FROM costs ORDER BY id'))
        stops=list(db.execute('SELECT reason FROM stop'))
    return {'rows_sha256':digest(rows),'rows':len(rows),'committed_usd':sum(r[2] for r in rows)/1e6,'stages':{s:sum(r[2] for r in rows if r[1]==s)/1e6 for s in {r[1] for r in rows}},'stops':stops}


def audit(out):
    out=Path(out)
    if out.exists():raise ValueError('Do not overwrite evidence')
    # No real credentials, transport, token-count API, quota probe or ledger writes.
    before=ledger_snapshot()
    inputs=[SOURCE/n for n in ['paired.json','judges.json','frozen.json','unresolved.json','budget-after.json']]
    inputs+=sorted((SOURCE/'raw-grades').glob('*.json'))
    source_hashes={str(p.relative_to(SOURCE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    read=lambda p:json.loads(p.read_text(encoding='utf-8'))
    old=read(SOURCE/'judges.json');answers=read(SOURCE/'paired.json');cases=read_cases()
    unresolved=read(SOURCE/'unresolved.json');assert len(unresolved)==31
    by={r['case_id']:r for r in old['rows']};analysis=[];new_requests=[];original_requests=[]
    for item in unresolved:
        raw=read(SOURCE/item['raw_path']);value=json.loads(raw['text'])
        assert raw['finish_reasons']==['FinishReason.STOP']
        assert isinstance(value,dict) and set(value)=={'a','b'} and all(isinstance(value[s],list) for s in ['a','b'])
        try:parse(raw['text'])
        except ValueError:pass
        else:raise AssertionError('Unlabelled scores became valid')
        row=by[item['case_id']]
        c=next(c for c in cases if c['id']==item['case_id'])
        payload,mapping=pair_payload(c,answers['rows'],cases.index(c))
        assert digest(payload)==row['answer_binding'] and mapping==row['mapping']
        proposed=request(payload,item['case_id']);new_requests.append(proposed)
        original=json.loads(json.dumps(proposed));original['config']['system_instruction']=RUBRIC
        original['config']['response_json_schema']={'type':'object','properties':{s:Grade.model_json_schema() for s in ['a','b']},'required':['a','b'],'additionalProperties':False}
        original_requests.append(original)
        analysis.append({'case_id':item['case_id'],'classification':'unlabelled_positional_arrays','finish_reason':'STOP','raw_sha256':item['raw_sha256'],'answer_binding':row['answer_binding'],'array_lengths':{s:len(value[s]) for s in ['a','b']},'prior_batch_cost_usd':row['batch_cost_usd'],'recoverable_without_inference':False})
    fixtures=[]
    for i in range(20):
        v={s+'_'+k:('synthetic rationale '+s+str(i) if k=='reason' else (i+j+(s=='b'))%2==0) for s in ['a','b'] for j,k in enumerate(FIELDS)}
        result=parse(json.dumps(v)).model_dump()
        assert result=={s:{k:v[s+'_'+k] for k in FIELDS} for s in ['a','b']}
        fixtures.append({'id':'format-dev-'+str(i).zfill(2),'scope':'fabricated format fixture, not a model answer or quality grade','response':v})
    from google import genai
    from google.genai._api_client import BaseApiClient
    with patch.object(socket,'create_connection',side_effect=AssertionError('Offline only')),patch.object(BaseApiClient,'request',side_effect=AssertionError('No API calls')),patch.object(BaseApiClient,'async_request',side_effect=AssertionError('No API calls')):
        client=genai.Client(api_key='offline-placeholder-not-real')
        wire=json.loads(requests_digest(client,MODEL,new_requests));validate_wire(wire,new_requests)
        original_wire=json.loads(requests_digest(client,MODEL,original_requests))
        assert all(e['request']['generationConfig']['responseJsonSchema']['properties']['a']['type']=='object' for e in original_wire['batch']['inputConfig']['requests']['requests'])
        bounds=[batch_cost(client,MODEL,[r]) for r in new_requests];client.close()
    observed=sum(r['prior_batch_cost_usd'] for r in analysis)
    # Cost scenarios only: not tokenizer output, actual usage or reserved funds.
    added_input_proxy=len(FORMAT_INSTRUCTION.encode('utf-8'))/4
    added_output_proxy=sum(len(k.encode('utf-8')) for k in KEYS)/4
    scenario=observed+31*(added_input_proxy+added_output_proxy*6)/1e6
    high=31*max(r['prior_batch_cost_usd'] for r in analysis)+31*(added_input_proxy+added_output_proxy*6)/1e6
    after=ledger_snapshot();assert before==after
    assert all(hashlib.sha256((SOURCE/n).read_bytes()).hexdigest()==h for n,h in source_hashes.items())
    assert before['committed_usd']==9.674849 and not before['stops']
    remaining=.108478;caps=read(SOURCE.parent/'resume-budget.json')
    out.mkdir(parents=True)
    save_json(out/'analysis.json',analysis);save_json(out/'development20.json',fixtures)
    save_json(out/'contract.json',{'version':CONTRACT_VERSION,'semantic_rubric_sha256':RUBRIC_SHA,'system_instruction_sha256':digest(RUBRIC+FORMAT_INSTRUCTION),'request_contract_sha256':digest(new_requests),'module_sha256':hashlib.sha256((ROOT/'backend/scripts/eval/clarification_grade_contract.py').read_bytes()).hexdigest(),'format_instruction':FORMAT_INSTRUCTION,'model':MODEL,'max_output_tokens':2048,'thinking':'low','wire_verified_requests':31,'no_activation':True})
    save_json(out/'budget-plan.json',{'remaining_authorized_usd':remaining,'additional_committed_usd':0,'observed_same31_prior_batch_usd':observed,'format_overhead_scenario_usd':scenario,'high_observed_case_scenario_usd':high,'all31_conservative_reservation_usd':sum(bounds),'per_request_bounds_usd':bounds,'first2_reservation_usd':sum(bounds[:2]),'worst_bound_first_chunk_size':int(remaining//max(bounds)),'fits_expected_scenario':scenario<=remaining,'completion_guaranteed':False,'stage_judge_headroom_usd':caps['stage_caps']['judge']-before['stages']['judge'],'campaign_cap_usd':caps['total_limit_usd'],'overall_cap_usd':caps['original_total_ceiling_usd'],'active_narrow_cap_usd':9.783327,'pricing':'Frozen Pro Batch $1 input/$6 output incl thinking per1M; no cached tokens','scenario_method':'prior same31 usage + format instruction UTF8bytes/4 input proxy + added field-name UTF8bytes/4 output proxy. Not measured tokenizer usage. High uses prior maximum pair cost, not a statistical guarantee.','execution_plan':'Not authorized now. If later authorized,2 paid format probes included within31 then sequential <=5 chunks with atomic reservations and actual settlement; no re-generation, retry or cap increase. Stop before next bound exceeds remaining.'})
    save_json(out/'preservation.json',{'before':before,'after':after,'source_hashes':source_hashes,'sources_unchanged':True,'existing69_grades_unchanged':True,'all200_answers_unchanged':True,'raw31_scores_not_inferred':True,'new_paid_calls':0,'ledger_writes':0,'provider_conformance_proven':False,'offline_fixture_checks':20})
    print(json.dumps({'format_development_checks':20,'unresolved':31,'new_paid_calls':0,'observed31':observed,'overhead_scenario':scenario,'high_scenario':high,'reservation_all':sum(bounds),'first2_bound':sum(bounds[:2])}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);audit(p.parse_args().out)
