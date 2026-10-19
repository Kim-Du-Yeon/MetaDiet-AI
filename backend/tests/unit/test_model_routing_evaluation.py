import pytest

from scripts.eval.model_routing_support import estimate_cost, summarize, deployment_gate, evaluation_key


def test_cost_includes_reasoning_and_cache_is_not_double_charged():
    # LangChain output_tokens already includes thoughts; do not add them twice.
    usage = {'input_tokens': 1000, 'output_tokens': 500,
             'input_token_details': {'cache_read': 400},
             'output_token_details': {'reasoning': 300}}
    assert estimate_cost('gemini-3.1-flash-lite', usage) == pytest.approx(.00091)
    assert estimate_cost('unknown-model', usage) is None
    assert estimate_cost('gemini-3.1-flash-lite', {}) is None


def test_failed_attempts_remain_in_quality_and_failure_denominators():
    rows = [{'status': 'completed', 'quality': True, 'fresh': True, 'ms': 10,
             'cost_usd': .1}, {'status': 'failed', 'quality': False, 'fresh': False,
             'ms': 30, 'cost_usd': None}]
    report = summarize(rows)
    assert report['attempts'] == 2
    assert report['quality_rate'] == .5
    assert report['failure_rate'] == .5
    assert report['cost_complete'] is False


def test_all_failed_or_missing_judge_never_passes_gate():
    failed = summarize([{'status': 'failed', 'quality': False, 'fresh': False,
        'ms': 1, 'cost_usd': None}] * 100)
    assert not deployment_gate(failed, failed, judge_complete=True)
    good = summarize([{'status': 'completed', 'quality': True, 'fresh': True,
        'ms': 10, 'cost_usd': .1}] * 100)
    assert not deployment_gate(good, good, judge_complete=False)
    assert not deployment_gate(good, good, judge_complete=True)  # no improvement


def test_explicit_evaluation_env_key_wins_without_mutating_process(tmp_path, monkeypatch):
    import os
    monkeypatch.setenv('GEMINI_API_KEY', 'synthetic-stale')
    path = tmp_path / '.env'
    path.write_text('GEMINI_API_KEY=synthetic-rotated\nSUPABASE_SERVICE_KEY=synthetic-ignored\n')
    assert evaluation_key(path) == 'synthetic-rotated'
    assert os.environ['GEMINI_API_KEY'] == 'synthetic-stale'


def test_task_regression_cannot_hide_behind_aggregate_improvement():
    good = summarize([{'status':'completed','quality':True,'fresh':True,'ms':10,'cost_usd':.1}]*100)
    better = {**good,'p50_ms':8,'p95_ms':9,'mean_cost_usd':.05}
    by_task = {task:{'baseline':good,'routing':better} for task in
        ('extraction','classification','query_translation','agent')}
    assert deployment_gate(good,better,judge_complete=True,by_task=by_task)
    by_task['extraction']['baseline'] = {**good,'quality_rate':.9}
    by_task['classification']['routing'] = {**better,'quality_rate':.96}
    assert not deployment_gate(good,better,judge_complete=True,by_task=by_task)


def test_retry_seconds_cannot_be_mistaken_for_http402():
    from scripts.eval.benchmark_model_routing import safe_error
    class GoogleRateLimitError(Exception): pass
    assert safe_error(GoogleRateLimitError('retry delay81402 seconds'))['reason']=='quota_exhausted'
    assert safe_error(Exception('network retry81402 seconds'))['reason']=='provider_or_parse_error'
def test_v1_comparison_rejects_changed_prompt_bundle_before_generation():
    from scripts.eval.model_routing_support import require_prompt_v1
    import pytest
    expected = {'prompt_release': 'v1', 'prompt_bundle_sha256':
        '4c40f46e4c2aa01b5ba7c78f456cff11b11907a4730e697288f796694ec7a741'}
    assert require_prompt_v1(expected) == expected
    for changed in [dict(expected, prompt_release='v2'),
                    dict(expected, prompt_bundle_sha256='0' * 64)]:
        with pytest.raises(ValueError, match='v1'):
            require_prompt_v1(changed)


def test_judge_cost_is_separate_and_missing_usage_does_not_become_free():
    from scripts.eval.model_routing_support import summarize_judge_cost
    rows = [{'condition': 'baseline', 'cost_usd': .03},
            {'condition': 'routing', 'cost_usd': None}]
    report = summarize_judge_cost(rows)
    assert report['baseline'] == {'attempts': 1, 'known_cost_usd': .03, 'cost_complete': True}
    assert report['routing'] == {'attempts': 1, 'known_cost_usd': 0, 'cost_complete': False}
