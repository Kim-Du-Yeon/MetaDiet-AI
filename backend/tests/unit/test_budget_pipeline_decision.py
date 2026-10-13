import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts/eval'))
from summarize_budget_pipeline100 import decision


def test_storage_only_improvement_cannot_override_total_or_freshness_regression():
    base = dict(total_ms_completed={'median':1000,'p95':1500},completed=100,fresh=100,no_write=100)
    candidate = {**base, 'total_ms_completed':{'median':990,'p95':1300}}
    storage = {'baseline':{'median':300,'n':100},'pipeline':{'median':100,'n':100}}
    grades = {'baseline':{'judge_completed':100},'pipeline':{'judge_completed':100}}
    assert decision(base,candidate,storage,grades)['total_median_5_percent'] is False
    candidate.update(total_ms_completed={'median':900,'p95':1300},fresh=99)
    assert decision(base,candidate,storage,grades)['completion_freshness_no_write'] is False


def test_missing_storage_timings_cannot_be_adopted():
    base = dict(total_ms_completed={'median':1000,'p95':1500},completed=100,fresh=100,no_write=100)
    candidate = {**base, 'total_ms_completed':{'median':800,'p95':1300}}
    storage = {'baseline':{'median':300,'n':100},'pipeline':{'median':100,'n':99}}
    grades = {'baseline':{'judge_completed':100},'pipeline':{'judge_completed':100}}
    assert not all(decision(base,candidate,storage,grades).values())


def test_equal_judge_failures_are_not_quality_evidence():
    base = dict(total_ms_completed={'median':1000,'p95':1500},completed=100,fresh=100,no_write=100)
    candidate = {**base, 'total_ms_completed':{'median':800,'p95':1300}}
    storage = {'baseline':{'median':300,'n':100},'pipeline':{'median':100,'n':100}}
    grades = {'baseline':{'judge_completed':0},'pipeline':{'judge_completed':0}}
    assert not all(decision(base,candidate,storage,grades).values())
