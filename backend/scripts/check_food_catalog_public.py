"""Public HITL smoke with a disposable account; never prints credentials."""
import argparse
import json
from pathlib import Path
from uuid import uuid4
from datetime import datetime
from zoneinfo import ZoneInfo
from check_render_beta import load_env, json_request, service_api, BACKEND


def check(base):
    marker = uuid4().hex
    email, password = f'food-smoke-{marker}@example.invalid', f'T!{marker}a9'
    auth_id = None
    report = {'synthetic': True, 'base_url': base, 'checks': []}
    try:
        auth_id = service_api('/auth/v1/admin/users', 'POST', {'email': email, 'password': password, 'email_confirm': True})['id']
        token = service_api('/auth/v1/token?grant_type=password', 'POST', {'email': email, 'password': password})['access_token']
        onboarding = json_request(base + '/users/onboarding', token=token, method='POST', payload={
            'goal': 'diet', 'region': 'KR', 'height_cm': 175, 'weight_kg': 82, 'age': 35,
            'sex': 'male', 'activity': 'low_active', 'general_adult_confirmed': True,
            'target_weight_kg': 75, 'target_date': '2027-04-30', 'goal_priority': 'balance'})
        user_id = service_api(f'/rest/v1/users?auth_id=eq.{auth_id}&select=id')[0]['id']
        thread = 'food-smoke-' + marker
        before = service_api(f'/rest/v1/meal_logs?user_id=eq.{user_id}&select=id')
        result = json_request(base + '/nutrition/lookup', method='POST', payload={'foods': [{'name': '돼지바', 'quantity_g': 50}]})['results'][0]
        assert result['status'] == 'ambiguous' and not result['found_in_db']
        report['checks'].append('ambiguous_product_not_calculated')
        payload = {'food_name': '합성 영양표 검증 제품', 'manufacturer': '합성 테스트', 'basis_g': 50,
            'quantity_g': 100, 'calories': 100, 'protein_g': 0, 'carbs_g': 20, 'fat_g': 2,
            'meal_type': 'snack', 'log_date': datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat(),
            'thread_id': thread, 'request_id': str(uuid4())}
        proposal = json_request(base + '/nutrition/label-proposal', token=token, method='POST', payload=payload)
        repeated = json_request(base + '/nutrition/label-proposal', token=token, method='POST', payload=payload)
        assert repeated['id'] == proposal['id'] and proposal['status'] == 'pending'
        assert service_api(f'/rest/v1/meal_logs?user_id=eq.{user_id}&select=id') == before
        restored = json_request(base + '/session/restore/' + thread, token=token)
        assert restored['pending_proposal']['id'] == proposal['id']
        report['checks'].extend(['pending_without_domain_write', 'duplicate_request_same_proposal', 'pending_restore'])
        decision = {'proposal_id': proposal['id'], 'version': proposal['version'], 'action': 'confirm'}
        assert json_request(base + '/proposals/decision', token=token, method='POST', payload=decision)['status'] == 'confirmed'
        assert json_request(base + '/proposals/decision', token=token, method='POST', payload=decision)['status'] == 'confirmed'
        rows = service_api(f'/rest/v1/meal_logs?user_id=eq.{user_id}&select=id,source,food_id,nutrition_metadata,calories')
        assert len(rows) == len(before) + 1
        row = next(r for r in rows if r['source'] == 'user_label')
        assert row['calories'] == 200 and row['food_id'].startswith('label:') and row['nutrition_metadata']['basis_g'] == 50
        assert json_request(base + '/session/restore/' + thread, token=token)['pending_proposal'] is None
        report['checks'].extend(['explicit_confirm', 'duplicate_confirm_single_write', 'source_metadata_persisted', 'resolved_restore'])
        payload['request_id'] = str(uuid4())
        cancelled = json_request(base + '/nutrition/label-proposal', token=token, method='POST', payload=payload)
        json_request(base + '/proposals/decision', token=token, method='POST', payload={'proposal_id': cancelled['id'], 'version': cancelled['version'], 'action': 'cancel'})
        assert len(service_api(f'/rest/v1/meal_logs?user_id=eq.{user_id}&select=id')) == len(rows)
        report['checks'].append('cancel_no_write')
    finally:
        if auth_id:
            service_api(f'/auth/v1/admin/users/{auth_id}', 'DELETE')
            report['synthetic_cleanup'] = 'auth_user_deleted'
        path = BACKEND.parent / 'docs/food_catalog/PUBLIC_SMOKE.json'
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=True))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', default='https://metadiet-api.onrender.com')
    args = parser.parse_args()
    load_env(BACKEND / '.env')
    check(args.base_url.rstrip('/'))
