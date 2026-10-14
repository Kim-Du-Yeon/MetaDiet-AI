"""Public serial comparison; disposable synthetic account only, no evidence overwrite."""
import argparse
import hashlib
import json
import re
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from uuid import uuid4
from dotenv import dotenv_values
from latency100 import capture, API, ROOT, load_env, service_api, json_request

FOLDER = ROOT / 'docs/budget_public'
ENV = ROOT / 'backend/.env.budget-public'
COMMIT = 'f60c040bb1a973db4e8ecc18196ecf52920d73c8'
QUESTIONS = ['그럼 한식뷔페 가서 일반식 먹어도 괜찮아?', '그럼 샌드위치 먹어도 괜찮아?',
             '밥이랑 계란 먹어도 괜찮아?', '닭가슴살이랑 샐러드 먹어도 괜찮아?']
CONTEXTS = [('confirmed',600,2000),('edited',850,2000),('deleted',0,2000),
            ('goal_changed',600,1800),('prior_day_only',0,1900)]


def verify_state(token, calories, target, unavailable):
    for attempt in range(3):
        try:
            state = json_request(API+'/session/restore/budget-public-check',token=token)
        except RuntimeError as exc:
            # Only retry transient HTTP failures for this read-only preflight.
            if not any(str(exc).startswith('HTTP '+str(code)+' ') for code in (500,502,503,504)):
                raise
            state = {}
            unavailable.append({'attempt':attempt+1,'reason':str(exc).split(' ',2)[0:2]})
        if 'today_calories' in state and 'target_calories' in state:
            assert state['today_calories']==calories and state['target_calories']==target, 'Fixture state mismatch'
            return
        unavailable.append({'attempt':attempt+1,'reason':'public_stats_missing'})
        if attempt<2:
            time.sleep(2**attempt)
    raise AssertionError('Public stats unavailable after bounded preflight retry')


def persist_capture(report, output, row, before, readback):
    """Never lose a timed attempt if an untimed postflight read fails."""
    row.update(no_write=False,postflight_verified=False)
    report['rows'].append(row)
    def save():
        output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    save()
    try:
        row['no_write'] = before==readback() and not row.get('unexpected_proposal')
        row['postflight_verified'] = True
    except Exception as exc:
        row['postflight_error_type'] = type(exc).__name__
    save()

