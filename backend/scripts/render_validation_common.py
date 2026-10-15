"""Independent Render-only validation helpers. No production env fallback."""
import hashlib
import json
import math
import re
import statistics
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID, uuid5

import certifi
from dotenv import dotenv_values
from psycopg.conninfo import conninfo_to_dict

ROOT = Path(__file__).resolve().parents[2]
ENV = ROOT / 'backend/.env.render-validation'
TABLES = ['auth.users', 'public.users', 'public.beta_feedback', 'public.beta_feedback_history', 'public.validation_meta']


def validate_render_target(values):
    try:
        dbid = values['VALIDATION_DB_ID']
        name = values['VALIDATION_DB_NAME']
        db = conninfo_to_dict(values['VALIDATION_DB_URL'])
        UUID(values['VALIDATION_RUN_ID'])
        api = urlsplit(values['VALIDATION_API_URL'])
        safe_api = (api.scheme == 'https' and not api.username and not api.password
                    and api.port in (None, 443) and api.path in ('', '/') and not api.query and not api.fragment
                    and re.fullmatch(r'metadiet-api-validation(?:-[a-z0-9]+)?\.onrender\.com', api.hostname or ''))
    except Exception:
        raise ValueError('invalid_validation_configuration') from None
    if (values.get('ENVIRONMENT') != 'validation' or name != 'metadiet_validation'
            or not re.fullmatch(r'dpg-[a-z0-9]+-a', dbid) or not safe_api):
        raise ValueError('independent_render_target_required')
    host = db.get('host', '')
    if (host not in [dbid, dbid + '.singapore-postgres.render.com']
            or db.get('dbname') != name or db.get('hostaddr') or db.get('options')
            or db.get('port', '5432') != '5432' or not db.get('user') or not db.get('password')):
        raise ValueError('independent_render_database_required')
    return True


def load_values():
    if not ENV.is_file():
        raise ValueError('explicit_validation_env_required')
    values = dict(dotenv_values(ENV))
    validate_render_target(values)
    return values


def connection_options(values):
    validate_render_target(values)
    options = conninfo_to_dict(values['VALIDATION_DB_URL'])
    options.update(connect_timeout=10, sslmode='require', options='-c statement_timeout=15000 -c lock_timeout=5000')
    if options['host'].endswith('.render.com'):
        options.update(sslmode='verify-full', sslrootcert=certifi.where())
    return options


def summarize(rows, planned):
    times = sorted(row['ms'] for row in rows)
    passed = sum(bool(row['ok']) for row in rows)
    return {'planned': planned, 'attempts': len(rows), 'passed': passed,
            'failures': len(rows) - passed, 'not_attempted': max(0, planned - len(rows)),
            'median_ms': round(statistics.median(times), 2) if times else None,
            'p95_ms': round(times[math.ceil(len(times) * .95) - 1], 2) if times else None}


def actors(run_id):
    return [uuid5(UUID(run_id), 'admin-' + str(index)) for index in range(3)]


def fingerprint(conn):
    """Canonical data and constraint/index hashes, no row bodies in reports."""
    hashes = {}
    for table in TABLES:
        # TABLES is a source-controlled allowlist, never user input.
        rows = conn.execute(f'select row_to_json(t)::text from {table} t order by 1').fetchall()
        hashes[table] = {'rows': len(rows), 'sha256': hashlib.sha256('\n'.join(row[0] for row in rows).encode()).hexdigest()}
    schema = conn.execute("""select n.nspname,c.relname,k.conname,pg_get_constraintdef(k.oid)
        from pg_constraint k join pg_class c on c.oid=k.conrelid join pg_namespace n on n.oid=c.relnamespace
        where n.nspname in ('public','auth') order by 1,2,3""").fetchall()
    indexes = conn.execute("select schemaname,tablename,indexname,indexdef from pg_indexes where schemaname in ('public','auth') order by 1,2,3").fetchall()
    rls = conn.execute("""select n.nspname,c.relname,c.relrowsecurity,c.relforcerowsecurity
        from pg_class c join pg_namespace n on n.oid=c.relnamespace
        where c.relkind='r' and n.nspname in ('public','auth') order by 1,2""").fetchall()
    hashes['schema_sha256'] = hashlib.sha256(json.dumps([schema,indexes,rls],default=str).encode()).hexdigest()
    return hashes


def assert_identity(conn, values):
    if conn.execute('select current_database()').fetchone()[0] != values['VALIDATION_DB_NAME']:
        raise ValueError('database_identity_mismatch')
    rows = conn.execute('select run_id from public.validation_meta').fetchall()
    if len(rows) != 1 or str(rows[0][0]) != values['VALIDATION_RUN_ID']:
        raise ValueError('validation_marker_mismatch')
