"""Offline configuration guard only. Never connects, deploys, restarts or restores."""
import argparse
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from dotenv import dotenv_values
from psycopg.conninfo import conninfo_to_dict

EXISTING_PROJECTS={'xznckgjdruxowbgzqamd','cxjglgodsdymrseuyett'}


def validate_configuration(values):
    def required(key):
        value=str(values.get(key) or '').strip()
        if not value:raise ValueError('missing_'+key.lower())
        return value
    ref=required('VALIDATION_PROJECT_REF')
    if not re.fullmatch('[a-z]{20}',ref) or ref in EXISTING_PROJECTS:
        raise ValueError('independent_project_required')
    try:
        api=urlsplit(required('VALIDATION_API_URL'))
        api_port=api.port
        auth=urlsplit(required('SUPABASE_URL'))
    except ValueError:raise ValueError('invalid_target_url') from None
    if (api.scheme!='https' or not re.fullmatch(r'metadiet-api-validation(?:-[a-z0-9]+)?\.onrender\.com',api.hostname or '')
            or api.username or api.password or api_port not in (None,443)
            or api.path not in ('','/') or api.query or api.fragment):
        raise ValueError('independent_render_service_required')
    if (auth.scheme!='https' or auth.netloc!=ref+'.supabase.co' or auth.path not in ('','/')
            or auth.query or auth.fragment):
        raise ValueError('independent_auth_project_required')
    raw_dsn=required('SUPABASE_DB_URL')
    if any(existing in raw_dsn for existing in EXISTING_PROJECTS):
        raise ValueError('existing_database_forbidden')
    try:db=conninfo_to_dict(raw_dsn)
    except Exception:raise ValueError('invalid_database_configuration') from None
    direct=db.get('host')=='db.'+ref+'.supabase.co' and db.get('user')=='postgres'
    pooled=(bool(re.fullmatch(r'[a-z0-9-]+\.pooler\.supabase\.com',db.get('host','')))
            and db.get('user')=='postgres.'+ref)
    if not (direct or pooled) or db.get('dbname')!='postgres' or db.get('hostaddr'):
        raise ValueError('database_project_mismatch')
    for key,expected in [('ENABLE_SCHEDULER','false'),('ENVIRONMENT','validation'),
                         ('LANGSMITH_TRACING','false'),('VALIDATION_SYNTHETIC_ONLY','true')]:
        if required(key)!=expected:raise ValueError('unsafe_'+key.lower())
    try:
        duration=int(required('VALIDATION_DURATION_SECONDS'))
        sessions=int(required('VALIDATION_SESSIONS'))
        interval=int(required('VALIDATION_INTERVAL_SECONDS'))
    except ValueError:raise ValueError('invalid_load_configuration') from None
    if not 7200<=duration<=86400 or not 1<=sessions<=10 or interval<5:
        raise ValueError('invalid_load_bounds')
    attempts=duration//interval
    if attempts<100 or attempts*sessions>60000:raise ValueError('invalid_attempt_count')
    return {'configuration_only':True,'remote_identity_verified':False,
            'duration_seconds':duration,'sessions':sessions,'interval_seconds':interval,
            'planned_requests_per_session':attempts,'planned_requests_total':attempts*sessions,
            'destructive_operations_enabled':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file',type=Path,required=True)
    args=parser.parse_args()
    if not args.env_file.is_file():
        print(json.dumps({'configuration_valid':False,'reason':'explicit_validation_env_required'}))
        raise SystemExit(2)
    try:
        result=validate_configuration(dotenv_values(args.env_file))
    except ValueError as exc:
        # Only our fixed reason codes, never connection strings or credentials.
        print(json.dumps({'configuration_valid':False,'reason':str(exc)}))
        raise SystemExit(2)
    print(json.dumps({'configuration_valid':True,**result}))
