"""Functional real-Postgres concurrency/rollback checks, not a performance eval."""
import asyncio
from contextlib import asynccontextmanager
import json
import os
import sys

from benchmark_intake_snapshot import safe_dsn,prepare,ROOT,OWNER,MEAL,BASE
import psycopg
from psycopg.rows import dict_row
from fastapi import HTTPException


async def run():
    dsn=safe_dsn(); prepare(dsn)
    os.environ.update(SUPABASE_DB_URL=dsn,SUPABASE_URL='http://127.0.0.1:55439',
        SUPABASE_SERVICE_KEY='isolated-test-placeholder',SUPABASE_JWT_SECRET='isolated-test-placeholder',
        GEMINI_API_KEY='isolated-test-placeholder',PINECONE_API_KEY='isolated-test-placeholder',LANGSMITH_TRACING='false')
    from app.db import intake_snapshot as module
    from app.core.service_clock import service_today
    @asynccontextmanager
    async def connect():
        async with await psycopg.AsyncConnection.connect(dsn,row_factory=dict_row) as conn:
            await conn.execute("set local statement_timeout='5s'")
            yield conn
    def reset():
        with psycopg.connect(dsn,row_factory=dict_row) as conn:
            conn.execute('delete from meal_logs')
            conn.execute("insert into meal_logs values(%s,%s,%s,'밥','lunch',10,15,.3,3,.1,0)",(MEAL,OWNER,service_today()))
            return conn.execute('select * from meal_logs where id=%s',(MEAL,)).fetchone()
    for _ in range(10):
        original=reset(); token=module.record_version(original)
        results=await asyncio.gather(*[module.mutate_meal(OWNER,MEAL,grams,
            expected_record_version=token,connect=connect) for grams in (20,30)],return_exceptions=True)
        assert sum(isinstance(r,dict) and r['success'] for r in results)==1
        assert sum(isinstance(r,HTTPException) and r.status_code==409 for r in results)==1
        with psycopg.connect(dsn) as conn:
            calories=conn.execute('select calories from meal_logs where id=%s',(MEAL,)).fetchone()[0]
        success=next(r for r in results if isinstance(r,dict))
        assert success['sync']['today_calories']==calories
    original=reset()
    real=module.make_snapshot
    def invalid(*args): raise ValueError('injected_snapshot_failure')
    module.make_snapshot=invalid
    try:
        try: await module.mutate_meal(OWNER,MEAL,20,connect=connect)
        except HTTPException as error: assert error.status_code==409
        else: raise AssertionError('rollback_required')
    finally: module.make_snapshot=real
    with psycopg.connect(dsn) as conn:
        assert conn.execute('select quantity_g from meal_logs where id=%s',(MEAL,)).fetchone()[0]==10
    result={'concurrent_pairs':10,'successes':10,'stale_or_serialization_rejections':10,
            'snapshot_matches_committed_value':True,'post_write_snapshot_failure_rolls_back':True,
            'environment':'isolated local PostgreSQL; functional checks only'}
    path=ROOT/'docs/food_catalog/intake-snapshot-20261019/transaction-checks.json'
    path.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))


if __name__=='__main__':
    if sys.platform=='win32': asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run())
