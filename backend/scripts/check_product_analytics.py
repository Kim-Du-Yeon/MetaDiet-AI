"""Disposable public analytics lifecycle check; never writes credentials to disk."""
import asyncio
import json
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_beta_feedback import BACKEND, api_request, load_env, service_api
from app.db.analytics import ProductEventRepository


def run():
    load_env(BACKEND / '.env')
    base = 'https://metadiet-api.onrender.com'
    auth_id = user_id = None
    result = {}
    try:
        marker = uuid4().hex
        email, password = f'analytics-check-{marker}@example.invalid', f'T!{marker}a9'
        auth_id = service_api('/auth/v1/admin/users', 'POST', {
            'email': email, 'password': password, 'email_confirm': True,
        })['id']
        token = service_api('/auth/v1/token?grant_type=password', 'POST', {
            'email': email, 'password': password,
        })['access_token']
        user_id = service_api('/rest/v1/users', 'POST', {
            'auth_id': auth_id, 'name': 'synthetic-analytics-check', 'goal': 'maintain',
        })[0]['id']
        payload = {'event_name': 'chat_completed', 'status': 'success',
                   'client_event_id': str(uuid4()), 'session_id': str(uuid4()),
                   'duration_ms': 1234, 'properties': {'channel': 'text'}}
        first_status, first = api_request(base + '/analytics/events', token=token, method='POST', payload=payload)
        replay_status, replay = api_request(base + '/analytics/events', token=token, method='POST', payload=payload)
        assert first_status == 201 and replay_status == 200
        assert first['id'] == replay['id'] and first['created'] and not replay['created']
        rows = service_api(f'/rest/v1/product_events?user_id=eq.{user_id}&select=id,duration_ms,properties')
        assert len(rows) == 1 and rows[0]['duration_ms'] == 1234
        assert rows[0]['properties'] == {'channel': 'text'}
        try:
            api_request(base + '/admin/analytics/overview', token=token)
        except RuntimeError as exc:
            assert 'HTTP 403' in str(exc), 'ordinary-user admin denial was not HTTP 403'
        else:
            raise AssertionError('ordinary user received administrator metrics')
        overview = asyncio.run(ProductEventRepository().overview(1))
        assert overview['active_users']['weekly'] >= overview['active_users']['daily'] >= 1
        assert 0 <= overview['funnel']['onboarding_rate'] <= 1
        assert 0 <= overview['funnel']['first_meal_rate'] <= 1
        assert overview['agent']['requests'] >= 1
        deleted, _ = api_request(base + '/users/me', token=token, method='DELETE', payload={'confirmation': 'DELETE'})
        assert deleted == 200
        remaining = service_api(f'/rest/v1/product_events?user_id=eq.{user_id}&select=id')
        assert remaining == []
        result = {'status': 'passed', 'create_http': first_status, 'replay_http': replay_status,
                  'rows_after_replay': 1, 'rows_after_delete': 0,
                  'cohort_query': 'passed', 'weekly_window': 'passed', 'non_admin_http': 403}
    finally:
        # Remove only the IDs created by this invocation, even if public checks fail.
        if user_id:
            service_api(f'/rest/v1/users?id=eq.{user_id}', 'DELETE')
        if auth_id:
            try:
                service_api(f'/auth/v1/admin/users/{auth_id}', 'DELETE')
            except RuntimeError as exc:
                if 'HTTP 404' not in str(exc):
                    raise
    target = BACKEND / 'artifacts' / 'product-analytics-lifecycle-v2.json'
    target.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    run()
