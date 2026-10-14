import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts/eval'))
from summarize_brief_public100 import gates
from summarize_latency100 import RUBRIC


@pytest.mark.parametrize('regression', ['none', 'p95', 'failure', 'quality', 'missing_model_time'])
def test_brief_adoption_rejects_tail_failure_or_quality_regression(regression):
    groups = {p: dict(completed=100, fresh=100, no_write=100, unexpected_proposals=0,
                     duration_ms_all_attempts=dict(median=8000 if p == 'before' else 7000, p95=10000))
              for p in ('before', 'after')}
    grades = {p: dict(judge_completed=100, **{k: 100 for k in RUBRIC}) for p in groups}
    stages = {p: {'model_meal': {'median': 3000 if p == 'before' else 2500}} for p in groups}
    if regression == 'p95': groups['after']['duration_ms_all_attempts']['p95'] = 10001
    if regression == 'failure': groups['after']['completed'] = 99
    if regression == 'quality': grades['after']['actionable'] = 99
    if regression == 'missing_model_time': stages['after']['model_meal']['median'] = None
    assert all(gates(groups, grades, stages).values()) == (regression == 'none')
