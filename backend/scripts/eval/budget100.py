"""100 alternating reservations per implementation against an isolated live DB run."""
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from uuid import uuid4
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'backend'))
from benchmark_coaching import load_env, service_api
from app.db import budget_pool
from app.db.execution_budget import DurableBudget
from app.core.config import get_settings
from app.agents.runtime import ExecutionStopped


async def main():
    output = ROOT/'docs/latency100/budget.json'
    if output.exists(): raise SystemExit('Refusing to overwrite evidence')
    load_env(ROOT/'backend/.env'); load_env(ROOT/'backend/.env.selection-browser')
    assert os.environ['EMAIL'].startswith('selection-') and os.environ['EMAIL'].endswith('@example.invalid')
    user = service_api('/rest/v1/users?auth_id=eq.'+os.environ['AUTH_ID']+'&select=id')[0]['id']
    run_ids = [str(uuid4()), str(uuid4())]
    rows = []
    async with budget_pool.lifespan(get_settings().supabase_db_url):
        budgets = {mode: DurableBudget(user, run, {'model_calls': 100, 'elapsed_seconds': 1800}, initialize_once=mode == 'after')
                   for mode, run in zip(['before', 'after'], run_ids)}
        try:
            for budget in budgets.values(): await budget.update()
            for pair in range(100):
                for mode in (['before', 'after'] if pair % 2 == 0 else ['after', 'before']):
                    budget = budgets[mode]
                    started = time.perf_counter()
                    await budget.reserve('model')
                    rows.append({'pair': pair, 'mode': mode, 'ms': (time.perf_counter()-started)*1000})
                output.write_text(json.dumps({'scope': 'live_db_alternating_reservations_100_each',
                    'rows': rows}, indent=2)+'\n', encoding='utf-8')
            for budget in budgets.values():
                try:
                    await budget.reserve('model')
                    raise AssertionError('call limit bypassed')
                except ExecutionStopped: pass
            async with budget_pool.connection() as conn:
                for run in run_ids:
                    row = await (await conn.execute('select usage from agent_execution_budgets where user_id=%s and run_id=%s', (user, run))).fetchone()
                    assert row['usage']['model_calls'] == 100
            output.write_text(json.dumps({'scope': 'live_db_alternating_reservations_100_each',
                'persisted_100_each': True, 'limit_blocked_both': True, 'rows': rows}, indent=2)+'\n', encoding='utf-8')
            print('100 reservations each; persisted counters and cap verified', flush=True)
        finally:
            async with budget_pool.connection() as conn:
                for run in run_ids:
                    await conn.execute('delete from agent_execution_budgets where user_id=%s and run_id=%s', (user, run))


if __name__ == '__main__':
    if sys.platform == 'win32': asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
