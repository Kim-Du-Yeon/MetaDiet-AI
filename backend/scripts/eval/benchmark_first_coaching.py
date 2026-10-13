"""Three-arm real-model comparison with production tools and synthetic DB reads."""
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'backend'))
from dotenv import load_dotenv
load_dotenv(ROOT/'backend/.env')
from app.core.config import get_settings
from app.agents.team import DietTeam
from app.agents.coaching_route import simple_recommendation
from benchmark_multiturn_delivery import SCENARIOS


async def main():
    folder = ROOT/'docs/first_coaching'
    folder.mkdir(parents=True, exist_ok=True)
    settings = get_settings()
    previous = settings.first_coaching_mode
    rows = []
    variants = [('baseline','off'),('direct_default','default'),('direct_low','low')]
    try:
        for case, calories, target in [('confirmed',600,2000), ('deleted_goal_changed',0,1800)]:
            for scenario, question, _ in SCENARIOS:
                question += ' 오늘 남은 칼로리도 알려줘.'
                assert simple_recommendation({'message':question})
                history = [{'role':'user','content':'이전 상황은 어때?'},
                    {'role':'assistant','content':'이전 섭취 300 kcal, 하루 목표 2000 kcal입니다.'}]
                pair = len(rows)//3
                order = variants[pair%3:] + variants[:pair%3]
                for label, mode in order:
                    settings.first_coaching_mode = mode
                    async def read_rows(table, **filters):
                        if table == 'users': return [{'goal':'diet'}]
                        if table == 'diet_strategies': return [{'daily_calories':target}]
                        return [{'calories':calories}] if calories else []
                    repo = AsyncMock()
                    team = DietTeam({'user_id':'synthetic-first','message':question,'messages':history},
                        db=object(),repository=repo)
                    team.rows = AsyncMock(side_effect=read_rows)
                    started = time.perf_counter()
                    result = await team.execute()
                    elapsed = time.perf_counter()-started
                    assert result['agent_used'] == ('supervisor' if mode=='off' else 'meal')
                    rows.append({'pair':pair,'case':case,'scenario':scenario,'level':label,
                        'question':question,'history':history,'expected_calories':calories,
                        'expected_target':target,'expected_remaining':target-calories,
                        'seconds':elapsed,'answer':result['response'],'usage':result['execution_usage'],
                        'status':result['execution_status'],'agent':result['agent_used'],
                        'no_write':not repo.create.called and not repo.resolve.called and not result.get('pending_proposal')})
                    summary = {name:{'n':len(group),'median_seconds':statistics.median(r['seconds'] for r in group),
                        'median_model_calls':statistics.median(r['usage']['model_calls'] for r in group),
                        'completed':sum(r['status']=='completed' for r in group),'no_write':sum(r['no_write'] for r in group)}
                        for name,_ in variants if (group:=[r for r in rows if r['level']==name])}
                    report = {'scope':'three_arm_real_gemini_synthetic_db_rotating_order',
                        'model':settings.gemini_model,'summary':summary,'rows':rows}
                    (folder/'ALTERNATING.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
                    print(case,scenario,label,round(elapsed,2),result['execution_status'],flush=True)
        print(json.dumps(summary),flush=True)
    finally:
        settings.first_coaching_mode = previous


if __name__ == '__main__': asyncio.run(main())
