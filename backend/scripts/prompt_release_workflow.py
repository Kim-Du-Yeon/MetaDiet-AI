"""Offline-first release approval. Only immutable private templates; never promote.

The compact-followup suite is deliberately coverage-limited. New routes require a
code-reviewed evaluation adapter, not an unchecked JSON claim of success.
"""
import argparse,copy,hashlib,json,math,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
from app.core.prompt_release_control import REPOS,_snapshot,canonical,digest,sign_snapshot,validate_snapshot
from scripts.eval.analyze_prompt_control import analyze

RUBRIC_SHA='82509133f08be4a9553b209dfcc111ff6dd641352b86ac06de6b202e1f0ee7ff'
CONDITIONS='same model temperature0 low thinking max1024 compact prompt; AB/BA pair order; concurrency1; no retrieval in this read-only followup route'
FILES=('paired.json','judges.json','frozen.json')
# Exact pre-binding historical run, already source-reviewed and signed. No other
# legacy artifact may omit judge provenance; callers cannot supply this allowlist.
LEGACY_HASHES={
    'paired.json':'116fd62dba5da079a0ee4596f1d4366c73619f63c2b4fc9f905bacd97041471e',
    'judges.json':'2180048a9dfc95404cbf3d1db5d191085e796dd130b63f3b0499321010b23713',
    'frozen.json':'f1785b53de4513e868a91faaa62260fd340bbd2349b5544f8f908282a6aadb86'}


def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def identity(value):
    snapshot=_snapshot(value).wire
    return digest({'prompts':snapshot['manifest']['prompts'],'texts':snapshot['texts']})

def validate_candidate(value,key):
    if set(value)!={'schema_version','baseline','snapshot'} or value['schema_version']!=1:raise ValueError('Invalid candidate schema')
    validate_snapshot(value['baseline'],key)
    snapshot=_snapshot(value['snapshot'])
    if value['snapshot'].get('kind')!='evaluation' or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}',snapshot.release):raise ValueError('Invalid candidate release')
    if set(value['snapshot'])!={'kind','manifest','texts','origin_commit'}:raise ValueError('Unexpected candidate fields')
    return snapshot

def make_candidate(baseline,name,overrides,pull,key):
    validate_snapshot(baseline,key)
    value=copy.deepcopy(baseline)
    value={k:value[k] for k in ['kind','manifest','texts']}
    value.update(kind='evaluation',origin_commit=None)
    value['manifest'].pop('validation',None);value['manifest']['release']=name
    for prompt,commit in overrides.items():
        if prompt not in REPOS or not re.fullmatch(r'[a-f0-9]{64}',commit):raise ValueError('Select known prompt and full immutable64hex commit')
        text,actual=pull(REPOS[prompt],commit)
        if actual!=commit:raise ValueError('Immutable commit mismatch')
        value['texts'][prompt]=text;entry=value['manifest']['prompts'][prompt]
        entry.update(commit=commit,sha256=hashlib.sha256(text.encode()).hexdigest())
    candidate={'schema_version':1,'baseline':baseline,'snapshot':value}
    validate_candidate(candidate,key)
    return candidate

def supported_changes(candidate):
    changed={name for name in REPOS if candidate['snapshot']['texts'][name]!=candidate['baseline']['texts'][name]}
    if changed-{'team.compact_followup'}:raise ValueError('Evaluation coverage missing for changed route; add a reviewed suite before approval')

