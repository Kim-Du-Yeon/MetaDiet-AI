"""100 paired, alternating real-model calls per prompt, synthetic fresh DB.

Measures scoped prompt reduction, not public latency. No production
records are modified; answers are synthetic evaluation evidence, not user data.
"""
import asyncio
import json
import re
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'backend'))
from dotenv import load_dotenv
load_dotenv(ROOT/'backend/.env')
from app.agents.team import DietTeam
from app.agents.execution_stream import set_event_sink, reset_event_sink
from app.core.config import get_settings
from app.core.llm import get_chat_model


async def main():
    output = ROOT/'docs/compact_coaching/paired.json'
    if output.exists():
        raise SystemExit('Refusing to overwrite evidence')
    rows = []
    questions = ['그럼 한식뷔페 가서 일반식 먹어도 괜찮아?', '그럼 샌드위치 먹어도 괜찮아?',
                 '밥이랑 계란 먹어도 괜찮아?', '닭가슴살이랑 샐러드 먹어도 괜찮아?']
    contexts = [('confirmed', 600, 2000), ('edited', 850, 2000), ('deleted', 0, 2000),
                ('goal_changed', 600, 1800), ('new_day', 0, 1900)]
    settings = get_settings()
    for pair in range(100):
        case, calories, target = contexts[(pair//4) % 5]
        message = questions[pair % 4] + ' 첫 문장에 "오늘 섭취: N kcal, 하루 기준: N kcal" 형식으로 적어줘.'
        history = [{'role': 'user', 'content': '점심 추천해줘'}, {'role': 'assistant',
                    'content': '이전 조회의 섭취 기록은 300 kcal, 목표는 2200 kcal입니다. 밥과 채소를 곁들이세요.'}]
        for mode in (['baseline', 'compact'] if pair % 2 == 0 else ['compact', 'baseline']):
            async def read_rows(table, **filters):
                if table == 'users': return [{'goal': 'diet'}]
                if table == 'diet_strategies': return [{'daily_calories': target}]
                return [{'calories': calories}] if calories else []
            repo = AsyncMock()
            diagnostics = {}
            async def sink(kind, payload):
                if kind == 'model_first_token': diagnostics.setdefault('model_first_token_ms', payload['elapsed_ms'])
                if kind == 'model_usage':
                    usage = diagnostics.setdefault('tokens', {})
                    for k, v in payload.items(): usage[k] = usage.get(k, 0) + v
            event_token = set_event_sink(sink)
            started = time.perf_counter()
            row = dict(pair=pair, case=case, mode=mode, question=message, expected_calories=calories,
                       expected_target=target, status='failed', fresh=False, no_write=False)
            try:
                with patch('app.agents.team.get_settings', lambda: settings.model_copy(update={'coaching_delivery': 'invoke', 'compact_followup_prompt': mode == 'compact'})):
                    team = DietTeam({'user_id': 'synthetic-streaming', 'message': message, 'messages': history},
                        repository=repo, db=object(), model_factory=lambda: get_chat_model(thinking_level='low'))
                    team.rows = AsyncMock(side_effect=read_rows)
                    result = await asyncio.wait_for(team.execute(), 150)
                answer = result['response']
                match = re.search(r'오늘\s*섭취\s*[:：]\s*([\d,]+)\s*kcal.*?하루\s*기준\s*[:：]\s*([\d,]+)\s*kcal',
                                  answer.replace('**', ''), re.S | re.I)
                row.update(answer=answer, status=result['execution_status'], usage=result['execution_usage'],
                    fresh=bool(match and tuple(int(v.replace(',', '')) for v in match.groups()) == (calories, target)),
                    no_write=not repo.create.called and not repo.resolve.called and not result.get('pending_proposal'))
            except Exception as exc:
                row['error_type'] = type(exc).__name__
            finally:
                reset_event_sink(event_token)
            row.update(total_ms=(time.perf_counter()-started)*1000, **diagnostics)
            rows.append(row)
            output.write_text(json.dumps({'model': settings.gemini_model,
                'scope': 'alternating_prompt_real_model_synthetic_db_100_each', 'rows': rows}, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
            print(pair, mode, row['status'], round(row['total_ms']), row['fresh'], flush=True)
    assert len(rows) == 200


if __name__ == '__main__':
    asyncio.run(main())
