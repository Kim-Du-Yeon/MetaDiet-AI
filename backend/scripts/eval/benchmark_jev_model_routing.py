"""Rules vs Jev model choice only, 100 frozen synthetic cases/condition.

No downstream generation, DB access, user health data, or implied cost savings.
Preferred bands are developer policy annotations, not measured model capability.
"""
import argparse
import asyncio
from collections import Counter
from datetime import datetime,timezone
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
import time

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'backend'))
from dotenv import dotenv_values,load_dotenv
load_dotenv(ROOT/'backend/.env')
from app.core.config import get_settings
from app.core.jev import JevClient
from app.core.prompts import prompt_metadata
from app.agents.runtime import ExecutionBudget
from scripts.eval.jev_model_router import RoutingRequest,select_model


def frozen_cases():
    foods=['닭가슴살','밥','김치','제육볶음','김치찌개','계란후라이','만두','피자','소보로빵','고구마']
    questions=[]
    for i in range(20):
        food=foods[i%10]
        questions.extend([
            {'task':'extraction','text':f'{food} {100+i*10}g 먹었어. 음식명과 양만 추출해.', 'preferred_band':'fast','group':'clear_extract'},
            {'task':'classification','text':f'문장: 오늘 {food} 먹었어. 식사 기록인지 조언인지 분류해.', 'preferred_band':'fast','group':'clear_classify'},
            {'task':'query_translation','text':f'{food} 관련 영양 지침을 찾는 짧은 영어 검색어로 번역해.', 'preferred_band':'fast','group':'clear_translate'},
            {'task':'extraction','text':f'앞선 기록은 {food}100g과 밥200g이고 정정은 첫 항목만150g이다. 그 뒤 첫 음식의 절반만 먹었다. 중간 정정을 반영해 최종 음식과 g를 추출해.', 'preferred_band':'standard','group':'context_extract'},
            {'task':'query_translation' if i%2==0 else 'classification',
             'text':f'앞 문장에서는 {food}의 일반적인 섭취 근거를 묻고 다음 문장에서는 무조건 좋다는 전제를 취소했다. 서로 모순된 전제를 제거하고 의도와 근거 질의를 구분해 처리해.',
             'preferred_band':'standard','group':'conflicting_context'}])
    return [{'id':f'route-{i:03}',**row} for i,row in enumerate(questions)]


def summarize(rows):
    n=len(rows)
    elapsed=sorted(r['ms'] for r in rows)
    success=[r for r in rows if r['status']=='completed']
    return {'attempts':n,'completed':len(success),'fallbacks':sum(r['status']=='fallback' for r in rows),
        'transport_or_protocol_failures':sum(r['status']=='failed' for r in rows),
        'preferred_band_matches':sum(r['preferred_match'] for r in rows),
        'direct_nonfallback_matches':sum(r['preferred_match'] and r['status']=='completed' for r in rows),
        'jev_api_calls':sum(r['budget_model_calls'] for r in rows),
        'p50_ms':statistics.median(elapsed),'p95_ms':elapsed[math.ceil(n*.95)-1],
        'input_tokens_known':sum((r.get('decision') or {}).get('usage',{}).get('input_tokens',0) for r in rows),
        'output_tokens_known':sum((r.get('decision') or {}).get('usage',{}).get('output_tokens',0) for r in rows),
        'failure_reasons':dict(Counter((r.get('decision') or {}).get('fallback_reason') or r.get('error_type')
            for r in rows if r['status']!='completed'))}


async def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--env-file',type=Path,required=True)
    args=parser.parse_args()
    args.output_dir.mkdir(parents=True,exist_ok=True)
    output=args.output_dir/'paired.json'
    if output.exists(): raise SystemExit('Refusing to overwrite evidence')
    values=dotenv_values(args.env_file)
    key=values.get('TYPESAFE_API_KEY','')
    if not key: raise SystemExit('Missing TYPESAFE_API_KEY in explicit ignored env')
    settings=get_settings()
    client=JevClient(api_key=key,model=values.get('JEV_MODEL') or settings.jev_model)
    cases=frozen_cases()
    frozen=json.dumps(cases,ensure_ascii=False,indent=2)+'\n'
    (args.output_dir/'frozen.json').write_text(frozen,encoding='utf-8',newline='\n')
    report={'scope':'synthetic_router_only_not_generation_or_real_users','created_at':datetime.now(timezone.utc).isoformat(),
        'cases_sha256':hashlib.sha256(frozen.encode()).hexdigest(),'jev_model':client.model,
        'confidence_threshold':.9,'prompt_metadata':prompt_metadata(),
        'model_config':{k:getattr(settings,k) for k in ['gemini_model','gemini_simple_model']},
        'gold_scope':'developer preferred-tier policy, not independently validated model capability',
        'cost_usd':None,'downstream_quality':None,'latest_record_reflection':None,'rows':[]}
    for index,case in enumerate(cases):
        for mode in (['rules','jev'] if (index//5)%2==0 else ['jev','rules']):
            budget=ExecutionBudget(max_model_calls=1,timeout_seconds=7)
            started=time.perf_counter()
            try:
                result=await select_model(RoutingRequest(task=case['task'],text=case['text']),
                    mode=mode,settings=settings,client=client,budget=budget)
            except Exception as exc:
                result={'status':'failed','band':'standard','model':settings.gemini_model,'error_type':type(exc).__name__}
            report['rows'].append({'case_id':case['id'],'condition':mode,'group':case['group'],**result,
                'ms':(time.perf_counter()-started)*1000,'budget_model_calls':budget.model_calls,
                'preferred_match':result['band']==case['preferred_band']})
            output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
        print(case['id'],report['rows'][-1]['status'],flush=True)
        await asyncio.sleep(.1)
    report['summary']={mode:summarize([r for r in report['rows'] if r['condition']==mode]) for mode in ['rules','jev']}
    report['by_group']={group:{mode:summarize([r for r in report['rows'] if r['condition']==mode and r['group']==group])
        for mode in ['rules','jev']} for group in sorted({c['group'] for c in cases})}
    report['production_adoption']=False
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(report['summary'],ensure_ascii=False),flush=True)


if __name__=='__main__': asyncio.run(main())
