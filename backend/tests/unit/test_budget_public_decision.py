import copy
import json
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts/eval'))
from summarize_budget_public100 import public_gates
import budget_public100


def evidence():
    base = dict(total_ms_completed={'median':1000,'p95':1500,'n':100},completed=100,fresh=100,no_write=100,unexpected_proposals=0)
    candidate = {**base,'total_ms_completed':{'median':800,'p95':1300,'n':100}}
    storage = {'baseline':{'median':300,'n':100},'pipeline':{'median':100,'n':100}}
    grades = {'baseline':{'judge_completed':100,'relevant':100},'pipeline':{'judge_completed':100,'relevant':100}}
    return base,candidate,storage,grades


def test_valid_public_improvement_passes():
    assert all(public_gates(*evidence()).values())


@pytest.mark.parametrize('key',['completed','fresh','no_write'])
def test_equal_failures_cannot_count_as_success(key):
    args = copy.deepcopy(evidence())
    args[0][key] = args[1][key] = 99
    assert not all(public_gates(*args).values())


def test_unexpected_proposal_blocks_adoption():
    args = evidence()
    args[1]['unexpected_proposals'] = 1
    assert not all(public_gates(*args).values())


def test_partial_response_timings_block_adoption():
    args = evidence()
    args[1]['total_ms_completed']['n'] = 99
    assert not all(public_gates(*args).values())


def test_missing_stats_are_retried_not_treated_as_zero(monkeypatch):
    responses = iter([{}, {'today_calories':600,'target_calories':2000}])
    monkeypatch.setattr(budget_public100,'json_request',lambda *a,**k:next(responses))
    monkeypatch.setattr(budget_public100.time,'sleep',lambda delay:None)
    errors=[]
    budget_public100.verify_state('unused',600,2000,errors)
    assert errors==[{'attempt':1,'reason':'public_stats_missing'}]


def test_wrong_stats_fail_instead_of_being_retried(monkeypatch):
    monkeypatch.setattr(budget_public100,'json_request',lambda *a,**k:{'today_calories':0,'target_calories':2000})
    with pytest.raises(AssertionError,match='Fixture state mismatch'):
        budget_public100.verify_state('unused',600,2000,[])


def test_auth_failure_is_not_retried(monkeypatch):
    def unauthorized(*args,**kwargs):
        raise RuntimeError('HTTP 401 GET endpoint')
    monkeypatch.setattr(budget_public100,'json_request',unauthorized)
    with pytest.raises(RuntimeError,match='401'):
        budget_public100.verify_state('unused',600,2000,[])


def test_timed_attempt_survives_postflight_failure(tmp_path):
    output=tmp_path/'evidence.json'
    report={'rows':[]}
    def failed_read():
        assert len(json.loads(output.read_text())['rows'])==1
        raise RuntimeError('read unavailable')
    budget_public100.persist_capture(report,output,{'pair':0,'status':'completed'},([],[]),failed_read)
    saved=json.loads(output.read_text())['rows']
    assert len(saved)==1 and saved[0]['no_write'] is False
    assert saved[0]['postflight_verified'] is False
    assert saved[0]['postflight_error_type']=='RuntimeError'
