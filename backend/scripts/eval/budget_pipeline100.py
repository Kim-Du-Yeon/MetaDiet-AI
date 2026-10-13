"""Matched real-model + isolated real-Postgres reservations, 100 per condition.

No real user rows are read or changed. Temporary unexposed schema is removed
in finally; its identifier is retained locally for recovery, never a credential.
"""
import argparse
import asyncio
from contextlib import asynccontextmanager
import json
import re
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'backend'))
from dotenv import load_dotenv
load_dotenv(ROOT / 'backend/.env')
from psycopg import sql
from app.agents.team import DietTeam, team_node
from app.agents.runtime import ExecutionStopped
from app.agents.execution_stream import set_event_sink, reset_event_sink
from app.db import budget_pool
from app.db.execution_budget import DurableBudget
from app.core.config import get_settings
from app.core.llm import get_chat_model


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--safety-only', action='store_true')
    args = parser.parse_args()
    folder = ROOT / 'docs/budget_pipeline'
    output = folder / ('safety.json' if args.safety_only else 'paired.json')
    if output.exists():
        raise SystemExit('Refusing to overwrite evidence')
    schema = 'budget_eval_' + uuid4().hex
    user = str(uuid4())
    settings = get_settings()
    rows = []
    report = {'scope': 'real_model_and_isolated_postgres_synthetic_profile_100_each',
              'model': settings.gemini_model, 'rows': rows, 'schema_cleaned': False}
    (ROOT / 'tmp').mkdir(exist_ok=True)
    (ROOT / 'tmp/budget_pipeline_schema.txt').write_text(schema, encoding='utf-8')
    async with budget_pool.lifespan(settings.supabase_db_url):
        async with budget_pool.connection(pipeline=False) as conn:
            await conn.execute(sql.SQL('create schema {}').format(sql.Identifier(schema)))
            await conn.execute(sql.SQL('create table {}.agent_execution_budgets '
                '(like public.agent_execution_budgets including all)').format(sql.Identifier(schema)))
            await conn.execute(sql.SQL('alter table {}.agent_execution_budgets enable row level security').format(sql.Identifier(schema)))
            await conn.execute(sql.SQL('revoke all on schema {} from public, anon, authenticated').format(sql.Identifier(schema)))
        class Isolated:
            def __init__(self, conn): self.conn = conn
            async def execute(self, query, params=None):
                # Only known application's table identifier is substituted;
                # parameters remain bound, user input never enters SQL text.
                query = query.replace('agent_execution_budgets', schema + '.agent_execution_budgets')
                return await self.conn.execute(query, params)
        def connection(mode):
            @asynccontextmanager
            async def selected():
                async with budget_pool.connection(pipeline=mode == 'pipeline') as conn:
                    yield Isolated(conn)
            return selected
        try:
            # Independent connections contend for same row: counters must not
            # lose updates or exceed cap, including INSERT-conflict path.
            safety = {}
            for mode in ('baseline', 'pipeline'):
                run = str(uuid4())
                def make():
                    return DurableBudget(user, run, {'model_calls': 5, 'elapsed_seconds': 1800}, connect=connection(mode))
                async def reserve():
                    try:
                        await make().reserve('model')
                        return 'reserved'
                    except ExecutionStopped as exc:
                        return str(exc)
                outcomes = await asyncio.gather(*(reserve() for _ in range(12)))
                assert outcomes.count('reserved') == 5 and outcomes.count('model_calls_limit') == 7
                usage = await make().update(finish=True)
                assert usage['model_calls'] == 5
                try:
                    await make().reserve('model')
                    raise AssertionError('recreated budget bypassed cap')
                except ExecutionStopped as exc:
                    assert str(exc) == 'model_calls_limit'
                rollback_run = str(uuid4())
                try:
                    async with connection(mode)() as conn:
                        await conn.execute('insert into agent_execution_budgets(user_id,run_id) values(%s,%s)', (user, rollback_run))
                        await conn.execute('select 1 / 0')
                except Exception as exc:
                    assert type(exc).__name__ == 'DivisionByZero'
                async with connection(mode)() as conn:
                    count = await (await conn.execute('select count(*) as n from agent_execution_budgets where user_id=%s and run_id=%s', (user, rollback_run))).fetchone()
                    assert count['n'] == 0
                safety[mode] = {'concurrent_reserved': 5, 'concurrent_blocked': 7, 'restart_cap': True, 'rollback': True}
            report['safety'] = safety
            print('Live transaction safety passed', flush=True)
            if args.safety_only:
                return
            questions = ['그럼 한식뷔페 가서 일반식 먹어도 괜찮아?', '그럼 샌드위치 먹어도 괜찮아?',
                         '밥이랑 계란 먹어도 괜찮아?', '닭가슴살이랑 샐러드 먹어도 괜찮아?']
            contexts = [('confirmed', 600, 2000), ('edited', 850, 2000), ('deleted', 0, 2000),
                        ('goal_changed', 600, 1800), ('new_day', 0, 1900)]
            for pair in range(100):
                case, calories, target = contexts[(pair // 4) % 5]
                message = questions[pair % 4] + ' 첫 문장에 "오늘 섭취: N kcal, 하루 기준: N kcal" 형식으로 적어줘.'
                history = [{'role': 'user', 'content': '점심 추천해줘'}, {'role': 'assistant',
                            'content': '이전 조회의 섭취 기록은 300 kcal, 목표는 2200 kcal입니다. 밥과 채소를 곁들이세요.'}]
                for mode in (['baseline', 'pipeline'] if pair % 2 == 0 else ['pipeline', 'baseline']):
                    repo = AsyncMock()
                    diagnostics = {'stage_timings_ms': {}}
                    async def sink(kind, payload):
                        if kind == 'stage_timing':
                            stages = diagnostics['stage_timings_ms']
                            stages[payload['stage']] = stages.get(payload['stage'], 0) + payload['elapsed_ms']
                        if kind == 'model_usage':
                            usage = diagnostics.setdefault('tokens', {})
                            for k, v in payload.items(): usage[k] = usage.get(k, 0) + v
                    async def read_rows(table, **filters):
                        if table == 'users': return [{'goal': 'diet'}]
                        if table == 'diet_strategies': return [{'daily_calories': target}]
                        return [{'calories': calories}] if calories else []
                    def make_team(state, **kwargs):
                        team = DietTeam(state, repository=repo, db=object(), config=kwargs.get('config'),
                                        model_factory=lambda: get_chat_model(thinking_level='low'))
                        team.rows = AsyncMock(side_effect=read_rows)
                        return team
                    def make_budget(*args, **kwargs):
                        return DurableBudget(*args, connect=connection(mode), **kwargs)
                    row = dict(pair=pair, mode=mode, case=case, question=message,
                               expected_calories=calories, expected_target=target,
                               status='failed', fresh=False, no_write=False)
                    event_token = set_event_sink(sink)
                    started = time.perf_counter()
                    try:
                        with patch('app.agents.team.DietTeam', make_team), patch('app.db.execution_budget.DurableBudget', make_budget):
                            result = await asyncio.wait_for(team_node({'user_id': user, 'run_id': str(uuid4()),
                                'message': message, 'messages': history}), 150)
                        answer = result['response']
                        match = re.search(r'오늘\s*섭취\s*[:：]\s*([\d,]+)\s*kcal.*?하루\s*기준\s*[:：]\s*([\d,]+)\s*kcal', answer.replace('**', ''), re.S | re.I)
                        row.update(status=result['execution_status'], answer=answer, usage=result.get('execution_usage'),
                            fresh=bool(match and tuple(int(v.replace(',', '')) for v in match.groups()) == (calories, target)),
                            no_write=not repo.create.called and not repo.resolve.called and not result.get('pending_proposal'))
                    except Exception as exc:
                        row['error_type'] = type(exc).__name__
                    finally:
                        reset_event_sink(event_token)
                    row.update(total_ms=(time.perf_counter()-started)*1000, **diagnostics)
                    rows.append(row)
                    output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
                    print(pair, mode, row['status'], round(row['total_ms']), row['fresh'], flush=True)
            assert len(rows) == 200
        finally:
            async with budget_pool.connection(pipeline=False) as conn:
                await conn.execute(sql.SQL('drop schema {} cascade').format(sql.Identifier(schema)))
            report['schema_cleaned'] = True
            output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__':
    if sys.platform == 'win32': asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
