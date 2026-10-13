import importlib.util
from pathlib import Path
import sys

folder = Path(__file__).resolve().parents[2] / 'scripts/eval'
sys.path.insert(0, str(folder))
spec = importlib.util.spec_from_file_location('compact_summary', folder / 'summarize_compact100.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_all_failed_candidate_cannot_be_adopted():
    before = {'total_ms_completed': {'median': 100, 'p95': 200}, 'completed':100,'fresh':100,'no_write':100}
    after = {'total_ms_completed': {'median': None, 'p95': None}, 'completed':0,'fresh':0,'no_write':0}
    grades = {k:100 for k in ('judge_completed','relevant','actionable','no_invented_intake','no_false_save_claim','concise')}
    result = module.decision(before, after, grades, grades)
    assert result['median_10_percent'] is False
    assert result['freshness_and_no_write'] is False


def test_speed_does_not_hide_one_stale_answer():
    before = {'total_ms_completed': {'median': 100, 'p95': 200}, 'completed':100,'fresh':100,'no_write':100}
    after = {**before, 'total_ms_completed': {'median': 70,'p95':150}, 'fresh':99}
    grades = {k:100 for k in ('judge_completed','relevant','actionable','no_invented_intake','no_false_save_claim','concise')}
    result = module.decision(before,after,grades,grades)
    assert result['median_10_percent'] is True
    assert not all(result.values())
