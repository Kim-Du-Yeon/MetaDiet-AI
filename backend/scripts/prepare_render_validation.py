"""Initialize only the new disposable Render DB. Never loads backend/.env."""
import base64
import json
from datetime import datetime, timezone
from uuid import uuid4, uuid5, UUID
import secrets

from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from dotenv import dotenv_values
from psycopg import connect
from render_validation_common import ROOT, ENV, validate_render_target, connection_options, actors
from check_feedback_scale import seed_rows, ASSIGNEES


def run():
    values = dict(dotenv_values(ENV))
    values.update(ENVIRONMENT='validation', VALIDATION_API_URL='https://metadiet-api-validation.onrender.com',
                  VALIDATION_RUN_ID=values.get('VALIDATION_RUN_ID') or str(uuid4()))
    validate_render_target(values)
    if 'VALIDATION_PRIVATE_KEY' not in values:
        private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        values['VALIDATION_PRIVATE_KEY'] = base64.b64encode(pem).decode()
        numbers = private.public_key().public_numbers()
        encoded = lambda n: base64.urlsafe_b64encode(n.to_bytes((n.bit_length()+7)//8,'big')).rstrip(b'=').decode()
        values['VALIDATION_PUBLIC_JWK'] = json.dumps({'kty':'RSA','kid':values['VALIDATION_RUN_ID'], 'use':'sig','alg':'RS256','n':encoded(numbers.n),'e':encoded(numbers.e)},separators=(',',':'))
        values['SUPABASE_JWT_SECRET'] = secrets.token_urlsafe(48)
    values['ADMIN_EMAILS'] = ','.join('admin-'+str(i)+'@validation.invalid' for i in range(3))
    ENV.write_text('\n'.join(key+'='+value for key,value in values.items())+'\n',encoding='utf-8')
    with connect(**connection_options(values)) as conn:
        assert conn.execute('select current_database()').fetchone()[0] == 'metadiet_validation'
        if conn.execute("select to_regclass('public.validation_meta')").fetchone()[0]:
            raise ValueError('validation_database_already_initialized')
        assert conn.execute("select count(*) from pg_tables where schemaname='public'").fetchone()[0] == 0
        conn.execute('create schema auth')
        conn.execute('create table auth.users(id uuid primary key,email text not null unique,email_confirmed_at timestamptz not null)')
        conn.execute('create table public.users(id uuid primary key,auth_id uuid not null references auth.users(id))')
        for relative in ['backend/scripts/migrations/add_beta_feedback.sql',
                         'supabase/migrations/20261015014035_admin_feedback_workflow.sql',
                         'supabase/migrations/20261015022407_admin_feedback_assignment_history.sql']:
            source=(ROOT/relative).read_text(encoding='utf-8-sig').replace('begin;','').replace('commit;','')
            # Render has no Supabase API roles. Keep RLS and revoke PUBLIC instead.
            source=source.replace('from anon, authenticated','from public')
            conn.execute(source)
        conn.execute('create table public.validation_meta(run_id uuid primary key,created_at timestamptz not null)')
        conn.execute('insert into public.validation_meta values(%s,now())',(values['VALIDATION_RUN_ID'],))
        ids=actors(values['VALIDATION_RUN_ID'])
        for index,actor in enumerate(ids):
            conn.execute('insert into auth.users values(%s,%s,now())',(actor,'admin-'+str(index)+'@validation.invalid'))
        uid=uuid5(UUID(values['VALIDATION_RUN_ID']),'fixture-user')
        conn.execute('insert into public.users values(%s,%s)',(uid,ids[0]))
        rows=seed_rows(10000,datetime.now(timezone.utc))
        with conn.cursor().copy('copy beta_feedback(id,user_id,rating,category,comment,client_submission_id,status,assignee_id,created_at) from stdin') as copy:
            for row in rows:
                assignee=ids[ASSIGNEES[1:].index(row['assignee_id'])] if row['assignee_id'] else None
                copy.write_row((row['id'],uid,5,row['category'],'SYNTHETIC RENDER VALIDATION',row['id'],row['status'],assignee,row['created_at']))
    print(json.dumps({'prepared':True,'rows':10000,'admins':3,'production_touched':False}))


if __name__=='__main__':
    try:run()
    except Exception as exc:
        print(json.dumps({'failed':True,'error_type':type(exc).__name__,'sqlstate':getattr(exc,'sqlstate',None)}))
        raise SystemExit(1)
