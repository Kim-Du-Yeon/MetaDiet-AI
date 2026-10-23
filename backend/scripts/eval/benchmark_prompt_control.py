"""Frozen real DietTeam read-only follow-up comparison. Never writes domain data."""
import asyncio,hashlib,json,sys,time
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'backend'))
from dotenv import load_dotenv
load_dotenv(ROOT/'backend/.env',override=True)
from scripts.eval import benchmark_model_routing as base,eval_budget
from app.core.config import get_settings
from app.core.llm import get_chat_model
from app.core.prompt_release_control import _snapshot,using_snapshot

async def main(folder=None,candidate_path=None):
    folder=Path(folder) if folder else ROOT/'docs/prompt_control/comparison';folder.mkdir(parents=True,exist_ok=True)
    protocol=json.loads((ROOT/'docs/prompt_control/budget-protocol.json').read_text())
    eval_budget.TOTAL=protocol['total_limit_usd'];eval_budget.LIMITS=protocol['stage_caps']
    budget=eval_budget.Budget(protocol['ledger']);eval_budget.install_transport_guard(budget,'comparison')
    if candidate_path:
        from scripts.prompt_release_workflow import read,validate_candidate,supported_changes
        from app.core.prompt_service import approval_key
        candidate=read(candidate_path);validate_candidate(candidate,approval_key());supported_changes(candidate)
        drafts={'v1':candidate['baseline'],'v2':candidate['snapshot']}
    else:
        drafts=json.loads((ROOT/'docs/prompt_control/release-drafts/release-drafts.json').read_text(encoding='utf-8-sig'))
    experiment_id='prompt-release-'+candidate['snapshot']['manifest']['release'] if candidate_path else 'prompt-control-20261021'
    snapshots={k:_snapshot({**v,"experiment":{"prompt_experiment_id":experiment_id,"prompt_experiment_group":k}}) for k,v in drafts.items()}
    questions=['그럼 한식뷔페 가서 일반식 먹어도 괜찮아?','그럼 샌드위치 먹어도 괜찮아?','밥이랑 계란 먹어도 괜찮아?','닭가슴살이랑 샐러드 먹어도 괜찮아?']
    changes=[(600,2000,'confirmed'),(850,2000,'edited'),(0,2000,'deleted'),(600,1800,'goal_changed'),(0,1900,'new_day')]
    cases=[]
    for rep in range(5):
        for calories,target,change in changes:
            for question in questions:
                cases.append({'id':f'pc-{len(cases):03}','task':'agent','question':question+' 첫 문장에 "오늘 섭취: N kcal, 하루 기준: N kcal" 형식으로 적어줘.','calories':calories+rep*10 if calories else 0,'target':target+rep*20,'change':change})
    frozen=json.dumps(cases,ensure_ascii=False,indent=2)+'\n';path=folder/'frozen.json'
    if path.exists() and path.read_text(encoding='utf-8')!=frozen:raise ValueError('Frozen cases changed')
    if not path.exists():path.write_text(frozen,encoding='utf-8')
    settings=get_settings().model_copy(update={'compact_followup_prompt':True,'brief_followup_answer':False,'coaching_delivery':'invoke','followup_model':'default','gemini_model':'gemini-3.8-flash','model_max_retries':0,'model_routing_enabled':False})
    report_path=folder/'paired.json'
    report=json.loads(report_path.read_text(encoding='utf-8')) if report_path.exists() else {'scope':'synthetic_actual_DietTeam_followup_not_users','cases_sha256':hashlib.sha256(frozen.encode()).hexdigest(),'model':'gemini-3.8-flash','prompt_snapshots':{k:v.wire for k,v in snapshots.items()},'conditions':'same model temperature0 low thinking max1024 compact prompt; AB/BA pair order; concurrency1; no retrieval in this read-only followup route','hypothesis':'v2 avoids unsupported macro sufficiency claims when current macro target is absent; latest calorie values preserved','quality_gate':'noninferiority within2pp; targeted errors reduced; freshness and no-write100%; p95/cost <=1.25x; complete judge and usage','rows':[]}
    from scripts.prompt_release_workflow import identity,CONDITIONS
    if report['cases_sha256']!=hashlib.sha256(frozen.encode()).hexdigest() or report['conditions']!=CONDITIONS or any(identity(report['prompt_snapshots'][label])!=identity(snapshot.wire) for label,snapshot in snapshots.items()):raise ValueError('Existing comparison belongs to another candidate/cohort/settings')
    if candidate_path:report['experiment_id']=experiment_id
    done={(r['case_id'],r['condition']) for r in report['rows']}
    def factory(**kwargs):return get_chat_model(**{**kwargs,'max_tokens':1024,'model_name':'gemini-3.8-flash'})
    for index,case in enumerate(cases):
        for label in (['v1','v2'] if index%2==0 else ['v2','v1']):
            if (case['id'],label) in done:continue
            with using_snapshot(snapshots[label]),patch.object(base,'get_chat_model',factory),patch('app.core.llm.get_settings',lambda:settings),patch('app.agents.team.get_settings',lambda:settings):
                row=await base.attempt(case,False,settings)
            row['condition']=label;row['prompt_metadata']=snapshots[label].metadata()
            report['rows'].append(row)
            from scripts.eval.cache_artifacts import save_json
            save_json(report_path,report)
            print(case['id'],label,row['status'],round(row['ms']),flush=True)
            if row.get('error',{}).get('reason') in {'credits_depleted','quota_exhausted'}:raise RuntimeError('Provider quota/credit stop; resume preserved')
            await asyncio.sleep(.25)
    print('completed200',flush=True)
if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--allow-paid',action='store_true')
    parser.add_argument('--folder');parser.add_argument('--candidate')
    args=parser.parse_args()
    if args.candidate and not args.folder:parser.error('A candidate requires a new --folder')
    if not args.allow_paid:parser.error('Offline default: pass --allow-paid only with authorization')
    asyncio.run(main(args.folder,args.candidate))