def main():
    global FOLDER, COMMIT
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=['setup','before','after','cleanup'])
    parser.add_argument('--resume',action='store_true',help='Append remaining cases without removing failed attempts')
    parser.add_argument('--probe',action='store_true',help='One separately recorded deployment warm-up, outside the 100')
    parser.add_argument('--folder', default='docs/budget_public')
    parser.add_argument('--expected-commit', default=COMMIT)
    parser.add_argument('--experiment', choices=['budget', 'brief'], default='budget')
    args = parser.parse_args()
    FOLDER = ROOT / args.folder
    COMMIT = args.expected_commit
    load_env(ROOT/'backend/.env')
    FOLDER.mkdir(exist_ok=True)
    if args.phase == 'setup':
        assert not ENV.exists(), 'Existing fixture must be recovered, not replaced'
        email = 'budget-public-'+uuid4().hex+'@example.invalid'
        password = 'T!'+uuid4().hex+'a9'
        auth = service_api('/auth/v1/admin/users','POST',dict(email=email,password=password,email_confirm=True))
        ENV.write_text(f'EMAIL={email}\nPASSWORD={password}\nAUTH_ID={auth["id"]}\n',encoding='utf-8')
    fixture = dotenv_values(ENV)
    assert fixture['EMAIL'].startswith('budget-public-') and fixture['EMAIL'].endswith('@example.invalid')
    signed = service_api('/auth/v1/token?grant_type=password','POST',
        dict(email=fixture['EMAIL'],password=fixture['PASSWORD']))
    assert signed['user']['id']==fixture['AUTH_ID'] and signed['user']['email']==fixture['EMAIL'], 'Fixture identity mismatch'
    token = signed['access_token']
    if args.phase == 'cleanup':
        result = json_request(API+'/users/me',token=token,method='DELETE',payload={'confirmation':'DELETE'})
        assert result['status']=='deleted'
        assert service_api('/rest/v1/users?auth_id=eq.'+fixture['AUTH_ID']+'&select=id')==[]
        (FOLDER/'cleanup.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        ENV.unlink()
        print('Synthetic account and credentials removed.')
        return
    if args.phase == 'setup':
        result = json_request(API+'/users/onboarding',token=token,method='POST',payload=dict(
            goal='diet',region='KR',height_cm=175,weight_kg=82,age=35,sex='male',activity='low_active',
            general_adult_confirmed=True,target_weight_kg=75,target_date='2027-04-30',goal_priority='balance'))
        p = result['pending_proposal']
        json_request(API+'/proposals/decision',token=token,method='POST',payload=dict(proposal_id=p['id'],version=p['version'],action='confirm'))
        print('Disposable fixture ready; credentials stored only in ignored env.')
        return
    output = FOLDER/(args.phase+('_probe' if args.probe else '')+'.json')
    assert not output.exists() or args.resume, 'Refusing to overwrite evidence; use --resume to append'
    health = json_request(API+'/health')
    assert health['build']['commit'] == COMMIT, 'Deployment mismatch'
    user = service_api('/rest/v1/users?auth_id=eq.'+signed['user']['id']+'&select=id')[0]['id']
    def meals():
        return service_api('/rest/v1/meal_logs?user_id=eq.'+user+'&order=id')
    def strategies():
        return service_api('/rest/v1/diet_strategies?user_id=eq.'+user+'&order=id')
    report = dict(scope='public_serial_real_model_real_database_synthetic_fixture',phase=args.phase,
        expected_commit=COMMIT,health=health,started_at=datetime.now().astimezone().isoformat(),
        dataset_sha256=hashlib.sha256(json.dumps([QUESTIONS,CONTEXTS],ensure_ascii=False).encode()).hexdigest(),rows=[])
    if args.resume:
        previous = json.loads(output.read_text(encoding='utf-8'))
        assert all(previous[k]==report[k] for k in ('phase','expected_commit','dataset_sha256'))
        assert [r['pair'] for r in previous['rows']]==list(range(len(previous['rows'])))
        report = previous
    for index in range(len(report['rows']),1 if args.probe else 100):
        case, calories, target = CONTEXTS[(index//4)%5]
        today = datetime.now(ZoneInfo('Asia/Seoul')).date()
        service_api('/rest/v1/meal_logs?user_id=eq.'+user,'DELETE')
        service_api('/rest/v1/diet_strategies?user_id=eq.'+user,'PATCH',{'daily_calories':target})
        if calories or case == 'prior_day_only':
            service_api('/rest/v1/meal_logs','POST',dict(user_id=user,
                log_date=str(today-timedelta(days=1) if case=='prior_day_only' else today),
                meal_type='breakfast',food_name='synthetic benchmark fixture',quantity_g=100,
                calories=calories or 600,protein_g=30,carbs_g=60,fat_g=20))
        unavailable = []
        verify_state(token,calories,target,unavailable)
        before = (meals(),strategies())
        question = QUESTIONS[index%4]+' 첫 문장에 "오늘 섭취: N kcal, 하루 기준: N kcal" 형식으로 적어줘.'
        row = capture(token,dict(message=question,messages=[{'role':'user','content':'점심 추천해줘'},
            {'role':'assistant','content':'이전 조회의 섭취 기록은 300 kcal, 목표는 2200 kcal입니다. 밥과 채소를 곁들이세요.'}],
            thread_id='budget-public-'+uuid4().hex,stream_run_id=str(uuid4()),after_seq=0,stream_protocol=2))
        match = re.search(r'오늘\s*섭취\s*[:：]\s*([\d,]+)\s*kcal.*?하루\s*기준\s*[:：]\s*([\d,]+)\s*kcal',row['answer'].replace('**',''),re.S|re.I)
        row.update(pair=index,case=case,question=question,expected_calories=calories,expected_target=target,
            fresh=bool(match and tuple(int(v.replace(',','')) for v in match.groups())==(calories,target)),
            preflight_unavailable=unavailable,
            mode='baseline' if args.phase=='before' else ('brief' if args.experiment=='brief' else 'pipeline'))
        persist_capture(report,output,row,before,lambda:(meals(),strategies()))
        print(args.phase,index+1,row['status'],round(row['total_ms']),row['fresh'],flush=True)
        if row.get('build'):
            assert row['build']['commit'] == COMMIT, 'Build mismatch; evidence retained'
        stages = row['stage_timings_ms']
        if 'budget_setup' in stages or 'budget_setup_enqueue' in stages:
            assert ('budget_setup_enqueue' in stages) == (args.experiment=='brief' or args.phase=='after'), 'Mode mismatch; evidence retained'
        if args.experiment == 'brief' and row['status'] == 'completed':
            assert row.get('answer_style') == ('brief' if args.phase=='after' else 'default'), 'Answer style mismatch; evidence retained'
            assert (row.get('route'), row.get('reasoning'), row.get('model_delivery'), row.get('model_name')) == (
                'followup_direct', 'low', 'invoke', 'gemini-3.8-flash'), 'Model configuration mismatch; evidence retained'
        # Missing timings on failures remain in the denominator and block adoption.

if __name__ == '__main__': main()
