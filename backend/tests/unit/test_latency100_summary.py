import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location('latency_summary', Path(__file__).resolve().parents[2] / 'scripts/eval/summarize_latency100.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_refuses_small_sample():
    with pytest.raises(ValueError, match='100'):
        module.summarize([{'status': 'completed'}] * 99)


def test_failures_retained_and_nearest_rank_p95():
    rows = [{'status': 'completed', 'total_ms': i} for i in range(1, 100)]
    rows.append({'status': 'failed', 'total_ms': 180000})
    result = module.summarize(rows)
    assert result['attempts'] == 100
    assert result['failed_or_blocked'] == 1
    assert result['fresh'] is None
    assert result['total_ms_completed']['n'] == 99
    assert result['duration_ms_all_attempts']['p95'] == 95


def test_judge_failure_is_not_removed():
    rows = [{'index': i, 'judge_status': 'completed', 'relevant': True} for i in range(99)]
    rows.append({'index': 99, 'judge_status': 'failed'})
    assert module.quality(rows)['relevant'] == 99
    assert module.quality(rows)['attempts'] == 100
