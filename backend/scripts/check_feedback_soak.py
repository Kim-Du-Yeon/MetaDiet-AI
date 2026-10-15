"""Bounded real Auth sessions, private DB soak and fault recovery; no public outage."""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time
from uuid import uuid4, uuid5, NAMESPACE_URL

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI
from psycopg import AsyncConnection, sql
from psycopg.rows import dict_row

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
sys.path.insert(0,str(ROOT/'backend/scripts'))
from app.core.config import get_settings
from app.core.auth import _decode_verified_token
from app.api.routes import admin_feedback as routes
from app.db.admin_feedback import AdminFeedbackRepository
from check_feedback_scale import frozen_cases, seed_rows, expected, summarize
from check_render_beta import service_api

OUTPUT=ROOT/'backend/artifacts/feedback-soak.json'
ENV=ROOT/'backend/.env.feedback-soak'


def fault_passed(row):
    return (row.get('status')==503 and row.get('unchanged') is True
            and row.get('recovery_status')==200 and row.get('audit_once') is True
            and row.get('audit_unchanged') is True)


async def track_creation(operation, remember):
    """Do not lose a completed remote identity when the caller is cancelled."""
    task=asyncio.ensure_future(operation)
    try:
        user=await asyncio.shield(task)
    except asyncio.CancelledError:
        user=await task
        remember(user)
        raise
    remember(user)
    return user


def reconcile_accounts(planned, known, list_page):
    """Resolve only exact pre-recorded fixture emails after an ambiguous create."""
    missing=set(planned)-set(known)
    if not missing:return list(known.values())
    for page in range(1,21):
        users=list_page(page)
        for user in users:
            email=str(user.get('email','')).lower()
            if email in missing:
                known[email]=user['id']
                missing.remove(email)
        if not missing or len(users)<100:return list(known.values())
    raise RuntimeError('auth_reconciliation_page_limit')


