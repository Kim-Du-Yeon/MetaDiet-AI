"""Additive migration + rolled-back synthetic HITL verification. No real users changed."""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
import sys
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from psycopg import AsyncConnection, Rollback
from psycopg.rows import dict_row
from app.core.config import get_settings
from app.core.onboarding import OnboardingRequest
import app.core.onboarding as onboarding
from app.db.proposals import ProposalRepository,ProposalConflict


async def main():
    migration=Path(__file__).resolve().parents[2]/'supabase/migrations/20261010065145_nutrition_policy_context.sql'
    async with await AsyncConnection.connect(get_settings().supabase_db_url,row_factory=dict_row,connect_timeout=10) as conn:
        await conn.execute("set statement_timeout='15s'")
        cols=await (await conn.execute("select column_name from information_schema.columns where table_schema='public' and table_name='users'")).fetchall()
        required={'age','weight_kg','region','target_weight_kg','target_date','goal_priority'}
        missing=required-{c['column_name'] for c in cols}
        if missing: raise RuntimeError('Required existing columns missing: '+','.join(sorted(missing)))
        await conn.execute(migration.read_text(encoding='utf8'))
        await conn.commit()
        print('additive migration applied')
        async with conn.transaction():
            @asynccontextmanager
            async def connect():
                async with conn.transaction(): yield conn
            onboarding.connection=connect
            repo=ProposalRepository(connect)
            auth_id=str(uuid4())
            from datetime import date,timedelta
            req=OnboardingRequest(age=30,sex='male',weight_kg=70,height_cm=170,activity='low_active',general_adult_confirmed=True,goal='diet',target_weight_kg=65,target_date=date.today()+timedelta(days=100))
            first=await onboarding.save_onboarding(req,auth_id)
            assert first['goal_assessment']['status']=='adjustment_ready'
            assert first['goal_assessment']['applied_adjustment_kcal']==-500
            assert first['pending_proposal']['payload']['daily_calories']==first['goal_assessment']['target_calories']
            assert (await onboarding.onboarding_status(auth_id))['pending_proposal']['id']==first['pending_proposal']['id']
            user=await (await conn.execute('select id from users where auth_id=%s',(auth_id,))).fetchone()
            uid=str(user['id']); p=first['pending_proposal']
            assert (await (await conn.execute('select count(*) n from diet_strategies where user_id=%s',(uid,))).fetchone())['n']==0
            await repo.resolve(uid,p['id'],p['version'],'cancel')
            second=await onboarding.save_onboarding(req,auth_id); p=second['pending_proposal']
            saved=await repo.resolve(uid,p['id'],p['version'],'confirm')
            assert saved['status']=='confirmed'
            assert (await onboarding.onboarding_status(auth_id))['current_strategy']
            await repo.resolve(uid,p['id'],p['version'],'confirm')
            assert (await (await conn.execute('select count(*) n from diet_strategies where user_id=%s',(uid,))).fetchone())['n']==1
            third=await onboarding.save_onboarding(req,auth_id); p=third['pending_proposal']
            assert third['current_strategy']['id']==saved['result']['strategy_id'] or str(third['current_strategy']['id'])==saved['result']['strategy_id']
            await conn.execute('update users set weight_kg=71 where id=%s',(uid,))
            try:
                await repo.resolve(uid,p['id'],p['version'],'confirm')
                raise AssertionError('Changed profile must block approval')
            except ProposalConflict: pass
            await conn.execute('update users set weight_kg=70 where id=%s',(uid,))
            await conn.execute('update users set target_weight_kg=64 where id=%s',(uid,))
            try:
                await repo.resolve(uid,p['id'],p['version'],'confirm')
                raise AssertionError('Changed target must block approval')
            except ProposalConflict: pass
            original_create=ProposalRepository.create
            async def fail_create(*args,**kwargs): raise RuntimeError('synthetic create failure')
            ProposalRepository.create=fail_create
            failed_auth=str(uuid4())
            try:
                try: await onboarding.save_onboarding(req,failed_auth)
                except RuntimeError: pass
                assert (await (await conn.execute('select count(*) n from users where auth_id=%s',(failed_auth,))).fetchone())['n']==0
            finally: ProposalRepository.create=original_create
            print('real DB: status resume, pending/no strategy, cancel/retry, confirm, duplicate, existing preservation, changed-profile block, profile/proposal failure rollback passed')
            raise Rollback()
        print('synthetic profile/proposals/strategies rolled back')


if __name__=='__main__':
    if sys.platform=='win32': asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
