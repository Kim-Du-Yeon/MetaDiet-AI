"""Functional public SSE smoke test, not a performance sample."""
import json
import os
from urllib import request
from uuid import uuid4
from benchmark_coaching import API, ROOT, load_env, service_api


def main():
    load_env(ROOT / 'backend/.env')
    load_env(ROOT / 'backend/.env.selection-browser')
    token = service_api('/auth/v1/token?grant_type=password', 'POST', {'email': os.environ['EMAIL'], 'password': os.environ['PASSWORD']})['access_token']

    def capture(payload):
        req = request.Request(API + '/chat', data=json.dumps(payload).encode(), method='POST',
                              headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
        with request.urlopen(req, timeout=180) as response:
            return [json.loads(line[5:]) for line in response if line.startswith(b'data:')]

    payload = {'message': '점심 추천해줘', 'thread_id': 'reconnect-' + uuid4().hex,
               'stream_run_id': str(uuid4()), 'stream_protocol': 2}
    initial = capture(payload)
    done = next(e for e in initial if e['type'] == 'completed')
    assert done['answer']
    seq = [e['seq'] for e in initial]
    assert seq == sorted(set(seq))
    replay = capture({**payload, 'after_seq': done['seq'] - 1, 'stream_reconnect': True})
    assert replay == [done]
    exhausted = capture({**payload, 'after_seq': done['seq'], 'stream_reconnect': True})
    assert exhausted == []
    missing = capture({**payload, 'stream_run_id': str(uuid4()), 'stream_reconnect': True})
    assert missing and all(e['type'] == 'failed' for e in missing)
    report = {'scope': 'functional_smoke_not_performance', 'build': done['build'],
              'monotonic_unique_ids': True, 'terminal_replay_identical': True,
              'after_terminal_empty': True, 'missing_run_fails_closed': True,
              'trace_id': done.get('trace_id'), 'usage': done.get('execution_usage')}
    (ROOT / 'docs/latency100/public_delivery.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
