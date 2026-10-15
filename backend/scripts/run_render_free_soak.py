"""Two-hour HTTPS feedback soak on the independent free Render service.

An operator restarts ONLY the validation DB when restart_requested becomes true.
Failed requests stay in the artifact. No production endpoints or keys are loaded.
"""
import asyncio
import base64
from contextlib import AsyncExitStack
from datetime import datetime, timezone
import json
import sys
import time

import httpx
import jwt
from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg import connect

from render_validation_common import ROOT, load_values, connection_options, actors, summarize, assert_identity
from check_feedback_scale import frozen_cases, expected, ASSIGNEES

ARTIFACT=ROOT/'backend/artifacts/render-free-soak.json'


def signed_tokens(values):
    key=base64.b64decode(values['VALIDATION_PRIVATE_KEY'])
    return [jwt.encode({'sub':str(actor),'email':'admin-'+str(index)+'@validation.invalid',
                        'aud':'authenticated','iss':'metadiet-independent-validation',
                        'session_id':str(actor),'iat':int(time.time()),'exp':int(time.time())+21600},
                       key,algorithm='RS256',headers={'kid':values['VALIDATION_RUN_ID']})
            for index,actor in enumerate(actors(values['VALIDATION_RUN_ID']))]


async def run():
    values=load_values();options=connection_options(values)
    duration=int(values['VALIDATION_DURATION_SECONDS']);interval=int(values['VALIDATION_INTERVAL_SECONDS'])
    if (duration<7200 or interval<5 or duration//interval<100 or duration>14400
            or duration % interval or int(values['VALIDATION_SESSIONS']) != 3):
        raise ValueError('unsafe_soak_bounds')
    rounds=duration//interval;ids=actors(values['VALIDATION_RUN_ID']);tokens=signed_tokens(values)
    cases=frozen_cases()
    for case in cases:
        if case['assignee'] not in (None,'unassigned'):
            case['assignee']=str(ids[0 if case['assignee']==str(ASSIGNEES[1]) else 1])
    with connect(**options) as conn:
        assert_identity(conn,values)
        from psycopg.rows import dict_row as row_factory
        frozen=conn.cursor(row_factory=row_factory).execute('select id,status,category,assignee_id,created_at from beta_feedback').fetchall()
        if len(frozen)!=10000:raise ValueError('fixture_row_count_mismatch')
    result={'scope':'free_Render_HTTPS_real_Postgres_synthetic_RSA_auth_not_Supabase',
            'duration_seconds':duration,'interval_seconds':interval,'sessions':3,
            'started_at_utc':datetime.now(timezone.utc).isoformat(),
            'requests':[],'health_checks':[],'races':[],'diagnostics':[],
            'restart_requested':False,'restart_observed':False,'passed':False}
    def persist():
        ARTIFACT.parent.mkdir(parents=True,exist_ok=True)
        ARTIFACT.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    start=time.monotonic()
    async with AsyncExitStack() as stack:
        client=await stack.enter_async_context(httpx.AsyncClient(base_url=values['VALIDATION_API_URL'],timeout=20))
        initial=(await client.get('/health',timeout=90));initial.raise_for_status();initial=initial.json()
        assert initial['run_id']==values['VALIDATION_RUN_ID'] and initial['validation_only'] is True
        result['deployment_commit']=initial['commit'];result['initial_database_started_at']=initial['database_started_at']
        persistent=await stack.enter_async_context(await AsyncConnection.connect(**options,autocommit=True))
        await persistent.execute('select 1')
        start=time.monotonic()
        result['measurement_started_at_utc']=datetime.now(timezone.utc).isoformat()
        try:
            for number in range(rounds):
                elapsed=time.monotonic()-start
                if elapsed>=duration/2 and not result['restart_requested']:
                    result['restart_requested']=True;result['restart_requested_elapsed']=round(elapsed,3)
                    persist();print(json.dumps({'phase':'restart_requested','seconds':round(elapsed,1)}),flush=True)
                case=cases[number%100]
                async def query(actor):
                    began=time.perf_counter();row={'round':number,'actor':actor,'elapsed':round(time.monotonic()-start,3),
                                                  'phase':'after_restart' if result['restart_observed'] else 'before_restart','ok':False}
                    try:
                        response=await client.get('/admin/feedback',params={k:v for k,v in case.items() if v is not None},
                                                  headers={'Authorization':'Bearer '+tokens[actor]})
                        row['status']=response.status_code
                        if response.status_code==200:
                            body=response.json();counts,matched=expected(frozen,case,datetime.fromisoformat(body['refreshed_at']))
                            row['ok']=(body['counts']==counts and [item['id'] for item in body['items']]==
                                       [str(item['id']) for item in matched[case['offset']:case['offset']+20]]
                                       and body['has_more']==(len(matched)>case['offset']+20)
                                       and response.headers.get('cache-control')=='no-store')
                    except Exception as exc:row['error_type']=type(exc).__name__
                    row['ms']=round((time.perf_counter()-began)*1000,3)
                    return row
                result['requests'].extend(await asyncio.gather(*(query(actor) for actor in range(3))))
                if number%2==0:
                    check={'elapsed':round(time.monotonic()-start,3),'ok':False}
                    try:
                        response=await client.get('/health');check['status']=response.status_code
                        if response.status_code==200:
                            body=response.json()
                            check['ok']=body['run_id']==values['VALIDATION_RUN_ID'] and body['commit']==result['deployment_commit']
                            if not check['ok']:
                                result['diagnostics'].append({'error_type':'remote_identity_or_commit_changed'})
                            if check['ok'] and body['database_started_at']!=result['initial_database_started_at'] and not result['restart_observed']:
                                result['restart_observed']=True
                                result['restart_observed_elapsed']=round(time.monotonic()-start,3)
                                result['new_database_started_at']=body['database_started_at']
                                try:
                                    await persistent.execute('select 1')
                                    result['existing_connection_failed_after_restart']=False
                                except Exception as exc:
                                    result['existing_connection_failed_after_restart']=True
                                    result['old_connection_error_type']=type(exc).__name__
                                print(json.dumps({'phase':'restart_observed','seconds':result['restart_observed_elapsed']}),flush=True)
                    except Exception as exc:check['error_type']=type(exc).__name__
                    result['health_checks'].append(check)
                persist()
                if number%10==9:print(json.dumps({'phase':'soak','rounds':number+1,'attempts':len(result['requests']),'failures':sum(not row['ok'] for row in result['requests'])}),flush=True)
                await asyncio.sleep(max(0,start+(number+1)*interval-time.monotonic()))
            result['observed_seconds']=round(time.monotonic()-start,3)
            # Real three-JWT races use production SQL after the frozen read phase.
            for number in range(100):
                fid=str(frozen[number]['id']);row={'case':number,'ok':False}
                try:
                    responses=await asyncio.gather(*(client.patch('/admin/feedback/'+fid,headers={'Authorization':'Bearer '+tokens[actor]},
                        json={'version':1,'status':'resolved','admin_note':'synthetic Render race','assignee_id':str(ids[actor])}) for actor in range(3)))
                    row['statuses']=sorted(response.status_code for response in responses)
                    winner=next(i for i,response in enumerate(responses) if response.status_code==200)
                    with connect(**options) as conn:
                        assert_identity(conn,values)
                        history=conn.execute('select version,actor_auth_id from beta_feedback_history where feedback_id=%s',(fid,)).fetchall()
                    row['ok']=row['statuses']==[200,409,409] and len(history)==1 and history[0][0]==2 and history[0][1]==ids[winner]
                except Exception as exc:row['error_type']=type(exc).__name__
                result['races'].append(row)
                persist()
        except Exception as exc:
            result['diagnostics'].append({'error_type':type(exc).__name__})
        finally:
            result['summary']=summarize(result['requests'],planned=rounds*3)
            for phase in ['before_restart','after_restart']:
                result[phase]=summarize([row for row in result['requests'] if row['phase']==phase],planned=rounds*3//2)
            outage_start=result.get('restart_requested_elapsed',duration+1)
            outage_end=min(result.get('restart_observed_elapsed',-100)+60,outage_start+600)
            transport_errors={'ReadTimeout','ConnectTimeout','ReadError','ConnectError','RemoteProtocolError'}
            def expected_outage(row):
                return (result['restart_observed'] and outage_start<=row['elapsed']<=outage_end and
                        (row.get('status') in [502,503,504] or row.get('error_type') in transport_errors))
            failures=[row for row in result['requests'] if not row['ok']]
            result['expected_outage_failures']=sum(expected_outage(row) for row in failures)
            result['unexpected_failures']=len(failures)-result['expected_outage_failures']
            result['passed']=bool(result.get('observed_seconds',0)>=duration and len(result['requests'])==rounds*3
                and result['restart_observed'] and result.get('existing_connection_failed_after_restart')
                and result['before_restart']['attempts']>=100 and result['after_restart']['attempts']>=100
                and result['unexpected_failures']==0 and len(result['races'])==100 and all(row['ok'] for row in result['races'])
                and not result['diagnostics'])
            persist()
    print(json.dumps({'passed':result['passed'],'summary':result['summary'],'restart_observed':result['restart_observed']}),flush=True)
    return result['passed']


if __name__=='__main__':
    if sys.platform=='win32':asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:passed=asyncio.run(run())
    except Exception as exc:
        print(json.dumps({'failed':True,'error_type':type(exc).__name__}));passed=False
    sys.exit(0 if passed else 1)
