import copy
import pytest

from scripts.eval.analyze_model_routing import combine, verify_frozen_hash


def fixtures():
    tasks = ['extraction','classification','query_translation','agent']
    cases = [{'id':f'case-{i:03}','task':tasks[i%4]} for i in range(100)]
    reports = []
    for shard in range(3):
        reports.append({'protocol':'task-balanced-pair-order-v2','shard':shard,'shards':3,
            'prompt_metadata': {'prompt_release': 'v1', 'prompt_bundle_sha256':
                '4c40f46e4c2aa01b5ba7c78f456cff11b11907a4730e697288f796694ec7a741'},
            'cases_sha256':'same-fixture-hash', 'model_config':{'gemini_model':'fixture'},
            'judge_status':'unavailable_or_not_run','rows':[
                {'case_id':c['id'],'task':c['task'],'condition':mode,'status':'completed',
                 'quality':True,'fresh':True,'fresh_applicable':c['task']=='agent',
                 'ms':10,'cost_usd':.1}
                for i,c in enumerate(cases) if i%3==shard for mode in ('baseline','routing')]})
    return cases,reports


def test_merge_requires_exact_case_pairs_and_keeps_missing_judge_blocked():
    cases,reports = fixtures()
    report = combine(reports,cases)
    assert report['summary']['baseline']['attempts']==100
    assert report['summary']['routing']['freshness_attempts']==25
    assert report['deployment_gate'] is False
    reports[0]['rows'].append(copy.deepcopy(reports[0]['rows'][0]))
    with pytest.raises(ValueError,match='duplicate'): combine(reports,cases)


def test_merge_rejects_missing_or_foreign_configuration():
    cases,reports = fixtures()
    with pytest.raises(ValueError,match='shard'): combine(reports[:-1],cases)
    reports[1]['model_config']={'gemini_model':'changed-fixture'}
    with pytest.raises(ValueError,match='identity'): combine(reports,cases)


def test_normalization_preserves_original_failure_evidence():
    cases,reports = fixtures()
    reports[0]['rows'][0].update(status='failed',quality=False,cost_usd=None,
        error={'type':'GoogleRateLimitError','reason':'credits_depleted'})
    merged = combine(reports,cases)
    row = next(r for r in merged['rows'] if r['case_id']=='case-000' and r['condition']=='baseline')
    assert row['error']['reason']=='credits_depleted'
    assert row['normalized_error']=='quota_exhausted'
    assert merged['error_reasons']['baseline']=={'quota_exhausted':1}


def test_windows_newlines_do_not_hide_actual_frozen_content_changes():
    import hashlib
    canonical = b'[\n  {"id":"case-000"}\n]\n'
    sha = hashlib.sha256(canonical).hexdigest()
    verify_frozen_hash(canonical.replace(b'\n',b'\r\n'),sha)
    with pytest.raises(ValueError,match='hash'):
        verify_frozen_hash(canonical.replace(b'000',b'001'),sha)


def test_merge_rejects_mixed_prompt_bundles_and_unverified_judge_completion():
    cases, reports = fixtures()
    for report in reports:
        report['judge_status'] = 'completed'
    # A status string alone cannot prove all case/condition judges completed.
    assert combine(reports, cases)['judge_complete'] is False
    reports[1]['prompt_metadata']['prompt_bundle_sha256'] = 'changed'
    with pytest.raises(ValueError, match='identity'):
        combine(reports, cases)


def test_missing_judge_usage_blocks_adoption_even_with_complete_grades():
    cases, reports = fixtures()
    for report in reports:
        report['judge_status'] = 'completed'
        for row in report['rows']:
            if row['condition'] == 'routing':
                row.update(ms=8, cost_usd=.05)
        report['judge_rows'] = [dict(case_id=row['case_id'], condition=row['condition'],
            status='completed', cost_usd=None) for row in report['rows'] if row['task']=='agent']
    assert combine(reports, cases)['deployment_gate'] is False
    for report in reports:
        for row in report['judge_rows']:
            row['cost_usd'] = .01
    assert combine(reports, cases)['deployment_gate'] is True


@pytest.mark.parametrize('metadata', [None, {'prompt_release': 'v1', 'prompt_bundle_sha256': 'wrong'}])
def test_merge_rejects_consistently_missing_or_wrong_v1(metadata):
    cases, reports = fixtures()
    for report in reports:
        report['prompt_metadata'] = metadata
    with pytest.raises(ValueError, match='v1'):
        combine(reports, cases)
