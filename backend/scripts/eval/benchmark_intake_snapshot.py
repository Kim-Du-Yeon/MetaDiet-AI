"""Frozen 120 paired synthetic mutation flows, real isolated local PostgreSQL.

Only backend/.env.intake-validation is read. Never import production credentials
for DB access. HTTP request latency is an explicit synthetic parameter.
"""
import asyncio
from contextlib import asynccontextmanager
from datetime import timedelta
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import sys
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'backend'))
from dotenv import dotenv_values
import httpx
import psycopg
from psycopg.rows import dict_row
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.types.json import Jsonb

OWNER='11111111-1111-4111-8111-111111111111'
OTHER='22222222-2222-4222-8222-222222222222'
MEAL='33333333-3333-4333-8333-333333333333'
BASE='44444444-4444-4444-8444-444444444444'
THREAD='snapshot_eval'


def safe_dsn():
    value=dotenv_values(ROOT/'backend/.env.intake-validation')['INTAKE_VALIDATION_DB_URL']
    args=conninfo_to_dict(value)
    if args.get('host')!='127.0.0.1' or args.get('port')!='55439' or args.get('dbname')!='metadiet_intake_validation':
        raise ValueError('isolated_loopback_database_required')
    return value


def prepare(dsn):
    args=conninfo_to_dict(dsn)
    with psycopg.connect(make_conninfo(dsn,dbname='postgres'),autocommit=True) as conn:
        if not conn.execute('select 1 from pg_database where datname=%s',(args['dbname'],)).fetchone():
            conn.execute('create database metadiet_intake_validation')
    with psycopg.connect(dsn) as conn:
        conn.execute('create table if not exists users(id uuid primary key)')
        conn.execute('create table if not exists meal_logs(id uuid primary key,user_id uuid,log_date date,food_name text,meal_type text,quantity_g double precision,calories double precision,protein_g double precision,carbs_g double precision,fat_g double precision,sodium_mg double precision)')
        conn.execute('create table if not exists diet_strategies(user_id uuid,daily_calories double precision,is_active boolean,created_at timestamptz default now())')
        conn.execute('create table if not exists chat_history(user_id uuid,thread_id text,role text,content text,agent_type text,created_at timestamptz default now())')
        conn.execute('create table if not exists agent_proposals(user_id uuid,thread_id text,kind text,status text,payload jsonb,result jsonb,resolved_at timestamptz default now())')
        conn.execute('insert into users values(%s),(%s) on conflict do nothing',(OWNER,OTHER))
        conn.execute('delete from diet_strategies')
        conn.execute('insert into diet_strategies(user_id,daily_calories,is_active) values(%s,2000,true)',(OWNER,))


class Query:
    def __init__(self,dsn,table):
        assert table in {'meal_logs','diet_strategies','chat_history','agent_proposals'}
        self.dsn,self.table=dsn,table
        self.where=[]; self.values=[]; self.sort=[]; self.count=None; self.method='select'; self.payload=None
    def select(self,*args): return self
    def eq(self,key,value): self.where.append(key+'=%s'); self.values.append(value); return self
    def gte(self,key,value): self.where.append(key+'>=%s'); self.values.append(value); return self
    def lte(self,key,value): self.where.append(key+'<=%s'); self.values.append(value); return self
    def in_(self,key,value): self.where.append(key+'=any(%s::uuid[])'); self.values.append(value); return self
    def order(self,key,desc=False): self.sort.append(key+(' desc' if desc else ' asc')); return self
    def limit(self,value): self.count=int(value); return self
    def update(self,payload): self.method='update'; self.payload=payload; return self
    def delete(self): self.method='delete'; return self
    def execute(self):
        where=' where '+' and '.join(self.where) if self.where else ''
        values=list(self.values)
        if self.method=='select':
            sql='select * from '+self.table+where
            if self.sort: sql+=' order by '+','.join(self.sort)
            if self.count: sql+=' limit '+str(self.count)
        elif self.method=='delete': sql='delete from '+self.table+where+' returning *'
        else:
            sql='update '+self.table+' set '+','.join(k+'=%s' for k in self.payload)+where+' returning *'
            values=list(self.payload.values())+values
        with psycopg.connect(self.dsn,row_factory=dict_row) as conn:
            rows=conn.execute(sql,values).fetchall()
        # Same JSON values as PostgREST, no UUID/date/Decimal objects.
        return SimpleNamespace(data=json.loads(json.dumps(rows,default=str)))


