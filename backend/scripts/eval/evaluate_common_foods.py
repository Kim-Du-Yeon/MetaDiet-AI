"""Frozen 100 distinct foods, real DietTeam/model/catalog, memory-only proposals.

This is a synthetic core-flow evaluation, NOT a public browser, HTTP latency,
nutrient accuracy or actual user study. No application/health records are written.
"""
import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'backend'))
DATASET=ROOT/'docs/food_catalog/COMMON_FOODS_100.json'
OUTPUT=ROOT/'docs/food_catalog/COMMON_FOODS_100_RESULTS.json'


def load_cases():
    raw=DATASET.read_bytes();data=json.loads(raw)
    cases=[{'id':index+1,'category':category,'food':food,
            'message':data['prompt_template'].format(food=food)}
        for index,(category,food) in enumerate((cat,food)
            for cat,foods in data['categories'].items() for food in foods)]
    if len(cases)!=100 or len({c['food'] for c in cases})!=100:
        raise ValueError('require_100_distinct_foods')
    return cases,hashlib.sha256(raw).hexdigest()


def classify_result(result):
    proposal=result.get('pending_proposal')
    if proposal:
        meals=proposal.get('payload',{}).get('meals') or []
        valid=(proposal.get('status')=='pending' and proposal.get('kind')=='intake'
            and result.get('awaiting_confirmation') is True and bool(meals))
        for meal in meals:
            for key in ['quantity_g','calories','carbs_g','protein_g','fat_g']:
                value=meal.get(key)
                valid=valid and isinstance(value,(int,float)) and math.isfinite(value) and value>=0
            valid=valid and meal.get('quantity_g',0)>0 and bool(meal.get('food_id'))
        return 'auto_card' if valid else 'invalid_card'
    choice=result.get('food_selection') or {}
    if choice.get('items'):
        return 'manual_choice' if choice.get('mode')=='meal_choices' else 'product_choice'
    if result.get('execution_status')=='blocked':return 'blocked'
    return 'no_proposal'


def summarize(rows,planned):
    counts=Counter(row['outcome'] for row in rows)
    return {'planned':planned,'completed_attempts':len(rows),'not_attempted':max(0,planned-len(rows)),
        'auto_card_count':counts['auto_card'],'auto_card_rate_planned':counts['auto_card']/planned,
        'outcomes':dict(sorted(counts.items()))}


class MemoryProposals:
    def __init__(self):self.created=0
    async def create(self,user,thread,payload,key):
        self.created+=1
        return {'id':str(uuid4()),'kind':payload['kind'],'version':1,'status':'pending','payload':payload}


class NoDomainDB:
    """record_only tools do not need a profile, intake or domain DB connection."""
    def table(self,*args,**kwargs):raise AssertionError('unexpected_domain_database_access')


