import copy
import pytest

from scripts.eval.analyze_model_routing import combine, verify_frozen_hash


def fixtures():
    tasks = ['extraction','classification','query_translation','agent']
    cases = [{'id':f'case-{i:03}','task':tasks[i%4]} for i in range(100)]
    reports = []
    for shard in range(3):
        reports.append({'protocol':'task-balanced-pair-order-v2','shard':shard,'shards':3,
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