def cases():
    return [dict(index=i,action='delete' if i%2 else 'update',past=i%4>=2,
                 fault='owner' if 100<=i<105 else 'stale' if 105<=i<110 else 'db' if 110<=i<115 else 'timeout' if i>=115 else None)
            for i in range(120)]


async def run(output):
    dsn=safe_dsn(); prepare(dsn)
    # Explicit non-production settings before importing application modules.
    os.environ.update(SUPABASE_URL='http://127.0.0.1:55439',SUPABASE_DB_URL=dsn,
        SUPABASE_SERVICE_KEY='isolated-test-placeholder',SUPABASE_JWT_SECRET='isolated-test-placeholder',
        GEMINI_API_KEY='isolated-test-placeholder',PINECONE_API_KEY='isolated-test-placeholder',
        LANGSMITH_TRACING='false',LANGCHAIN_TRACING_V2='false',FOOD_CATALOG_ENABLED='false')
    from app.api.routes import main
    from app.core.auth import get_current_user
    from app.core.service_clock import service_today
    from app.db import intake_snapshot
    from app.db.receipt_status import format_receipt
    from app.db.proposals import ProposalRepository
    today=service_today().isoformat()
    past=(service_today().replace(day=1)-timedelta(days=1)).isoformat()
    latency_ms=35
    mode={'fault':None}
    @asynccontextmanager
    async def connect():
        async with await psycopg.AsyncConnection.connect(dsn,row_factory=dict_row) as conn:
            await conn.execute("set local statement_timeout='3s'")
            if mode['fault']=='db':
                # Rollback is tested after a write, not merely a failed connection.
                real_execute=conn.execute
                async def execute(sql,*args,**kwargs):
                    if sql.startswith('select * from meal_logs where user_id='):
                        raise psycopg.OperationalError('injected_read_failure')
                    return await real_execute(sql,*args,**kwargs)
                conn.execute=execute
            yield conn
    intake_snapshot.connection=connect
    main.sb=SimpleNamespace(table=lambda name:Query(dsn,name))
    ProposalRepository.latest_pending=AsyncMock(return_value=None)
    main.get_graph=lambda:SimpleNamespace(aget_state=AsyncMock(return_value=SimpleNamespace(values={},next=())))
    main.app.dependency_overrides[get_current_user]=lambda:OWNER
    async def stats(_user):
        with psycopg.connect(dsn) as conn:
            total=conn.execute('select coalesce(sum(calories),0) from meal_logs where user_id=%s and log_date=%s',(OWNER,today)).fetchone()[0]
        return {'today_calories':total,'target_calories':2000}
    main._public_stats=stats
    attempts=[]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url='http://isolated') as client:
        # Alternate condition order by case to reduce run-order bias.
        for case in cases():
            for condition in (['before','after'] if case['index']%2==0 else ['after','before']):
                selected=past if case['past'] else today
                meal=dict(id=MEAL,user_id=OWNER,log_date=selected,food_name='밥',meal_type='lunch',quantity_g=10,
                          calories=15,protein_g=.3,carbs_g=3,fat_g=.1,sodium_mg=0)
                proposal={'payload':{'log_date':selected,'meals':[meal]},'result':{'meal_ids':[MEAL]}}
                with psycopg.connect(dsn) as conn:
                    for table in ('meal_logs','chat_history','agent_proposals'): conn.execute('delete from '+table)
                    conn.execute('insert into meal_logs values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',tuple(meal.values()))
                    conn.execute('insert into meal_logs values(%s,%s,%s,%s,%s,100,100,10,10,2,0)',(BASE,OWNER,today,'기존 음식','breakfast'))
                    conn.execute('insert into chat_history(user_id,thread_id,role,content,agent_type) values(%s,%s,%s,%s,%s)',(OWNER,THREAD,'assistant',format_receipt(proposal),'confirm'))
                    conn.execute("insert into agent_proposals(user_id,thread_id,kind,status,payload,result) values(%s,%s,'intake','confirmed',%s,%s)",(OWNER,THREAD,Jsonb(proposal['payload']),Jsonb(proposal['result'])))
                    if case['fault']=='owner': conn.execute('update meal_logs set user_id=%s where id=%s',(OTHER,MEAL))
                version=intake_snapshot.record_version(meal)
                options={'include_snapshot':condition=='after','selected_date':selected,'thread_id':THREAD,
                         'expected_record_version':'0'*64 if case['fault']=='stale' else version}
                mode['fault']=case['fault']
                requests=0; status=None; coherent=False; error=None
                started=time.perf_counter()
                async def request(method,path,**kwargs):
                    nonlocal requests
                    requests+=1
                    await asyncio.sleep(latency_ms/1000)
                    if case['fault']=='timeout': raise httpx.ReadTimeout('injected_timeout')
                    return await client.request(method,path,**kwargs)
                try:
                    response=await (request('DELETE','/meal/delete/'+MEAL,params=options) if case['action']=='delete'
                                    else request('PUT','/meal/update',json={'meal_id':MEAL,'quantity_g':20,**options}))
                    status=response.status_code
                    if response.is_success:
                        if condition=='after': snapshot=response.json()['sync']
                        else:
                            day,month=await asyncio.gather(request('GET','/calendar/'+selected),request('GET','/calendar/month/'+selected[:7]))
                            if case['fault']=='db': raise psycopg.OperationalError('injected_read_failure')
                            restored=await request('GET','/session/restore/'+THREAD)
                            snapshot={**restored.json(),'calendar':day.json(),'calendar_month':month.json()}
                        expected_today=100+(0 if case['past'] or case['action']=='delete' else 30)
                        day_expected=(0 if case['action']=='delete' else 30)+(0 if case['past'] else 100)
                        notice='삭제된' if case['action']=='delete' else '수정된'
                        coherent=(snapshot['today_calories']==expected_today
                                  and snapshot['calendar']['total']['calories']==day_expected
                                  and any(notice in m['content'] for m in snapshot.get('messages',[])))
                    elif case['fault']=='owner': coherent=status==403
                    elif case['fault']=='stale': coherent=status==409
                    elif case['fault']=='db': coherent=status==503
                except Exception as exc:
                    error=type(exc).__name__
                elapsed=(time.perf_counter()-started)*1000
                with psycopg.connect(dsn) as conn:
                    base=conn.execute('select quantity_g,calories from meal_logs where id=%s',(BASE,)).fetchone()
                    row=conn.execute('select quantity_g from meal_logs where id=%s',(MEAL,)).fetchone()
                preserved=base==(100,100)
                if case['fault'] in ('owner','stale','db','timeout'):
                    coherent=coherent and row==(10,)
                attempts.append({**case,'condition':condition,'elapsed_ms':round(elapsed,3),'requests':requests,
                    'status':status,'error_type':error,'coherent':coherent,'existing_preserved':preserved})
    summaries={}
    for condition in ('before','after'):
        rows=[r for r in attempts if r['condition']==condition]
        values=sorted(r['elapsed_ms'] for r in rows)
        summaries[condition]={'attempts':len(rows),'coherent':sum(r['coherent'] for r in rows),
            'existing_preserved':sum(r['existing_preserved'] for r in rows),
            'failures_or_timeouts':sum(bool(r['error_type']) or r['status']==503 for r in rows),
            'p50_ms':round(statistics.median(values),3),'p95_ms':values[math.ceil(.95*len(values))-1],
            'normal_requests':sorted(set(r['requests'] for r in rows if r['fault'] is None))}
    output.mkdir(parents=True,exist_ok=True)
    frozen=cases()
    report={'environment':'synthetic ASGI + isolated local PostgreSQL, no production data',
        'http_latency_injected_ms':latency_ms,'cases_sha256':hashlib.sha256(json.dumps(frozen,sort_keys=True).encode()).hexdigest(),
        'summary':summaries,'attempts':attempts}
    (output/'cases.json').write_text(json.dumps(frozen,indent=2)+'\n')
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(summaries))
    healthy=[r for r in attempts if r['condition']=='after' and r['fault'] is None]
    if (summaries['after']['coherent']!=115 or summaries['after']['existing_preserved']!=120
            or sum(r['coherent'] for r in healthy)!=100
            or summaries['after']['p95_ms']>=summaries['before']['p95_ms']):
        raise SystemExit(1)


if __name__=='__main__':
    if sys.platform=='win32': asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run(ROOT/'docs/food_catalog/intake-snapshot-20261019'))
