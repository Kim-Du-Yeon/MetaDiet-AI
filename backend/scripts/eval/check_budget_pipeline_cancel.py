"""Live cancellation/rollback/reuse check, isolated schema, no user records."""
import asyncio
import json
import sys
from uuid import uuid4
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'backend'))
from dotenv import load_dotenv
load_dotenv(ROOT/'backend/.env')
from psycopg import sql
from app.db import budget_pool
from app.core.config import get_settings


async def main():
    output = ROOT/'docs/budget_pipeline/cancellation.json'
    if output.exists(): raise SystemExit('Refusing to overwrite evidence')
    schema = 'budget_cancel_' + uuid4().hex
    (ROOT/'tmp/budget_cancel_schema.txt').write_text(schema, encoding='utf-8')
    result = {'modes':{}, 'schema_cleaned':False}
    async with budget_pool.lifespan(get_settings().supabase_db_url):
        try:
            async with budget_pool.connection(pipeline=False) as conn:
                await conn.execute(sql.SQL('create schema {}').format(sql.Identifier(schema)))
                await conn.execute(sql.SQL('revoke all on schema {} from public, anon, authenticated').format(sql.Identifier(schema)))
                await conn.execute(sql.SQL('create table {}.probe (id int)').format(sql.Identifier(schema)))
                await conn.execute(sql.SQL('alter table {}.probe enable row level security').format(sql.Identifier(schema)))
            for enabled in (False, True):
                issued = asyncio.Event()
                async def transaction():
                    async with budget_pool.connection(pipeline=enabled) as conn:
                        await conn.execute(sql.SQL('insert into {}.probe values (1)').format(sql.Identifier(schema)))
                        issued.set()
                        cursor = await conn.execute('select pg_sleep(10)')
                        await cursor.fetchone()
                task = asyncio.create_task(transaction())
                await asyncio.wait_for(issued.wait(), 20)
                await asyncio.sleep(.2)
                task.cancel()
                try:
                    await asyncio.wait_for(task, 20)
                    raise AssertionError('cancellation not propagated')
                except asyncio.CancelledError:
                    pass
                async with budget_pool.connection(pipeline=enabled) as conn:
                    row = await (await conn.execute(sql.SQL('select count(*) as n from {}.probe').format(sql.Identifier(schema)))).fetchone()
                    assert row['n'] == 0, 'cancelled transaction committed'
                    row = await (await conn.execute('select 1 as n')).fetchone()
                    assert row['n'] == 1
                result['modes']['pipeline' if enabled else 'baseline'] = {'cancel_propagated':True, 'rollback':True, 'pool_reusable':True}
        finally:
            async with budget_pool.connection(pipeline=False) as conn:
                await conn.execute(sql.SQL('drop schema if exists {} cascade').format(sql.Identifier(schema)))
            result['schema_cleaned'] = True
            output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print('Cancellation, rollback and pool reuse passed for both modes')


if __name__ == '__main__':
    if sys.platform == 'win32': asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