def verify_evidence(candidate,folder,key):
    policy=Path(folder)/'policy.json'
    if policy.exists() and read(policy).get('id')=='clarification-candidate-safety-v2':
        from scripts.eval.clarification_approval_review import verify
        return verify(candidate,folder,key)
    marker=Path(folder)/'protocol.json'
    if marker.exists() and read(marker).get('suite')=='clarification-closing-offer-v5':
        from scripts.eval.approve_clarification_v5 import verify
        return verify(candidate,folder,key)
    if marker.exists() and read(marker).get('suite')=='clarification-two-template-holdout-v1':
        from scripts.eval.clarification_holdout import verify
        return verify(candidate,folder,key)
    if read(Path(folder)/'paired.json').get('suite')=='clarification-balanced-v2':
        from scripts.eval.clarification_execution import verify
        return verify(candidate,folder,key)
    validate_candidate(candidate,key);supported_changes(candidate)
    folder=Path(folder);report=read(folder/'paired.json');judges=read(folder/'judges.json');cases=read(folder/'frozen.json');stored=read(folder/'summary.json')
    hashes={name:hashlib.sha256((folder/name).read_bytes()).hexdigest() for name in FILES}
    if stored.get('source_hashes')!=hashes:raise ValueError('Saved evidence hash mismatch')
    if report.get('cases_sha256')!=hashlib.sha256((folder/'frozen.json').read_text(encoding='utf-8').encode()).hexdigest():raise ValueError('Frozen cohort mismatch')
    if report.get('scope')!='synthetic_actual_DietTeam_followup_not_users' or report.get('conditions')!=CONDITIONS or report.get('model')!='gemini-3.8-flash':raise ValueError('Unsupported evaluation execution settings')
    if report.get('experiment_id'):
        binding=digest({k:report[k] for k in ['cases_sha256','prompt_snapshots','model','conditions']})
        if judges.get('generation_binding')!=binding:raise ValueError('Judge-to-generation binding mismatch')
    elif hashes!=LEGACY_HASHES:raise ValueError('Unknown unbound legacy evidence; rerun using bound evaluation adapter')
    if judges.get('model')!='gemini-3.1-pro-preview' or judges.get('rubric_sha256')!=RUBRIC_SHA or hashlib.sha256(judges.get('rubric','').encode()).hexdigest()!=RUBRIC_SHA:raise ValueError('Unrecognized evaluator/rubric')
    snapshots=report.get('prompt_snapshots',{})
    if set(snapshots)!={'v1','v2'} or identity(snapshots['v1'])!=identity(candidate['baseline']):raise ValueError('Evaluated baseline mismatch')
    labels=[label for label,value in snapshots.items() if identity(value)==identity(candidate['snapshot'])]
    if not labels:raise ValueError('No matching immutable candidate evaluation; run comparison first')
    label='v1' if 'v1' in labels else 'v2'
    ids=[c['id'] for c in cases]
    if len(ids)!=100 or len(set(ids))!=100:raise ValueError('Require frozen100 unique attempt IDs')
    expected={(case,label) for case in ids for label in ['v1','v2']}
    rows=report['rows'];keys=[(r['case_id'],r['condition']) for r in rows]
    if len(keys)!=200 or set(keys)!=expected:raise ValueError('Missing or duplicate generation attempts')
    for row in rows:
        metadata=_snapshot(snapshots[row['condition']]).metadata()
        actual=row.get('prompt_metadata',{})
        if any(actual.get(k)!=metadata[k] for k in ['prompt_commit_ids','prompt_hashes','prompt_bundle_sha256']):raise ValueError('Per-attempt prompt identity mismatch')
        if any(isinstance(row.get(k),bool) or not isinstance(row.get(k),(int,float)) or not math.isfinite(row[k]) or row[k]<0 for k in ['ms','cost_usd']):raise ValueError('Invalid measured duration/cost')
        if not row.get('usage'):raise ValueError('Generation usage missing')
        if row.get('model')!=report['model'] or type(row.get('fresh')) is not bool or type(row.get('no_write')) is not bool:raise ValueError('Invalid generation metadata')
    judge_ids=[r['case_id'] for r in judges['rows']]
    if len(judge_ids)!=100 or set(judge_ids)!=set(ids):raise ValueError('Missing or duplicate judging attempts')
    case_by_id={case['id']:case for case in cases}
    answer_by_key={(row['case_id'],row['condition']):row for row in rows}
    for row in judges['rows']:
        if report.get('experiment_id') and row['status']=='completed':
            case=case_by_id[row['case_id']];mapping=row['mapping']
            payload={'question':case['question'],'current_calories':case['calories'],'current_calorie_target':case['target'],**{position:answer_by_key[(row['case_id'],label)].get('answer','') for position,label in mapping.items()}}
            if row.get('answer_binding')!=digest(payload):raise ValueError('Judge answer binding mismatch')
        if set(row['mapping'])!={'a','b'} or set(row['mapping'].values())!={'v1','v2'}:raise ValueError('Invalid blinded pair mapping')
        if row['status']=='completed':
            if set(row.get('grades',{}))!={'a','b'}:raise ValueError('Missing grade')
            for grade in row['grades'].values():
                if any(type(grade.get(k)) is not bool for k in ['correct','faithful','unsupported_sufficiency']):raise ValueError('Invalid quality grade')
    result=analyze(report,judges)
    # Recompute gates; never trust candidate_passed or selection in a hand-edited summary.
    selected=result['summary'][label]
    baseline_ok=all(v['attempts']==100 and v['fresh_percent']==100 and v['no_write_percent']==100 and v['judge_complete'] and v['usage_complete'] for v in result['summary'].values())
    if not baseline_ok or not result['judge_usage_complete'] or selected['failure_percent']>2 or selected['quality_percent']<98:raise ValueError('Incomplete or unsafe evaluation')
    if label=='v2' and not result['candidate_passed']:raise ValueError('Candidate failed preregistered improvement gate')
    return {'schema_version':1,'suite':'compact_followup_v1','candidate_sha256':digest(candidate),'baseline_identity':identity(candidate['baseline']),'candidate_identity':identity(candidate['snapshot']),'condition':label,'source_hashes':hashes,'analysis':result,'approved':True,'scope':'synthetic100pairs; not live-user A/B; unchanged unexercised templates inherit trusted baseline'}

