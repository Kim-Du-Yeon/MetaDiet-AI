"""Validation-only ASGI entrypoint: real feedback router/repository, synthetic JWT issuer.

Never imported by production main.py. No Supabase Auth, Agent, RAG or scheduler.
"""
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from render_validation_common import validate_render_target, connection_options


def create_app():
    values = dict(os.environ)
    values['VALIDATION_API_URL'] = values.get('RENDER_EXTERNAL_URL') or values['VALIDATION_API_URL']
    validate_render_target(values)
    # Required settings are isolated and unused for model/RAG calls in this app.
    os.environ['SUPABASE_URL'] = values['VALIDATION_API_URL']
    from psycopg.conninfo import make_conninfo
    os.environ['SUPABASE_DB_URL'] = make_conninfo(**connection_options(values))
    for key in ['GEMINI_API_KEY', 'PINECONE_API_KEY', 'SUPABASE_SERVICE_KEY']:
        os.environ.setdefault(key, 'validation-unused-no-external-access')
    if not os.environ.get('SUPABASE_JWT_SECRET'):
        raise ValueError('independent_fallback_secret_required')
    from fastapi import FastAPI, HTTPException
    from psycopg import AsyncConnection
    from app.api.routes.admin_feedback import router
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.include_router(router)
    jwk = json.loads(values['VALIDATION_PUBLIC_JWK'])
    if jwk.get('kty') != 'RSA' or any(key in jwk for key in ['d', 'p', 'q']):
        raise ValueError('public_signing_key_required')

    @app.get('/auth/v1/.well-known/jwks.json')
    def public_jwks():
        return {'keys': [jwk]}

    @app.get('/health')
    async def health():
        try:
            async with await AsyncConnection.connect(**connection_options(values)) as conn:
                row = await (await conn.execute('select run_id,current_database(),pg_postmaster_start_time() from public.validation_meta')).fetchone()
                if row is None or str(row[0]) != values['VALIDATION_RUN_ID'] or row[1] != values['VALIDATION_DB_NAME']:
                    raise ValueError('validation_marker_mismatch')
                return {'validation_only': True, 'run_id': str(row[0]), 'database_name': row[1],
                        'database_started_at': row[2].isoformat(), 'commit': os.getenv('RENDER_GIT_COMMIT', 'local'),
                        'authentication': 'synthetic_RSA_JWT_not_Supabase_Auth'}
        except Exception:
            raise HTTPException(503, 'validation database unavailable') from None
    return app


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(create_app(), host='0.0.0.0', port=int(os.getenv('PORT', '10000')))