async def run(concurrency=2, output=OUTPUT):
    # Only this child process; never alter the deployment's configuration.
    from dotenv import load_dotenv
    load_dotenv(ROOT/'backend/.env')
    for key in ['LANGSMITH_TRACING','LANGCHAIN_TRACING_V2']:os.environ[key]='false'
    from app.agents.team import DietTeam
    from app.tools.simple_meals import parse_simple_meal
    from app.tools.food_catalog import FoodCatalog
    from app.db.food_catalog import FoodRepository
    from app.core.config import get_settings
    cases,digest=load_cases();settings=get_settings()
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True,timeout=10).strip()
    report={'scope':'synthetic_real_DietTeam_and_Gemini_read_only_catalog_memory_proposals',
        'started_at_utc':datetime.now(timezone.utc).isoformat(),'runtime_commit':commit,'dataset_sha256':digest,
        'planned':100,'concurrency':concurrency,'model':settings.gemini_model,
        'runtime_file_sha256': {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
            for name in ['backend/app/tools/simple_meals.py', 'backend/app/tools/food_groups.py',
                         'backend/app/tools/reviewed_foods.py', 'backend/app/tools/food_catalog.py',
                         'backend/app/agents/team.py', 'backend/app/tools/common_representatives.py',
                         'backend/app/tools/common_representatives.json']},
        'requested_action':'record_only','application_db_access':'blocked','domain_writes':0,
        'proposal_repository':'memory_only','rows':[],'summary':summarize([],100),
        'limitations':['one attempt for each of100 distinct synthetic foods; not a population success rate',
            'core Agent only; HTTP/UI/checkpointer/durable budget writes excluded',
            'record_only food tools; coaching prefetch disabled and no profile/intake DB access',
            'auto_card means a pending editable quote, not correct identity or nutrient accuracy',
            'no speed improvement/p95 comparison or end-to-end public performance claim']}
    def persist():
        report['rows'].sort(key=lambda row:row['id'])
        report['summary']=summarize(report['rows'],100)
        report['categories']={cat:summarize([r for r in report['rows'] if r['category']==cat],10)
            for cat in dict.fromkeys(c['category'] for c in cases)}
        output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    semaphore=asyncio.Semaphore(concurrency)
    async def attempt(case):
        async with semaphore:
            start=time.perf_counter();row={**case,'outcome':'error'}
            repo=MemoryProposals()
            team=None
            try:
                parsed=parse_simple_meal(case['message'],allow_unknown=True)
                row['parser_route']='model_fallback' if parsed is None else (
                    'unresolved_choice' if any(i.get('unresolved') for i in parsed['items']) else 'deterministic')
                row['parsed_items']=parsed['items'] if parsed else []
                team=DietTeam({'message':case['message'],'requested_action':'record_only',
                    'user_id':str(uuid4()),'thread_id':'synthetic-food-100','run_id':str(uuid4())},
                    repository=repo,db=NoDomainDB(),coaching_prefetch_enabled=False,
                    config={'tags':['synthetic','common-foods-100'],'metadata':{'case_id':case['id']}})
                team.food_catalog=FoodCatalog(repository=FoodRepository())
                result=await asyncio.wait_for(team.execute(),settings.agent_timeout_seconds+10)
                row['outcome']=classify_result(result)
                row['usage']=result.get('execution_usage',{})
                row['response']=result.get('response','')
                row['meals']=(result.get('pending_proposal') or {}).get('payload',{}).get('meals',[])
                row['food_selection']=result.get('food_selection')
                row['events']=result.get('agent_events',[])
                row['one_food_item']=len(row['meals'])==1
            except (TimeoutError,asyncio.TimeoutError):row['outcome']='timeout'
            except Exception as exc:
                row['error_type']=type(exc).__name__
                # Never publish raw provider exceptions; they can contain credentials.
                if 'prepayment credits are depleted' in str(exc).lower():
                    row['error_reason']='model_prepaid_credits_depleted'
                    row['http_status']=402
            finally:
                if team is not None:
                    row.setdefault('usage',{'model_calls':team.budget.model_calls,'tool_calls':team.budget.tool_calls})
                row['memory_proposals_created']=repo.created
                row['core_wall_seconds']=round(time.perf_counter()-start,3)
                report['rows'].append(row);persist()
                print(json.dumps({'done':len(report['rows']),'food':case['food'],'outcome':row['outcome']},ensure_ascii=False),flush=True)
    persist()
    await asyncio.gather(*(attempt(case) for case in cases))
    report['finished_at_utc']=datetime.now(timezone.utc).isoformat()
    report['evaluation_completed']=len(report['rows'])==100
    persist();print(json.dumps(report['summary'],ensure_ascii=False),flush=True)
    return report['evaluation_completed']


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--concurrency',type=int,choices=[1,2],default=2)
    parser.add_argument('--output',type=Path,default=OUTPUT,
                        help='Use a separate file for a candidate; preserve baseline evidence.')
    args=parser.parse_args()
    if sys.platform=='win32':asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    raise SystemExit(0 if asyncio.run(run(args.concurrency,args.output)) else 1)