def verify_receipt(candidate,folder,receipt,key):
    expected=verify_evidence(candidate,folder,key)
    if receipt!=expected:raise ValueError('Receipt/candidate/evidence changed; evaluate again')
    return expected

def publish(candidate,folder,receipt,key,private_key,client):
    verify_receipt(candidate,folder,receipt,key)
    from app.core.langsmith_prompts import LangSmithReleaseReader,RELEASE_REPO
    reader=LangSmithReleaseReader(client)
    for name,entry in candidate['snapshot']['manifest']['prompts'].items():
        text,commit=reader.pull(entry['repo'],entry['commit'])
        if text!=candidate['snapshot']['texts'][name] or commit!=entry['commit']:raise ValueError('Remote candidate readback mismatch')
    value=sign_snapshot(_snapshot(candidate['snapshot']),private_key,report_sha256=digest(receipt))
    validate_snapshot(value,key)
    body={k:value[k] for k in ['kind','manifest','signature']}
    record=client.get_prompt(RELEASE_REPO)
    if record is None or record.is_public is not False:raise ValueError('Private release repository required')
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.messages import SystemMessage
    from langsmith.utils import LangSmithConflictError
    try:client.push_prompt(RELEASE_REPO,object=ChatPromptTemplate.from_messages([SystemMessage(content=json.dumps(body,ensure_ascii=False))]),is_public=False,commit_description='Evaluated release '+value['manifest']['release']+'; no automatic promotion')
    except LangSmithConflictError:pass
    text,commit=reader.pull(RELEASE_REPO,'latest',allow_latest=True)
    if read_json_text(text)!=body:raise ValueError('Published release readback mismatch')
    value['origin_commit']=commit
    return value

def read_json_text(text):return json.loads(text)

def write_new(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    # Never overwrite historical evidence, candidates, receipts or approved snapshots.
    with path.open('x',encoding='utf-8') as stream:stream.write(json.dumps(value,ensure_ascii=False,indent=2)+'\n')

def main():
    parser=argparse.ArgumentParser(description='Offline-first immutable release approval; never promotes tags')
    commands=parser.add_subparsers(dest='command',required=True)
    prepare=commands.add_parser('prepare');prepare.add_argument('--base',required=True);prepare.add_argument('--name',required=True);prepare.add_argument('--select',action='append',default=[]);prepare.add_argument('--output',required=True)
    evaluate=commands.add_parser('evaluate');evaluate.add_argument('--candidate',required=True);evaluate.add_argument('--results',required=True);evaluate.add_argument('--output',required=True)
    approve=commands.add_parser('publish');approve.add_argument('--candidate',required=True);approve.add_argument('--results',required=True);approve.add_argument('--receipt',required=True);approve.add_argument('--output',required=True)
    args=parser.parse_args()
    # Refuse an existing destination before any remote publication.
    if Path(args.output).exists():raise ValueError('Destination exists; use a new release artifact path')
    from dotenv import load_dotenv
    load_dotenv(ROOT/'backend/.env',override=True)
    from app.core.prompt_service import approval_key
    from app.core.langsmith_prompts import make_client,LangSmithReleaseReader
    key=approval_key()
    if args.command=='prepare':
        selections={}
        for selection in args.select:
            name,commit=selection.split('=',1)
            if name in selections:raise ValueError('Duplicate prompt selection')
            selections[name]=commit
        client=make_client(timeout_ms=10000) if selections else None
        try:value=make_candidate(read(args.base),args.name,selections,LangSmithReleaseReader(client).pull if client else None,key)
        finally:
            if client:client.close()
    elif args.command=='evaluate':value=verify_evidence(read(args.candidate),args.results,key)
    else:
        candidate=read(args.candidate);receipt=read(args.receipt)
        verify_receipt(candidate,args.results,receipt,key) # Before key load or remote writes.
        from cryptography.hazmat.primitives import serialization
        private=serialization.load_pem_private_key((ROOT/'backend/.env.prompt-signer').read_bytes(),password=None)
        client=make_client(timeout_ms=10000)
        try:value=publish(candidate,args.results,receipt,key,private,client)
        finally:client.close()
    write_new(args.output,value)
    print(json.dumps({'operation':args.command,'artifact':str(Path(args.output).name),'promoted':False,'release_commit':value.get('origin_commit')}))