async def run():
    load_dotenv(ROOT/'backend/.env')
    settings=get_settings();dsn=settings.supabase_db_url
    schema='feedback_soak_'+uuid4().hex
    result={'scope':'real_supabase_JWT_local_ASGI_private_postgres_not_Render_soak',
            'planned_rounds':100,'sessions':3,'minimum_soak_seconds':600,
            'requests':[],'races':[],'faults':{},'diagnostics':[],'cleanup':{}}
    users=[];planned_emails=[];known_emails={};tokens=[];refresh=[];created=False;mode='normal'
    original_repo=routes.AdminFeedbackRepository;original_allowlist=settings.admin_emails
    if ENV.exists():raise RuntimeError('previous_fixture_requires_cleanup')
    ENV.write_text('SOAK_SCHEMA='+schema+'\n',encoding='utf-8')
    def persist():
        OUTPUT.parent.mkdir(parents=True,exist_ok=True)
        OUTPUT.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    def diagnostic(exc,stage):
        result['diagnostics'].append({'stage':stage,'error_type':type(exc).__name__,
                                      'sqlstate':getattr(exc,'sqlstate',None)})
    @asynccontextmanager
    async def plain():
        async with await AsyncConnection.connect(dsn,row_factory=dict_row,connect_timeout=10,
                options=f'-c search_path={schema},public -c statement_timeout=15000 -c lock_timeout=3000') as conn:
            yield conn
    class FaultConnection:
        def __init__(self,conn):self.conn=conn
        async def execute(self,query,params=None):
            cursor=await self.conn.execute(query,params)
            if isinstance(query,str) and 'update beta_feedback set' in query and mode=='close_after_update':
                await self.conn.close()
            return cursor
    @asynccontextmanager
    async def connect():
        try:
            async with plain() as conn:
                if mode=='statement_timeout':
                    await conn.execute("set local statement_timeout='50ms'")
                    await conn.execute('select pg_sleep(0.15)')
                elif mode=='closed_connection':
                    await conn.close()
                yield FaultConnection(conn)
        except Exception as exc:
            # Error class/state only; no SQL parameters, token or opinion bodies.
            result.setdefault('injected_errors',[]).append({'mode':mode,'error_type':type(exc).__name__,
                                                          'sqlstate':getattr(exc,'sqlstate',None)})
            raise
    async def call(client,method,path,**kwargs):
        return await asyncio.wait_for(client.request(method,path,**kwargs),30)
    try:
        # Admin allowlist is local to this process; production ADMIN_EMAILS is untouched.
        emails=[]
        for index in range(3):
            email=f'feedback-soak-{uuid4().hex}@example.invalid';password='S!'+uuid4().hex+'a9'
            planned_emails.append(email)
            with ENV.open('a',encoding='utf-8') as env:env.write('SOAK_EMAIL_'+str(index)+'='+email+'\n')
            def remember(user):
                known_emails[email]=user['id']
                users.append(user['id'])
                with ENV.open('a',encoding='utf-8') as env:env.write('SOAK_USER_'+str(index)+'='+user['id']+'\n')
            user=await track_creation(asyncio.to_thread(service_api,'/auth/v1/admin/users','POST',
                {'email':email,'password':password,'email_confirm':True}),remember)
            emails.append(email)
            session=await asyncio.to_thread(service_api,'/auth/v1/token?grant_type=password','POST',
                {'email':email,'password':password})
            tokens.append(session['access_token']);refresh.append(session['refresh_token'])
        settings.admin_emails=','.join(emails)
        claims=[await asyncio.to_thread(_decode_verified_token,token) for token in tokens]
        result['distinct_verified_sessions']=len({claim['session_id'] for claim in claims})==3
        result['verified_subjects_match']=all(claim['sub']==uid for claim,uid in zip(claims,users))
        async with await AsyncConnection.connect(dsn,connect_timeout=10,
                options='-c statement_timeout=20000 -c lock_timeout=5000') as conn:
            await conn.execute(sql.SQL('create schema {}').format(sql.Identifier(schema)))
            for table in ['beta_feedback','beta_feedback_history']:
                await conn.execute(sql.SQL('create table {} (like {} including all)').format(sql.Identifier(schema,table),sql.Identifier('public',table)))
                await conn.execute(sql.SQL('alter table {} enable row level security').format(sql.Identifier(schema,table)))
                await conn.execute(sql.SQL('revoke all on table {} from public,anon,authenticated').format(sql.Identifier(schema,table)))
            await conn.execute(sql.SQL('revoke all on schema {} from public,anon,authenticated').format(sql.Identifier(schema)))
        created=True
        frozen=seed_rows(10000,datetime.now(timezone.utc))
        # Replace synthetic assignees with real Auth subjects, preserving four buckets.
        from check_feedback_scale import ASSIGNEES
        for row in frozen:
            if row['assignee_id'] in ASSIGNEES[1:]:row['assignee_id']=users[ASSIGNEES[1:].index(row['assignee_id'])]
        async with plain() as conn:
            async with conn.cursor() as cursor:
                async with cursor.copy(sql.SQL('copy {} (id,user_id,rating,category,comment,client_submission_id,status,assignee_id,created_at) from stdin').format(sql.Identifier(schema,'beta_feedback'))) as copy:
                    for row in frozen:
                        await copy.write_row((row['id'],uuid4(),5,row['category'],'PRIVATE SOAK FIXTURE',row['id'],row['status'],row['assignee_id'],row['created_at']))
        app=FastAPI();app.include_router(routes.router) # no authentication dependency override
        routes.AdminFeedbackRepository=lambda:AdminFeedbackRepository(connect)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://isolated') as client:
            denied=await call(client,'GET','/admin/feedback')
            result['anonymous_denied']=denied.status_code==401
            cases=frozen_cases()
            for case in cases:
                if case['assignee'] not in [None,'unassigned']:
                    case['assignee']=users[0 if case['assignee']==str(ASSIGNEES[1]) else 1]
            start=time.monotonic()
            for number,case in enumerate(cases):
                async def query(actor):
                    started=time.perf_counter();row={'round':number,'actor':actor,'ok':False}
                    try:
                        response=await call(client,'GET','/admin/feedback',params={k:v for k,v in case.items() if v is not None},headers={'Authorization':'Bearer '+tokens[actor]})
                        row['status']=response.status_code
                        assert response.status_code==200
                        body=response.json();counts,matched=expected(frozen,case,datetime.fromisoformat(body['refreshed_at']))
                        assert body['counts']==counts
                        assert [item['id'] for item in body['items']]==[str(item['id']) for item in matched[case['offset']:case['offset']+20]]
                        assert body['has_more']==(len(matched)>case['offset']+20)
                        assert response.headers['cache-control']=='no-store'
                        row['ok']=True
                    except Exception as exc:row['error_type']=type(exc).__name__
                    row['ms']=round((time.perf_counter()-started)*1000,3)
                    return row
                result['requests'].extend(await asyncio.gather(*(query(actor) for actor in range(3))))
                persist()
                if number%10==9:print(json.dumps({'phase':'soak','completed_rounds':number+1,'seconds':round(time.monotonic()-start,1)}),flush=True)
                await asyncio.sleep(max(0,start+(number+1)*6-time.monotonic()))
            result['soak_seconds']=round(time.monotonic()-start,2)
            result['query_summary']=summarize(result['requests'])
            # Refresh all real login sessions, validate newly issued JWTs through same routes.
            refreshed=[]
            for actor in range(3):
                session=await asyncio.to_thread(service_api,'/auth/v1/token?grant_type=refresh_token','POST',{'refresh_token':refresh[actor]})
                tokens[actor]=session['access_token']
                response=await call(client,'GET','/admin/feedback',headers={'Authorization':'Bearer '+tokens[actor]})
                refreshed.append(response.status_code==200)
            result['token_refresh_passed']=all(refreshed)
            # Three actual JWT identities race for the same version, 100 independent rows.
            for number in range(100):
                fid=frozen[number]['id'];record={'round':number,'ok':False}
                try:
                    replies=await asyncio.gather(*(call(client,'PATCH','/admin/feedback/'+str(fid),headers={'Authorization':'Bearer '+tokens[actor]},json={'version':1,'status':'resolved','admin_note':'private real-session race','assignee_id':users[actor]}) for actor in range(3)))
                    record['statuses']=sorted(reply.status_code for reply in replies)
                    winner=next(actor for actor,reply in enumerate(replies) if reply.status_code==200)
                    async with plain() as conn:
                        rows=await(await conn.execute('select actor_auth_id,version from beta_feedback_history where feedback_id=%s',(fid,))).fetchall()
                    record['ok']=record['statuses']==[200,409,409] and len(rows)==1 and rows[0]['version']==2 and str(rows[0]['actor_auth_id'])==users[winner]
                except Exception as exc:record['error_type']=type(exc).__name__
                result['races'].append(record)
            for fault in ['closed_connection','statement_timeout','close_after_update']:
                rows=[]
                for number in range(100):
                    fid=frozen[1000+number]['id'];actor=number%3
                    record={'round':number,'ok':False};before=None
                    try:
                        async with plain() as conn:
                            before=await(await conn.execute('select version,status,admin_note,assignee_id from beta_feedback where id=%s',(fid,))).fetchone()
                            before_count=(await(await conn.execute('select count(*) as n from beta_feedback_history where feedback_id=%s',(fid,))).fetchone())['n']
                        body={'version':before['version'],'status':'resolved','admin_note':'private fault recovery'}
                        mode=fault
                        failed=await call(client,'PATCH','/admin/feedback/'+str(fid),headers={'Authorization':'Bearer '+tokens[actor]},json=body)
                        record['status']=failed.status_code
                        mode='normal'
                        async with plain() as conn:
                            after=await(await conn.execute('select version,status,admin_note,assignee_id from beta_feedback where id=%s',(fid,))).fetchone()
                            old_count=(await(await conn.execute('select count(*) as n from beta_feedback_history where feedback_id=%s',(fid,))).fetchone())['n']
                        record['unchanged']=before==after
                        record['audit_unchanged']=old_count==before_count
                        recovered=await call(client,'PATCH','/admin/feedback/'+str(fid),headers={'Authorization':'Bearer '+tokens[actor]},json=body)
                        record['recovery_status']=recovered.status_code
                        duplicate=await call(client,'PATCH','/admin/feedback/'+str(fid),headers={'Authorization':'Bearer '+tokens[actor]},json=body)
                        async with plain() as conn:
                            current=await(await conn.execute('select version from beta_feedback where id=%s',(fid,))).fetchone()
                            count=(await(await conn.execute('select count(*) as n from beta_feedback_history where feedback_id=%s',(fid,))).fetchone())['n']
                        record['audit_once']=count==before_count+1 and current['version']==before['version']+1 and duplicate.status_code==409
                        record['ok']=fault_passed(record)
                    except Exception as exc:record['error_type']=type(exc).__name__
                    finally:mode='normal'
                    rows.append(record)
                result['faults'][fault]={'planned':100,'passed':sum(row['ok'] for row in rows),'failed':100-sum(row['ok'] for row in rows),'rounds':rows}
                persist();print(json.dumps({'phase':fault,'passed':result['faults'][fault]['passed']}),flush=True)
    except Exception as exc:
        diagnostic(exc,'run')
    finally:
        settings.admin_emails=original_allowlist;routes.AdminFeedbackRepository=original_repo
        if created:
            try:
                assert schema.startswith('feedback_soak_') and len(schema)==46
                async with await AsyncConnection.connect(dsn,connect_timeout=10,options='-c statement_timeout=20000 -c lock_timeout=5000') as conn:
                    await conn.execute(sql.SQL('drop schema {} cascade').format(sql.Identifier(schema)))
                    result['cleanup']['schema_removed']=not await(await conn.execute('select 1 from pg_namespace where nspname=%s',(schema,))).fetchone()
            except Exception as exc:diagnostic(exc,'schema_cleanup')
        reconciled=False
        try:
            users=await asyncio.to_thread(reconcile_accounts,planned_emails,known_emails,
                lambda page:service_api('/auth/v1/admin/users?page='+str(page)+'&per_page=100')['users'])
            reconciled=True
        except Exception as exc:diagnostic(exc,'auth_reconciliation')
        deleted=0
        for uid in users:
            try:
                # Only IDs created in this invocation; no application profile or public feedback exists.
                await asyncio.to_thread(service_api,'/auth/v1/admin/users/'+uid,'DELETE')
                deleted+=1
            except Exception as exc:diagnostic(exc,'auth_cleanup')
        result['cleanup']['temporary_auth_users_removed']=reconciled and deleted==len(users)
        if result['cleanup'].get('schema_removed') and result['cleanup']['temporary_auth_users_removed']:ENV.unlink(missing_ok=True)
        result['passed']=bool(result.get('distinct_verified_sessions') and result.get('verified_subjects_match') and result.get('anonymous_denied') and result.get('token_refresh_passed') and result.get('soak_seconds',0)>=600 and len(result['requests'])==300 and all(row['ok'] for row in result['requests']) and len(result['races'])==100 and all(row['ok'] for row in result['races']) and len(result['faults'])==3 and all(value['passed']==100 for value in result['faults'].values()) and all(result['cleanup'].values()) and not result['diagnostics'])
        persist()
    print(json.dumps({'passed':result['passed'],'summary':result.get('query_summary'),'cleanup':result['cleanup'],'diagnostics':result['diagnostics']}),flush=True)
    return result['passed']


if __name__=='__main__':
    if sys.platform=='win32':asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    sys.exit(0 if asyncio.run(run()) else 1)
