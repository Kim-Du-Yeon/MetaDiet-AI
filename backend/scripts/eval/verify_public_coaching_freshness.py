"""Disposable synthetic account: approval, revision, cancellation and fresh coaching."""
import json
import os
import re
import argparse
from pathlib import Path
from uuid import uuid4
from benchmark_coaching import API, ROOT, load_env, service_api, json_request, run
from check_render_beta import stream


_cleanup = None


def verify(output_dir=ROOT / 'docs/answer_delivery', direct_followup=False, first_advice=False):
    global _cleanup
    load_env(ROOT / 'backend/.env')
    load_env(ROOT / 'backend/.env.selection-browser')
    token = service_api('/auth/v1/token?grant_type=password', 'POST',
                        {'email': os.environ['EMAIL'], 'password': os.environ['PASSWORD']})['access_token']
    user = service_api('/rest/v1/users?auth_id=eq.' + os.environ['AUTH_ID'] + '&select=id')[0]['id']
    def records():
        return service_api('/rest/v1/meal_logs?user_id=eq.' + user + '&select=id,calories')
    def proposal():
        events, _ = stream(API + '/chat', token, {'message': '밥 한공기', 'requested_action': 'record_only',
                         'thread_id': 'fresh-' + uuid4().hex, 'stream_run_id': str(uuid4()), 'after_seq': 0})
        return next(e for e in events if e.get('type') == 'completed')['pending_proposal']
    def decision(p, action):
        return json_request(API + '/proposals/decision', token=token, method='POST',
                            payload={'proposal_id': p['id'], 'version': p['version'], 'action': action})
    assert records() == [], 'Use a fresh disposable fixture, not a real account.'
    def cleanup():
        for row in records():
            json_request(API + '/meal/delete/' + row['id'], token=token, method='DELETE')
    _cleanup = cleanup
    p = proposal()
    assert records() == []
    decision(p, 'cancel')
    assert records() == []
    p = proposal()
    meals = p['payload']['meals']
    revised = json_request(API + '/proposals/' + p['id'] + '/meal', token=token, method='PUT', payload={
        'version': p['version'], 'log_date': p['payload']['log_date'], 'meal_type': meals[0]['meal_type'],
        'items': [{'amount': 300, 'unit': 'g'} for _ in meals]})
    p = revised.get('proposal', revised)
    assert records() == []
    decision(p, 'confirm')
    decision(p, 'confirm')
    assert len(records()) == 1
    expected = sum(r['calories'] for r in records())
    history = [{'role': 'user', 'content': '점심 추천해줘'},
               {'role': 'assistant', 'content': '이전 조회에서는 오늘 섭취가 0kcal였습니다.'}]
    message = ('그럼 한식뷔페 먹어도 괜찮아? 첫 문장에 "오늘 섭취: N kcal" 형식으로 현재 섭취 열량을 적어줘.' if direct_followup else
               '그럼 첫 문장을 "오늘 확정 섭취: N kcal" 형식으로 현재 확정 열량을 적고 점심 조언만 해줘. 계획 카드는 만들지 마.')
    if first_advice:
        message = '점심 추천해줘. 오늘 남은 칼로리도 알려줘.'
    row = run(token, {'message': message,
                      'messages': history, 'thread_id': 'other-' + uuid4().hex, 'stream_run_id': str(uuid4()), 'after_seq': 0})
    assert any(e.get('phase') == 'coaching_context' for e in row['progress'])
    if direct_followup or first_advice:
        assert row['stage_timings_ms'].get('model_meal', 0) > 0
        assert 'model_supervisor' not in row['stage_timings_ms']
    if first_advice:
        from check_first_coaching_answers import remaining_calories
        current = json_request(API + '/session/restore/freshness-first', token=token)
        observed = remaining_calories(row['answer'])
        expected_remaining = current['target_calories']-expected
        output_dir.mkdir(parents=True,exist_ok=True)
        (output_dir/'FRESHNESS_PUBLIC_ANSWER.json').write_text(json.dumps({'expected_remaining':expected_remaining,
            'observed_remaining':observed,'answer':row['answer'],'stage_timings_ms':row['stage_timings_ms']},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        assert observed is not None and abs(observed-expected_remaining)<=1
    else:
        current_intake = re.search(r'오늘\s*(?:확정\s*)?섭취\s*:\s*(\d+(?:\.\d+)?)\s*kcal',
                                   row['answer'].replace(',', '').replace('**', ''), re.I)
        assert current_intake and abs(float(current_intake.group(1)) - expected) <= 1
    json_request(API + '/meal/delete/' + records()[0]['id'], token=token, method='DELETE')
    assert records() == []
    state = json_request(API + '/session/restore/freshness-refresh', token=token)
    assert state['today_calories'] == 0
    report = {'scope': 'synthetic_public_approval_and_context_freshness', 'cancel_no_write': True,
              'direct_followup_verified': direct_followup,
              'first_advice_verified': first_advice,
              'revision_before_confirmation_no_write': True, 'duplicate_confirm_rows': 1,
              'confirmed_revised_intake_seen_despite_stale_messages': True, 'trace_id': row['trace_id'],
              'delete_and_refreshed_state_zero': True,
              'limitations': 'One disposable account. Date, target and DB outage coverage is scripted regression, not public fault injection.'}
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / 'FRESHNESS_PUBLIC.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print('Public approval/freshness checks passed; fixture meal records restored to empty.')


if __name__ == '__main__':
    try:
        parser = argparse.ArgumentParser()
        parser.add_argument('--output-dir', type=Path, default=ROOT / 'docs/answer_delivery')
        parser.add_argument('--direct-followup', action='store_true')
        parser.add_argument('--first-advice', action='store_true')
        args = parser.parse_args()
        verify(args.output_dir, args.direct_followup, args.first_advice)
    finally:
        if _cleanup:
            _cleanup()
