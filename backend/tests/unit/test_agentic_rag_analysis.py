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

def test_reuse_valid_grades_never_retries_a_valid_negative_grade():
    from rejudge_agentic_rag import valid_prior_grades
    rows=[{'attempt_id':'a','condition':'baseline','status':'completed','correct':False,'faithful':True,'reason':'valid negative'},
          {'attempt_id':'b','condition':'agentic','status':'failed','correct':False}]
    reused=valid_prior_grades(rows)
    assert len(reused)==1 and reused[0]['correct'] is False
    with pytest.raises(ValueError): valid_prior_grades(rows+[rows[0]])

def test_pair_judge_blinds_conditions_and_balances_side_order():
    from judge_agentic_pairs import paired_payload
    counts={'baseline':0,'agentic':0}
    for i in range(100):
        key=f'ag-{i:03d}'
        rows=[{'attempt_id':key,'condition':condition,'answer':'answer','context':'evidence','status':'completed'} for condition in ['baseline','agentic']]
        payload,mapping=paired_payload({'attempt_id':key,'question':'question','gold_answer':'gold'},rows)
        counts[mapping['A']]+=1
        assert set(payload)=={'question','gold','A','B'}
        assert 'condition' not in payload['A']
    assert counts=={'baseline':50,'agentic':50}
    with pytest.raises(ValueError): paired_payload({'attempt_id':'ag-000'},rows[:1])

def test_malformed_completed_prior_grade_is_rejudged_instead_of_aborting():
    from rejudge_agentic_rag import valid_prior_grades
    assert valid_prior_grades([{'attempt_id':'a','condition':'baseline','status':'completed','correct':'invalid'}])==[]

def test_pair_resume_reuses_only_complete_hash_bound_pairs():
    from judge_agentic_pairs import valid_prior_pairs, paired_payload, payload_hash
    from hashlib import sha256
    from judge_agentic_pairs import SYSTEM
    case={'attempt_id':'ag-000','question':'q','gold_answer':'g'}
    attempts=[{'attempt_id':'ag-000','condition':c,'status':'completed','answer':'a','context':'c'} for c in ['baseline','agentic']]
    payload,mapping=paired_payload(case,attempts)
    grades=[{'attempt_id':'ag-000','condition':c,'side':side,'status':'completed','correct':False,'faithful':True,'reason':'valid negative',
             'payload_sha256':payload_hash(payload),'rubric_sha256':sha256(SYSTEM.encode()).hexdigest(),
             'judge_model':'gemini-3.1-pro-preview','judge_tokens':2048,'judge_thinking':'low'} for side,c in mapping.items()]
    assert len(valid_prior_pairs(grades,{'ag-000':case},attempts))==2
    assert valid_prior_pairs(grades[:1],{'ag-000':case},attempts)==[]
    with pytest.raises(ValueError): valid_prior_pairs([{**g,'payload_sha256':'wrong'} for g in grades],{'ag-000':case},attempts)

def test_pair_resume_rejects_changed_judge_configuration():
    from judge_agentic_pairs import valid_prior_pairs
    cases={'ag-000':{'attempt_id':'ag-000','question':'q','gold_answer':'g'}}
    attempts=[{'attempt_id':'ag-000','condition':c,'status':'completed','answer':'a','context':'c'} for c in ['baseline','agentic']]
    prior=[{'attempt_id':'ag-000','condition':c,'side':side,'status':'completed','judge_model':'different'} for side,c in [('A','baseline'),('B','agentic')]]
    with pytest.raises(ValueError,match='configuration'): valid_prior_pairs(prior,cases,attempts)
