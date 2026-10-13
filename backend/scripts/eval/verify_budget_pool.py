"""Live DB test scoped to one disposable synthetic user and random run ID."""
import asyncio
import json
import os
import sys
from pathlib import Path
from uuid import uuid4
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'backend'))
from benchmark_coaching import load_env, service_api
from app.db import budget_pool
from app.db.execution_budget import DurableBudget
from app.agents.runtime import ExecutionStopped
from app.core.config import get_settings


async def main():
    load_env(ROOT / 'backend/.env')
    load_env(ROOT / 'backend/.env.selection-browser')
    assert os.environ['EMAIL'].startswith('selection-') and os.environ['EMAIL'].endswith('@example.invalid')
    user = service_api('/rest/v1/users?auth_id=eq.'+os.environ['AUTH_ID']+'&select=id')[0]['id']
    run_id = str(uuid4())
    async with budget_pool.lifespan(get_settings().supabase_db_url):
        budget = DurableBudget(user, run_id, {'model_calls': 4, 'elapsed_seconds': 180})
        async def reserve():
            try:
                await budget.reserve('model')
                return 'accepted'
            except ExecutionStopped:
                return 'blocked'
        try:
            results = await asyncio.gather(*(reserve() for _ in range(12)))
            assert results.count('accepted') == 4 and results.count('blocked') == 8
            async with budget_pool.connection() as conn:
                row = await (await conn.execute('select usage from agent_execution_budgets where user_id=%s and run_id=%s', (user, run_id))).fetchone()
            assert row['usage']['model_calls'] == 4
            try:
                async with budget_pool.connection() as conn:
                    await conn.execute('delete from agent_execution_budgets where user_id=%s and run_id=%s', (user, run_id))
                    raise ValueError('intentional rollback')
            except ValueError:
                pass
            async with budget_pool.connection() as conn:
                row = await (await conn.execute('select usage from agent_execution_budgets where user_id=%s and run_id=%s', (user, run_id))).fetchone()
            assert row['usage']['model_calls'] == 4
            report = {'concurrent_reservations': 12, 'accepted': 4, 'blocked': 8, 'persisted_count': 4, 'rollback_preserved_row': True}
            (ROOT / 'docs/coaching_stages/BUDGET_POOL_INTEGRATION.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
            print(report)
        finally:
            async with budget_pool.connection() as conn:
                await conn.execute('delete from agent_execution_budgets where user_id=%s and run_id=%s', (user, run_id))


if __name__ == '__main__':
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
