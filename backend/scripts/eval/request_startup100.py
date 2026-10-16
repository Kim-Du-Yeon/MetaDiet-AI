"""Frozen synthetic public API startup test; browser paint is separately measured."""
import argparse
import concurrent.futures
import hashlib
import json
import os
import re
from pathlib import Path
from uuid import uuid4
from dotenv import dotenv_values
from latency100 import capture, ROOT, API, load_env, service_api, json_request

QUESTIONS = [
    '점심 추천해줘. 조언만 하고 기록은 변경하지 마.',
    '감량과 근육 유지를 위해 목표 검토와 영양 근거 검토를 함께 해줘. 기록은 변경하지 마.',
    '그럼 한식뷔페 가서 일반식 먹어도 괜찮아? 기록은 변경하지 마.',
    '최근 식사와 체중 추세를 확인하고 목표 진행과 근손실 위험을 검토해줘. 기록은 변경하지 마.',
]
SUFFIX = ' 첫 문장에 "오늘 섭취: N kcal, 하루 기준: N kcal" 형식으로 적어줘.'


def main():
    p = argparse.ArgumentParser()
    p.add_argument('phase', choices=['before', 'after'])
    p.add_argument('--expected-commit', required=True)
    args = p.parse_args()
    folder = ROOT / 'docs/request_startup'
    output = folder / f'{args.phase}_frozen100.json'
    assert not output.exists(), 'Do not overwrite evidence'
    load_env(ROOT/'backend/.env')
    fixture = dotenv_values(ROOT/'backend/.env.budget-public')
    assert fixture['EMAIL'].startswith('budget-public-') and fixture['EMAIL'].endswith('@example.invalid')
    signed = service_api('/auth/v1/token?grant_type=password','POST',dict(email=fixture['EMAIL'],password=fixture['PASSWORD']))
    assert signed['user']['id'] == fixture['AUTH_ID']
    token = signed['access_token']
    user = service_api('/rest/v1/users?auth_id=eq.'+fixture['AUTH_ID']+'&select=id')[0]['id']
    def snapshot():
        return [service_api('/rest/v1/'+table+'?user_id=eq.'+user+'&order=id') for table in ['meal_logs','diet_strategies']]
    before = snapshot()
    state = json_request(API+'/session/restore/startup-preflight', token=token)
    expected = (state['today_calories'], state['target_calories'])
    health = json_request(API+'/health')
    assert health['build']['commit'] == args.expected_commit
    report = {'scope':'public real model/DB synthetic fixed account, concurrency=4; not browser paint',
        'dataset_sha256':hashlib.sha256(json.dumps(QUESTIONS,ensure_ascii=False).encode()).hexdigest(),
        'expected':expected, 'commit':args.expected_commit, 'rows':[]}
    if args.phase == 'after':
        previous = json.loads((folder/'before_frozen100.json').read_text(encoding='utf-8'))
        assert previous['dataset_sha256'] == report['dataset_sha256'] and previous['expected'] == list(expected)
    def attempt(index):
        request_id = str(uuid4())
        row = capture(token, {'message':QUESTIONS[index%4]+SUFFIX, 'thread_id':'startup-'+uuid4().hex,
            'stream_run_id':request_id, 'stream_protocol':2, 'after_seq':0,
            'messages':[{'role':'user','content':'점심 추천해줘'},
                        {'role':'assistant','content':'이전 기록은 300 kcal, 목표는 2200 kcal입니다.'}]})
        row.update(index=index, case=index%4, request_id=request_id)
        match = re.search(r'오늘\s*섭취\s*[:：]\s*([\d,]+)\s*kcal.*?하루\s*기준\s*[:：]\s*([\d,]+)\s*kcal',row['answer'].replace('**',''),re.S|re.I)
        row['fresh_numeric_match'] = bool(match and tuple(float(v.replace(',','')) for v in match.groups()) == expected)
        return row
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(attempt, i) for i in range(100)]
            for future in concurrent.futures.as_completed(futures):
                row = future.result()
                report['rows'].append(row)
                output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
                print(args.phase, len(report['rows']), row['index'], row['status'], round(row['total_ms']), flush=True)
    finally:
        report['domain_unchanged'] = snapshot() == before
        output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    assert len(report['rows']) == 100 and report['domain_unchanged']


if __name__ == '__main__':
    main()
