"""Alternating real-Gemini experiment through production DietTeam; synthetic DB.

No credentials, user records or model thoughts are written to reports. This is
an in-process comparison, not a public end-to-end latency measurement.
"""
import argparse
import asyncio
import json
import re
import statistics
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'backend'))
from dotenv import load_dotenv
load_dotenv(ROOT / 'backend/.env')
from app.agents.team import DietTeam
from app.agents.coaching_route import simple_followup
from app.core.config import get_settings
from app.core.llm import get_chat_model
from benchmark_multiturn_delivery import SCENARIOS


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', type=Path, default=ROOT/'docs/coaching_thinking')
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    # A stale previous answer must not override current confirmed/deleted/goal data.
    for case, calories, target in [('confirmed', 600, 2000), ('deleted', 0, 2000), ('goal_changed', 600, 1800)]:
        for name, first, follow in SCENARIOS:
            pair = len(rows)//2
            levels = [None, 'low'] if pair % 2 == 0 else ['low', None]
            message = follow + ' 첫 문장에 "오늘 섭취: N kcal, 하루 기준: N kcal" 형식으로 적어줘.'
            history = [{'role':'user', 'content':first}, {'role':'assistant',
                'content':'이전 조회의 섭취 기록은 300 kcal, 목표는 2000 kcal입니다. 밥과 단백질 반찬을 곁들이세요.'}]
            assert simple_followup({'message':message, 'messages':history}), 'Experiment must exercise the scoped route'
            for level in levels:
                async def read_rows(table, **filters):
                    if table == 'users': return [{'goal':'diet'}]
                    if table == 'diet_strategies': return [{'daily_calories':target}]
                    return [{'calories':calories}] if calories else []
                repo = AsyncMock()
                team = DietTeam({'user_id':'synthetic-thinking', 'message':message, 'messages':history},
                    repository=repo, db=object(), model_factory=lambda:get_chat_model(thinking_level=level))
                team.rows = AsyncMock(side_effect=read_rows)
                started = time.perf_counter()
                result = await team.execute()
                elapsed = time.perf_counter()-started
                answer = result['response']
                assert result['agent_used'] == 'meal'
                match = re.search(r'오늘\s*섭취\s*[:：]\s*([\d,]+)\s*kcal.*?하루\s*기준\s*[:：]\s*([\d,]+)\s*kcal', answer.replace('**',''), re.S|re.I)
                fresh = bool(match and tuple(int(s.replace(',','')) for s in match.groups()) == (calories, target))
                row = {'pair':pair, 'case':case, 'scenario':name, 'level':level or 'default',
                    'seconds':elapsed, 'question':message, 'history':history,
                    'expected_calories':calories, 'expected_target':target,
                    'fresh':fresh, 'status':result['execution_status'], 'agent':result['agent_used'],
                    'usage':result['execution_usage'], 'answer':answer,
                    'no_write':not repo.create.called and not repo.resolve.called and not result.get('pending_proposal')}
                rows.append(row)
                summary = {key:{'n':len(group), 'median_seconds':statistics.median(r['seconds'] for r in group),
                    'fresh':sum(r['fresh'] for r in group), 'completed':sum(r['status']=='completed' for r in group),
                    'no_write':sum(r['no_write'] for r in group)}
                    for key in ['default','low'] if (group := [r for r in rows if r['level']==key])}
                report = {'model':get_settings().gemini_model, 'scope':'alternating_real_model_synthetic_db_production_team',
                    'summary':summary,'rows':rows}
                (args.output_dir/'ALTERNATING.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
                print(case, name, level or 'default', round(elapsed,2), 'fresh',fresh, result['execution_status'],flush=True)
    print(json.dumps(summary),flush=True)


if __name__ == '__main__': asyncio.run(main())
