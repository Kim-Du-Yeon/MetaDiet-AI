"""Policy-v2 unit checks; fake metrics are not experimental results."""
import copy
import pytest


def metrics():
    row=dict(expected=100,attempted=100,judged=100,generation_failures=0,usage_complete=True,correct=100,faithful=100,passed=100,required_recall_numerator=50,unsafe_commitments=0,fresh=100,no_write=100,unnecessary_all=0,p95_ms=100,cost_usd=.1)
    values={'v1':copy.deepcopy(row),'v4':copy.deepcopy(row)}
    values['v1'].update(judged=98,generation_failures=2,correct=98,faithful=97,passed=92,fresh=98,no_write=98,unnecessary_all=5)
    return values


def test_review_separates_baseline_failure_from_candidate_safety():
    from scripts.eval.clarification_approval_review import select
    from scripts.eval.clarification_holdout import select as original
    v=metrics()
    assert not original(v)['holdout_passed']
    assert select(v)['candidate_approved']
    assert select(v)['baseline_failures_retained']==2


@pytest.mark.parametrize('field,value',[('judged',99),('generation_failures',1),('correct',97),('faithful',97),('passed',97),('required_recall_numerator',48),('unsafe_commitments',1),('fresh',99),('no_write',99),('unnecessary_all',3),('p95_ms',126),('cost_usd',.126),('usage_complete',False)])
def test_review_retains_every_candidate_safety_boundary(field,value):
    from scripts.eval.clarification_approval_review import select
    v=metrics(); v['v4'][field]=value
    assert not select(v)['candidate_approved']


def test_baseline_missing_attempts_or_usage_does_not_become_a_free_pass():
    from scripts.eval.clarification_approval_review import select
    v=metrics(); v['v1']['attempted']=99
    assert not select(v)['candidate_approved']
    v=metrics(); v['v1']['usage_complete']=False
    assert not select(v)['candidate_approved']


def test_review_policy_and_original_evidence_are_frozen():
    from scripts.eval.clarification_approval_review import validate_review,REVIEW
    assert validate_review(REVIEW)['suite']=='clarification-two-template-holdout-v1'


def test_review_refuses_edited_policy(tmp_path):
    from scripts.eval.clarification_approval_review import validate_review,REVIEW
    import json
    policy=json.loads((REVIEW/'policy.json').read_text(encoding='utf-8'));policy['candidate_correct_min']=90
    (tmp_path/'policy.json').write_text(json.dumps(policy),encoding='utf-8')
    with pytest.raises(ValueError,match='policy'):validate_review(tmp_path)


def test_real_saved_evidence_verifies_without_generation_or_regrading():
    from scripts.eval import clarification_approval_review as r
    from scripts.prompt_release_workflow import verify_evidence,verify_receipt
    from app.core.prompt_service import approval_key
    candidate=r.read(r.EVIDENCE/'candidate.json');key=approval_key()
    receipt=verify_evidence(candidate,r.REVIEW,key)
    assert receipt['approved'] and receipt['analysis']['conditions']['v1']['judged']==98
    assert receipt['analysis']['conditions']['v4']['judged']==100
    assert receipt['analysis']['decision']['baseline_failures_retained']==2
    assert verify_receipt(candidate,r.REVIEW,receipt,key)==receipt
    receipt['analysis']['conditions']['v4']['correct']=99
    with pytest.raises(ValueError,match='changed'):verify_receipt(candidate,r.REVIEW,receipt,key)


def test_missing_original_evidence_cannot_be_approved(monkeypatch,tmp_path):
    from scripts.eval import clarification_approval_review as r
    monkeypatch.setattr(r,'EVIDENCE',tmp_path)
    with pytest.raises(ValueError,match='Original evidence'):r.validate_review(r.REVIEW)
