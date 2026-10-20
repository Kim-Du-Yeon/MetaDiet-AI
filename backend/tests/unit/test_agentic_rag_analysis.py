import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts/eval'))
from analyze_agentic_rag import analyze


def fixture():
    rows=[]; grades=[]
    for i in range(100):
        for mode in ['baseline','agentic']:
            rows.append({'attempt_id':str(i),'condition':mode,'status':'completed','ms':100,
                         'support':True,'cost_complete':True,'known_model_cost_usd':.001})
            grades.append({'attempt_id':str(i),'condition':mode,'status':'completed',
                           'correct':mode=='agentic' or i<98,'faithful':True,'known_cost_usd':.001})
    return rows,grades

def test_complete_matching_improvement_can_pass():
    r,g=fixture()
    assert analyze(r,g)['rollout_gate']

def test_incomplete_cost_or_judge_failure_blocks_rollout():
    r,g=fixture(); r[1]['cost_complete']=False
    assert not analyze(r,g)['rollout_gate']
    r,g=fixture(); g[1]['status']='failed'
    assert not analyze(r,g)['rollout_gate']

def test_failures_stay_in_denominator_and_missing_pairs_rejected():
    r,g=fixture(); r[1]['status']='failed'
    result=analyze(r,g)
    assert result['agentic']['attempts']==100
    assert result['agentic']['failure_rate']==.01
    assert result['agentic']['correctness']==.99
    with pytest.raises(ValueError): analyze(r[:-1],g)
    with pytest.raises(ValueError): analyze(r+[r[0]],g)

def test_daily_quota_circuit_detects_only_daily_limit():
    from benchmark_agentic_rag import daily_quota
    assert daily_quota(RuntimeError('429 GenerateRequestsPerDayPerProjectPerModel limit 250'))
    assert not daily_quota(RuntimeError('429 GenerateRequestsPerMinutePerProjectPerModel'))
    assert not daily_quota(RuntimeError('402 credits exhausted'))

def test_incomplete_judging_is_not_presented_as_a_quality_score():
    r,g=fixture(); g[1]['status']='not_attempted_quota'
    report=analyze(r,g)
    assert report['agentic']['correctness'] is None
    assert report['agentic']['correctness_lower_bound']==.99
    assert not report['rollout_gate']
