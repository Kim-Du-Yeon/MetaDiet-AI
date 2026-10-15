"""Real PostgreSQL, private disposable schema; never seeds public feedback.

Run with the project venv. Uses the production repository and FastAPI router,
but synthetic administrator dependency identities, NOT public JWT validation.
Only counts/statuses/timings are exported. No opinions or credentials are logged.
"""
import argparse
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
import time
from uuid import UUID, uuid4, uuid5, NAMESPACE_URL

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from psycopg import AsyncConnection, sql
from psycopg.rows import dict_row

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
from app.db.admin_feedback import AdminFeedbackRepository, PENDING_STATUSES
from app.core.config import get_settings
from app.core.auth import get_current_admin
from app.api.routes import admin_feedback as routes

STATUSES=['received','reproducing','fixed','resolved','on_hold']
CATEGORIES=['general','answer_quality','evidence','usability','bug']
ACTORS=[uuid5(NAMESPACE_URL,'feedback-scale/admin-a'),uuid5(NAMESPACE_URL,'feedback-scale/admin-b')]
ASSIGNEES=[None,*ACTORS,uuid5(NAMESPACE_URL,'feedback-scale/former-admin')]


def frozen_cases():
    return [{'status':status,'category':category,'assignee':assignee,'offset':(index%3)*20,'limit':20}
            for index,(status,category,assignee) in enumerate(
                (s,c,a) for s in [None,'received','fixed','on_hold','resolved']
                for c in [None,'bug','usability','general','evidence']
                for a in [None,'unassigned',str(ACTORS[0]),str(ACTORS[1])])]


def summarize(rows):
    durations=sorted(row['ms'] for row in rows)
    passed=sum(bool(row['ok']) for row in rows)
    return {'attempts':len(rows),'passed':passed,'failed':len(rows)-passed,
            'failure_rate':(len(rows)-passed)/len(rows) if rows else None,
            'median_ms':round(statistics.median(durations),2) if rows else None,
            'p95_ms':round(durations[math.ceil(len(durations)*.95)-1],2) if rows else None}


def summarize_races(rows):
    passed=sum(bool(row['ok']) for row in rows)
    return {'planned_rounds':100,'completed_rounds':len(rows),'write_attempts':200,
            'passed':passed,'failed_rounds':100-passed,
            'timeout_rounds':sum(row.get('error_type')=='TimeoutError' for row in rows),
            'expected_conflicts':sum(row['http_statuses'].count(409) for row in rows)}


