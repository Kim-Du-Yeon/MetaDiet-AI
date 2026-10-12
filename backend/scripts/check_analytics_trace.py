"""Verify public SSE -> analytics -> private LangSmith correlation with a disposable user."""
import json
import sys
import time
from pathlib import Path
from urllib import request
from uuid import UUID, uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_beta_feedback import BACKEND, api_request, load_env, service_api
from langsmith import Client


def run():
    load_env(BACKEND / '.env')
    base = 'https://metadiet-api.onrender.com'
    auth_id = user_id = None
    try:
        marker = uuid4().hex
        credentials = {'email': f'trace-check-{marker}@example.invalid', 'password': f'T!{marker}a9'}
        auth_id = service_api('/auth/v1/admin/users', 'POST', {**credentials, 'email_confirm': True})['id']
        token = service_api('/auth/v1/token?grant_type=password', 'POST', credentials)['access_token']
        user_id = service_api('/rest/v1/users', 'POST', {
            'auth_id': auth_id, 'name': 'synthetic-trace-check', 'goal': 'maintain',
        })[0]['id']
        stream_id = str(uuid4())
        payload = {'message': '서울 날씨를 알려줘', 'thread_id': marker, 'stream_run_id': stream_id}
        req = request.Request(base + '/chat', data=json.dumps(payload).encode(), headers={
            'Authorization': f'Bearer {token}', 'Content-Type': 'application/json',
        })
        with request.urlopen(req, timeout=180) as response:
            frames = response.read().decode().splitlines()
        events = [json.loads(line[6:]) for line in frames if line.startswith('data: ')]
        completed = next((e for e in events if e.get('type') == 'completed'), None)
        assert completed, 'public chat did not emit completed'
        trace_id = completed.get('trace_id')
        assert trace_id, 'deployed response has no trace_id (check deployment version)'
        UUID(trace_id)
        status, _ = api_request(base + '/analytics/events', token=token, method='POST', payload={
            'event_name': 'chat_completed', 'status': 'success', 'client_event_id': str(uuid4()),
            'session_id': str(uuid4()), 'trace_id': trace_id,
        })
        assert status == 201
        rows = service_api(f'/rest/v1/product_events?user_id=eq.{user_id}&select=trace_id')
        assert len(rows) == 1 and rows[0]['trace_id'] == trace_id
        client = Client()
        # Trace uploads are asynchronous; allow bounded ingestion time.
        for attempt in range(4):
            try:
                span = client.read_run(trace_id)
                break
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(3)
        assert str(span.id) == trace_id and str(span.trace_id) == trace_id
        assert span.parent_run_id is None
        assert span.extra['metadata']['stream_run_id'] == stream_id
        result = {'status': 'passed', 'public_sse_trace': True,
                  'analytics_trace': True, 'langsmith_root_span': True}
        (BACKEND / 'artifacts' / 'analytics-trace-v1.json').write_text(json.dumps(result), encoding='utf-8')
        print(json.dumps(result))
    finally:
        if user_id:
            service_api(f'/rest/v1/users?id=eq.{user_id}', 'DELETE')
        if auth_id:
            service_api(f'/auth/v1/admin/users/{auth_id}', 'DELETE')


if __name__ == '__main__':
    run()
