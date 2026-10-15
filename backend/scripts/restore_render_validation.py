"""Direct logical backup and restore ONLY on the disposable marked Render DB.

No production credentials are loaded; passwords are child environment variables,
never pg_dump/pg_restore command arguments or published error messages.
"""
import hashlib
import json
import os
import subprocess
import time

import certifi
import httpx
from psycopg import connect
from psycopg.conninfo import conninfo_to_dict

from render_validation_common import ROOT, load_values, connection_options, assert_identity, fingerprint, summarize
from run_render_free_soak import signed_tokens

OUTPUT=ROOT/'backend/artifacts/render-free-restore.json'
ARCHIVE=ROOT/'backend/artifacts/render-free-backup.dump'
CLIENTS=ROOT/'tmp/validation-tools/postgresql17/pgsql/bin'


def run():
    values=load_values();options=connection_options(values)
    result={'scope':'manual_logical_backup_disposable_Render_Postgres_not_managed_PITR',
            'passed':False,'diagnostics':[],'post_restore_requests':[]}
    def persist():
        OUTPUT.parent.mkdir(parents=True,exist_ok=True)
        OUTPUT.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    try:
        with connect(**options) as conn:
            assert_identity(conn,values)
            result['before']=fingerprint(conn)
        db=conninfo_to_dict(values['VALIDATION_DB_URL'])
        child_env={**os.environ,'PGHOST':db['host'],'PGPORT':db.get('port','5432'),
                   'PGUSER':db['user'],'PGPASSWORD':db['password'],'PGDATABASE':db['dbname'],
                   'PGSSLMODE':'verify-full','PGSSLROOTCERT':certifi.where(),'PGCONNECT_TIMEOUT':'10'}
        # Capture stderr privately; publish only return codes/type, no DSNs.
        command=[str(CLIENTS/'pg_dump.exe'),'--format=custom','--schema=public','--schema=auth',
                 '--no-owner','--no-acl','--file='+str(ARCHIVE)]
        completed=subprocess.run(command,env=child_env,capture_output=True,timeout=120)
        result['dump_exit']=completed.returncode
        if completed.returncode:
            (ROOT/'backend/artifacts/render-free-dump-error.log').write_bytes(completed.stderr)
            raise RuntimeError('pg_dump_failed')
        result['archive_sha256']=hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()
        result['archive_bytes']=ARCHIVE.stat().st_size
        # An intact archive and a final independent DB identity check precede loss.
        listing=subprocess.run([str(CLIENTS/'pg_restore.exe'),'--list',str(ARCHIVE)],env=child_env,capture_output=True,timeout=20)
        if listing.returncode:raise RuntimeError('invalid_backup_archive')
        with connect(**options) as conn:
            assert_identity(conn,values)
            if fingerprint(conn)!=result['before']:raise RuntimeError('database_changed_during_backup')
            candidate=conn.execute('select id from public.beta_feedback order by id limit 1').fetchone()[0]
            removed=conn.execute("delete from public.beta_feedback where id=%s and comment='SYNTHETIC RENDER VALIDATION'",(candidate,))
            if removed.rowcount!=1:raise RuntimeError('fixture_only_delete_failed')
        with connect(**options) as conn:
            result['loss_detected']=fingerprint(conn)!=result['before']
        if not result['loss_detected']:raise RuntimeError('loss_not_observed')
        began=time.perf_counter()
        completed=subprocess.run([str(CLIENTS/'pg_restore.exe'),'--clean','--if-exists','--no-owner','--no-acl',
                                  '--single-transaction','--dbname='+db['dbname'],str(ARCHIVE)],
                                 env=child_env,capture_output=True,timeout=120)
        result['restore_exit']=completed.returncode
        result['restore_command_ms']=round((time.perf_counter()-began)*1000,3)
        if completed.returncode:
            (ROOT/'backend/artifacts/render-free-restore-error.log').write_bytes(completed.stderr)
            raise RuntimeError('pg_restore_failed')
        with connect(**options) as conn:
            assert_identity(conn,values)
            result['after']=fingerprint(conn)
        result['data_constraints_indexes_rls_match']=result['before']==result['after']
        token=signed_tokens(values)[0]
        with httpx.Client(base_url=values['VALIDATION_API_URL'],timeout=20) as client:
            health=client.get('/health');health.raise_for_status()
            if health.json().get('run_id')!=values['VALIDATION_RUN_ID']:
                raise RuntimeError('remote_identity_mismatch')
            result['unauthenticated_status']=client.get('/admin/feedback').status_code
            for index in range(100):
                started=time.perf_counter();row={'case':index,'ok':False}
                try:
                    response=client.get('/admin/feedback',params={'offset':(index%3)*20,'limit':20},
                                        headers={'Authorization':'Bearer '+token})
                    row['status']=response.status_code
                    if response.status_code==200:
                        body=response.json()
                        row['ok']=len(body['items'])==20 and body['counts']['matched_total']==10000
                except Exception as exc:row['error_type']=type(exc).__name__
                row['ms']=round((time.perf_counter()-started)*1000,3)
                result['post_restore_requests'].append(row)
            # Verify restored version/audit semantics through the deployed API.
            fid=str(candidate)
            headers={'Authorization':'Bearer '+token}
            detail=client.get('/admin/feedback/'+fid,headers=headers);detail.raise_for_status()
            original=detail.json()
            previous=client.get('/admin/feedback/'+fid+'/history',headers=headers);previous.raise_for_status()
            version=original['version']
            update={'version':version,'status':'resolved','admin_note':'synthetic post-restore write'}
            saved=client.patch('/admin/feedback/'+fid,headers=headers,json=update)
            duplicate=client.patch('/admin/feedback/'+fid,headers=headers,json=update)
            history=client.get('/admin/feedback/'+fid+'/history',headers=headers);history.raise_for_status()
            result['post_restore_write']={'saved_status':saved.status_code,'duplicate_status':duplicate.status_code,
                'history_added':len(history.json()['items'])-len(previous.json()['items']),
                'version_advanced':saved.status_code==200 and saved.json()['version']==version+1}
        result['summary']=summarize(result['post_restore_requests'],100)
        result['passed']=bool(result['data_constraints_indexes_rls_match'] and result['summary']['passed']==100
                              and result['unauthenticated_status']==401
                              and result['post_restore_write']=={'saved_status':200,'duplicate_status':409,
                                  'history_added':1,'version_advanced':True})
    except Exception as exc:
        result['diagnostics'].append({'error_type':type(exc).__name__,'sqlstate':getattr(exc,'sqlstate',None)})
    finally:persist()
    print(json.dumps({'passed':result['passed'],'data_match':result.get('data_constraints_indexes_rls_match'),
                      'summary':result.get('summary'),'diagnostics':result['diagnostics']}),flush=True)
    return result['passed']


if __name__=='__main__':
    raise SystemExit(0 if run() else 1)