def seed_rows(size, now):
    rows=[]
    for index in range(size):
        rows.append({'id':uuid5(NAMESPACE_URL,f'feedback-scale/row/{index}'),
            'status':STATUSES[index%5],'category':CATEGORIES[(index//5)%5],
            'assignee_id':ASSIGNEES[(index//25)%4],
            'created_at':now-timedelta(days=[0,3,8,14][(index//100)%4],seconds=index)})
    return rows


def expected(rows, case, now):
    scoped=[row for row in rows if (not case['category'] or row['category']==case['category']) and
            (not case['assignee'] or (row['assignee_id'] is None if case['assignee']=='unassigned'
                                     else str(row['assignee_id'])==case['assignee']))]
    matched=[row for row in scoped if not case['status'] or row['status']==case['status']]
    matched.sort(key=lambda row:(row['created_at'],str(row['id'])),reverse=True)
    pending=lambda row: row['status'] in PENDING_STATUSES
    stale=lambda row: pending(row) and row['created_at']<=now-timedelta(days=7)
    return {'total_unprocessed':sum(map(pending,rows)),'unprocessed':sum(map(pending,scoped)),
            'total_stale':sum(map(stale,rows)),'stale':sum(map(stale,scoped)),'matched_total':len(matched)},matched


async def run(output):
    load_dotenv(ROOT/'backend/.env')
    dsn=get_settings().supabase_db_url
    schema='feedback_check_'+uuid4().hex
    result={'scope':'synthetic_private_postgres_and_in_process_api_not_public_latency',
            'dataset_sizes':[1000,10000],'cases_sha256':hashlib.sha256(json.dumps(frozen_cases(),sort_keys=True).encode()).hexdigest(),
            'authentication':'synthetic admin dependency; public JWT policy checked separately',
            'conditions':{},'races':[],'diagnostics':[],'stage':'setup','cleanup':False}
    @asynccontextmanager
    async def connect():
        try:
            async with await AsyncConnection.connect(dsn,row_factory=dict_row,connect_timeout=10,
                    options=f'-c search_path={schema},public') as conn:
                await conn.execute("set local statement_timeout='15s'")
                await conn.execute("set local lock_timeout='10s'")
                yield conn
        except Exception as exc:
            result['diagnostics'].append({'stage':result['stage'],'error_type':type(exc).__name__,
                                          'sqlstate':getattr(exc,'sqlstate',None)})
            raise
    original=routes.AdminFeedbackRepository
    app=FastAPI();app.include_router(routes.router)
    def admin(x_test_admin: str | None=Header(default=None)):
        if x_test_admin not in [str(actor) for actor in ACTORS]:
            raise HTTPException(401 if x_test_admin is None else 403,'test authorization denied')
        return x_test_admin
    app.dependency_overrides[get_current_admin]=admin
    created=False
    try:
        async with await AsyncConnection.connect(dsn,connect_timeout=10,
                options='-c statement_timeout=20000 -c lock_timeout=5000') as setup:
            await setup.execute(sql.SQL('create schema {}').format(sql.Identifier(schema)))
            created=True
            await setup.execute(sql.SQL('revoke all on schema {} from public, anon, authenticated').format(sql.Identifier(schema)))
            for table in ['beta_feedback','beta_feedback_history']:
                await setup.execute(sql.SQL('create table {} (like {} including all)').format(
                    sql.Identifier(schema,table),sql.Identifier('public',table)))
                await setup.execute(sql.SQL('revoke all on table {} from public, anon, authenticated').format(sql.Identifier(schema,table)))
                await setup.execute(sql.SQL('alter table {} enable row level security').format(sql.Identifier(schema,table)))
        routes.AdminFeedbackRepository=lambda:AdminFeedbackRepository(connect)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://synthetic',timeout=30) as client:
            for size in result['dataset_sizes']:
                result['stage']='scale_'+str(size)
                frozen=seed_rows(size,datetime.now(timezone.utc))
                async with connect() as conn:
                    await conn.execute(sql.SQL('truncate {},{}').format(sql.Identifier(schema,'beta_feedback_history'),sql.Identifier(schema,'beta_feedback')))
                    async with conn.cursor() as cursor:
                        async with cursor.copy(sql.SQL('copy {} (id,user_id,rating,category,comment,client_submission_id,status,assignee_id,created_at) from stdin').format(sql.Identifier(schema,'beta_feedback'))) as copy:
                            for row in frozen:
                                await copy.write_row((row['id'],uuid5(NAMESPACE_URL,'feedback-scale/user'),5,row['category'],
                                    'SYNTHETIC PRIVATE SCALE FIXTURE',row['id'],row['status'],row['assignee_id'],row['created_at']))
                measurements=[]
                for number,case in enumerate(frozen_cases()):
                    started=time.perf_counter();record={'case':number,'ok':False}
                    try:
                        response=await asyncio.wait_for(client.get('/admin/feedback',params={key:value for key,value in case.items() if value is not None},
                            headers={'x-test-admin':str(ACTORS[number%2])}),30)
                        record['status']=response.status_code
                        assert response.status_code==200
                        body=response.json();counts,matched=expected(frozen,case,datetime.fromisoformat(body['refreshed_at']))
                        assert body['counts']==counts
                        page=matched[case['offset']:case['offset']+case['limit']]
                        assert [row['id'] for row in body['items']]==[str(row['id']) for row in page]
                        assert body['has_more']==(len(matched)>case['offset']+case['limit'])
                        assert all(row['is_stale']==(row['status'] in PENDING_STATUSES and
                            datetime.fromisoformat(row['created_at'])<=datetime.fromisoformat(body['refreshed_at'])-timedelta(days=7)) for row in body['items'])
                        assert response.headers['cache-control']=='no-store'
                        record['ok']=True
                    except Exception as exc:
                        record['error_type']=type(exc).__name__
                    record['ms']=round((time.perf_counter()-started)*1000,3);measurements.append(record)
                result['conditions'][str(size)]={**summarize(measurements),'requests':measurements}
                output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
                print(json.dumps({'rows':size,**summarize(measurements)}),flush=True)
            # Same version, two different server-supplied identities, separate real connections.
            result['stage']='concurrency'
            for index in range(100):
                fid=uuid5(NAMESPACE_URL,f'feedback-scale/row/{index}')
                start=asyncio.Event()
                async def save(actor_index):
                    await start.wait()
                    return await client.patch('/admin/feedback/'+str(fid),headers={'x-test-admin':str(ACTORS[actor_index])},
                        json={'version':1,'status':['fixed','resolved'][actor_index],'admin_note':'synthetic race '+str(actor_index)})
                tasks=[asyncio.create_task(save(i)) for i in range(2)];start.set()
                record={'case':index,'http_statuses':[],'ok':False}
                try:
                    responses=await asyncio.wait_for(asyncio.gather(*tasks,return_exceptions=True),30)
                    codes=sorted(getattr(response,'status_code',0) for response in responses)
                    record['http_statuses']=codes
                    winner=next((i for i,response in enumerate(responses) if getattr(response,'status_code',0)==200),None)
                    async with connect() as conn:
                        row=await(await conn.execute('select version,updated_by,status from beta_feedback where id=%s',(fid,))).fetchone()
                        history=await(await conn.execute('select version,actor_auth_id,after_status from beta_feedback_history where feedback_id=%s',(fid,))).fetchall()
                        record['ok']=bool(codes==[200,409] and row['version']==2 and len(history)==1 and
                            history[0]['version']==2 and row['updated_by']==ACTORS[winner] and
                            history[0]['actor_auth_id']==ACTORS[winner] and history[0]['after_status']==row['status'])
                except Exception as exc:
                    record['error_type']=type(exc).__name__
                result['races'].append(record)
            result['concurrency']=summarize_races(result['races'])
            # Commit an update strictly between the list SELECT and count SELECT.
            result['stage']='snapshot'
            before=await AdminFeedbackRepository(connect).list()
            selected=asyncio.Event();committed=asyncio.Event()
            class PausedConnection:
                def __init__(self,conn):self.conn=conn
                async def execute(self,query,params=None):
                    cursor=await self.conn.execute(query,params)
                    if isinstance(query,str) and 'left(comment, 100)' in query:
                        selected.set();await asyncio.wait_for(committed.wait(),30)
                    return cursor
            @asynccontextmanager
            async def paused_connect():
                async with connect() as conn:yield PausedConnection(conn)
            async def reader():return await AdminFeedbackRepository(paused_connect).list()
            read_task=asyncio.create_task(reader())
            await asyncio.wait_for(selected.wait(),30)
            changed=await client.patch('/admin/feedback/'+str(uuid5(NAMESPACE_URL,'feedback-scale/row/500')),
                headers={'x-test-admin':str(ACTORS[0])},json={'version':1,'status':'resolved','admin_note':'snapshot check'})
            committed.set();during=await read_task
            after=await AdminFeedbackRepository(connect).list()
            result['snapshot']={'writer_success':changed.status_code==200,
                'same_response_keeps_snapshot':during['counts']==before['counts'],
                'next_refresh_sees_change':after['counts']['total_unprocessed']==before['counts']['total_unprocessed']-1}
    finally:
        routes.AdminFeedbackRepository=original
        if created:
            assert schema.startswith('feedback_check_') and len(schema)==47
            try:
                async with await AsyncConnection.connect(dsn,connect_timeout=10,
                        options='-c statement_timeout=20000 -c lock_timeout=5000') as cleanup:
                    await cleanup.execute(sql.SQL('drop schema if exists {} cascade').format(sql.Identifier(schema)))
                    assert not await(await cleanup.execute('select 1 from pg_namespace where nspname=%s',(schema,))).fetchone()
                result['cleanup']=True
            except Exception as exc:
                result['diagnostics'].append({'stage':'cleanup','error_type':type(exc).__name__,
                                              'sqlstate':getattr(exc,'sqlstate',None)})
        output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    passed=all(condition['failed']==0 for condition in result['conditions'].values()) and len(result['conditions'])==2
    passed=passed and result['concurrency']['passed']==100 and all(result['snapshot'].values()) and result['cleanup']
    print(json.dumps({'passed':passed,'concurrency':result['concurrency'],'snapshot':result['snapshot'],'private_schema_removed':result['cleanup']}))
    return passed


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=ROOT/'backend/artifacts/feedback-scale.json');args=parser.parse_args()
    if sys.platform=='win32':asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        sys.exit(0 if asyncio.run(run(args.output)) else 1)
    except Exception as exc:
        print(json.dumps({'failed':True,'error_type':type(exc).__name__}))
        sys.exit(1)
