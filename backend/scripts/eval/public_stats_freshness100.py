"""Public restore100: five synthetic DB states x20, no model invocation."""
import argparse
import concurrent.futures
import hashlib
import json
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from uuid import uuid4
from dotenv import dotenv_values
from latency100 import ROOT, API, load_env, service_api, json_request

CASES = [('confirmed',600,2000), ('edited',850,2000), ('deleted',0,2000),
         ('goal_changed',600,1800), ('prior_day_only',0,1900)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=['before','after'])
    parser.add_argument('--expected-commit', required=True)
    args = parser.parse_args()
    folder = ROOT/'docs/public_stats_recovery'
    output = folder/f'{args.phase}_freshness100.json'
    assert not output.exists(), 'Never overwrite evidence'
    load_env(ROOT/'backend/.env')
    fixture = dotenv_values(ROOT/'backend/.env.budget-public')
    assert fixture['EMAIL'].startswith('budget-public-') and fixture['EMAIL'].endswith('@example.invalid')
    signed = service_api('/auth/v1/token?grant_type=password','POST',dict(email=fixture['EMAIL'],password=fixture['PASSWORD']))
    assert signed['user']['id'] == fixture['AUTH_ID']
    token = signed['access_token']
    user = service_api('/rest/v1/users?auth_id=eq.'+fixture['AUTH_ID']+'&select=id')[0]['id']
    def snapshot():
        return [service_api('/rest/v1/'+table+'?user_id=eq.'+user+'&order=id') for table in ('meal_logs','diet_strategies')]
    original = snapshot()
    assert not original[0] and len(original[1]) == 1, 'Only disposable empty fixture allowed'
    assert json_request(API+'/health')['build']['commit'] == args.expected_commit
    report = {'commit':args.expected_commit, 'scope':'public restore; synthetic mutations; concurrency4; no model',
              'dataset_sha256':hashlib.sha256(json.dumps(CASES).encode()).hexdigest(), 'rows':[]}
    def attempt(index, case, calories, target):
        started = time.perf_counter()
        row = {'index':index,'case':case,'correct':False}
        try:
            state = json_request(API+'/session/restore/stats-fresh-'+uuid4().hex, token=token, timeout=40)
            row['correct'] = (state.get('today_calories'),state.get('target_calories')) == (calories,target)
            row['stats_available'] = 'today_calories' in state and 'target_calories' in state
        except Exception as exc:
            row['error_type'] = type(exc).__name__
        row['total_ms'] = (time.perf_counter()-started)*1000
        return row
    try:
        for group, (case, calories, target) in enumerate(CASES):
            today = datetime.now(ZoneInfo('Asia/Seoul')).date()
            service_api('/rest/v1/meal_logs?user_id=eq.'+user,'DELETE')
            service_api('/rest/v1/diet_strategies?user_id=eq.'+user,'PATCH',{'daily_calories':target})
            if calories or case == 'prior_day_only':
                service_api('/rest/v1/meal_logs','POST',dict(user_id=user,
                    log_date=str(today-timedelta(days=1) if case=='prior_day_only' else today),
                    meal_type='breakfast',food_name='synthetic stats fixture',quantity_g=100,
                    calories=calories or 600,protein_g=30,carbs_g=60,fat_g=20))
            before = snapshot()
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                futures = [executor.submit(attempt,group*20+i,case,calories,target) for i in range(20)]
                for future in concurrent.futures.as_completed(futures):
                    report['rows'].append(future.result())
                    output.write_text(json.dumps(report,indent=2),encoding='utf-8')
            assert snapshot() == before, 'Reads changed domain data'
            print(args.phase,case,len(report['rows']),flush=True)
    finally:
        service_api('/rest/v1/meal_logs?user_id=eq.'+user,'DELETE')
        service_api('/rest/v1/diet_strategies?user_id=eq.'+user,'PATCH',{'daily_calories':original[1][0]['daily_calories']})
        report['restored_original_values'] = snapshot() == original
        output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    assert len(report['rows']) == 100 and report['restored_original_values']


if __name__ == '__main__': main()
