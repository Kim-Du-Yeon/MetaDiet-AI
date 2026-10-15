import importlib.util
from pathlib import Path
import sys
import pytest


def common():
    scripts=Path(__file__).resolve().parents[2]/'scripts'
    sys.path.insert(0,str(scripts))
    spec=importlib.util.spec_from_file_location('render_validation_common',scripts/'render_validation_common.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def values():
    return {'VALIDATION_DB_ID':'dpg-testvalidation-a','VALIDATION_DB_NAME':'metadiet_validation',
            'VALIDATION_DB_URL':'postgresql://fixture:fixture@dpg-testvalidation-a.singapore-postgres.render.com/metadiet_validation',
            'VALIDATION_RUN_ID':'ac5d2203-5a97-4bc8-9364-d6a30e013e9a',
            'ENVIRONMENT':'validation','VALIDATION_API_URL':'https://metadiet-api-validation.onrender.com'}


@pytest.mark.parametrize('key,value',[
 ('VALIDATION_DB_URL','postgresql://postgres:fixture@db.xznckgjdruxowbgzqamd.supabase.co/postgres'),
 ('VALIDATION_DB_URL','postgresql://fixture:fixture@unrelated.render.com/metadiet_validation'),
 ('VALIDATION_DB_NAME','postgres'),('ENVIRONMENT','beta'),
 ('VALIDATION_API_URL','https://metadiet-api.onrender.com')])
def test_never_targets_existing_resources(key,value):
    v=values();v[key]=value
    with pytest.raises(ValueError):common().validate_render_target(v)


def test_all_failure_and_missing_attempts_remain_visible():
    module=common();assert module.validate_render_target(values())
    s=module.summarize([{'ok':True,'ms':1},{'ok':False,'ms':100,'status':503}],planned=3)
    assert s['attempts']==2 and s['failures']==1 and s['not_attempted']==1
    assert s['passed']==1 and s['p95_ms']==100


def test_validation_app_keeps_signature_and_admin_authorization(monkeypatch):
    import json,time
    from types import SimpleNamespace
    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    from fastapi.testclient import TestClient
    from jwt.algorithms import RSAAlgorithm
    import app.core.auth as auth
    from app.api.routes import admin_feedback as routes
    import render_validation_app
    private=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    public=json.loads(RSAAlgorithm.to_jwk(private.public_key()));public.update(kid='fixture',alg='RS256',use='sig')
    for key,value in values().items():monkeypatch.setenv(key,value)
    monkeypatch.setenv('VALIDATION_PUBLIC_JWK',json.dumps(public))
    monkeypatch.setenv('SUPABASE_JWT_SECRET','random-fixture-fallback-key')
    settings=SimpleNamespace(admin_emails='admin@validation.invalid',supabase_jwt_secret='random-fixture-fallback-key')
    monkeypatch.setattr(auth,'get_settings',lambda:settings)
    class JWKS:
        def get_signing_key_from_jwt(self,token):return jwt.PyJWK.from_dict(public)
    monkeypatch.setattr(auth,'_get_jwks_client',lambda:JWKS())
    class Repository:
        async def list(self,**kwargs):return {'items':[]}
    monkeypatch.setattr(routes,'AdminFeedbackRepository',Repository)
    pem=private.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())
    def token(email,expired=False):return jwt.encode({'sub':'fixture-user','email':email,'aud':'authenticated','exp':time.time()+(-10 if expired else 60)},pem,algorithm='RS256',headers={'kid':'fixture'})
    with TestClient(render_validation_app.create_app()) as client:
        assert client.get('/admin/feedback').status_code==401
        assert client.get('/admin/feedback',headers={'Authorization':'Bearer '+token('member@validation.invalid')}).status_code==403
        assert client.get('/admin/feedback',headers={'Authorization':'Bearer '+token('admin@validation.invalid',True)}).status_code==401
        response=client.get('/admin/feedback',headers={'Authorization':'Bearer '+token('admin@validation.invalid')})
        assert response.status_code==200 and response.headers['cache-control']=='no-store'
        assert 'd' not in client.get('/auth/v1/.well-known/jwks.json').json()['keys'][0]


def test_fingerprint_detects_data_and_rls_changes_without_exporting_rows():
    import json
    module=common()
    class Result:
        def __init__(self,rows):self.rows=rows
        def fetchall(self):return self.rows
    class Connection:
        changed=False
        rls=True
        def execute(self,query):
            if 'row_to_json' in query:return Result([(json.dumps({'id':1,'comment':'private fixture','version':2 if self.changed else 1}),)])
            if 'relrowsecurity' in query:return Result([('public','beta_feedback',self.rls,False)])
            return Result([])
    conn=Connection();before=module.fingerprint(conn)
    assert 'private fixture' not in str(before)
    conn.changed=True
    assert module.fingerprint(conn)!=before
    conn.changed=False;conn.rls=False
    assert module.fingerprint(conn)!=before
