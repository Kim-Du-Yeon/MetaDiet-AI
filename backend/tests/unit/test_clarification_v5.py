"""Closing-offer regression and essential-clarification controls."""
import copy
import pytest


def test_development_has100_unique_cases_and50_required_controls():
    from scripts.eval.clarification_v5 import cases
    c=cases();assert len(c)==len({v['question'] for v in c})==100
    assert sum(v['expected']=='ask_required' for v in c)==50
    assert c[0]['id']=='v5-stale-00'
    assert all(v['split']=='development' for v in c)


def test_prompt_changes_only_reviewed_two_templates():
    from scripts.eval.clarification_v5 import candidate_snapshot,BASE,read,CLOSING_RULE
    base=read(BASE/'approved.json');candidate=candidate_snapshot(base)
    assert {k for k in base['texts'] if base['texts'][k]!=candidate['texts'][k]}=={'team.base','team.compact_followup'}
    for n in ['team.base','team.compact_followup']:
        assert candidate['texts'][n]==base['texts'][n]+'\n'+CLOSING_RULE
        assert '필수 정보 질문은 유지' in candidate['texts'][n]


def test_gate_keeps_required_quality_and_reduces_closing_offers():
    from scripts.eval.clarification_v5 import select
    r=dict(expected=100,attempted=100,judged=100,generation_failures=0,usage_complete=True,correct=100,faithful=100,passed=100,required_recall_numerator=50,unsafe_commitments=0,fresh=100,no_write=100,unnecessary_all=0,p95_ms=100,cost_usd=.1)
    v={'v4':copy.deepcopy(r),'v5':copy.deepcopy(r)};v['v4'].update(passed=99,unnecessary_all=1)
    assert select(v)['candidate_passed']
    for field,bad in [('required_recall_numerator',49),('correct',97),('faithful',97),('fresh',99),('no_write',99),('unsafe_commitments',1),('unnecessary_all',1),('p95_ms',126),('usage_complete',False)]:
        other=copy.deepcopy(v);other['v5'][field]=bad;assert not select(other)['candidate_passed'],field


def test_saved_regression_reuse_requires_identical_request():
    from scripts.eval.clarification_v5 import cases,BASE,read,reuse_regression
    base=read(BASE/'approved.json');row=reuse_regression(cases()[0],base)
    assert row['condition']=='v4' and '필요하시면' in row['answer']
    c=copy.deepcopy(cases()[0]);c['question']+='changed'
    with pytest.raises(ValueError):reuse_regression(c,base)


def test_trace_metadata_contains_identity_not_question_or_health_values():
    from scripts.eval.clarification_v5 import BASE,read
    from scripts.eval.run_clarification_v5 import trace_metadata
    m=trace_metadata('synthetic-case','v5',read(BASE/'approved.json'))
    assert m['prompt_release_commit'] and m['condition']=='v5' and m['synthetic']
    assert not {'question','user_id','thread_id','calories','target','api_key'}&set(m)


def test_every_primary_call_must_use_its_assigned_prompt():
    from scripts.eval.v5_evidence_contract import trace_templates
    from scripts.eval.clarification_v5 import BASE,read,candidate_snapshot
    snapshots={'v4':read(BASE/'approved.json'),'v5':candidate_snapshot(read(BASE/'approved.json'))}
    question='synthetic question';import json
    good=[{'type':'system','content':snapshots['v5']['texts']['team.base']+'\nrole'},{'type':'human','content':json.dumps({'message':question})}]
    assert trace_templates([good],'v5',snapshots,question)=={'team.base'}
    bad=copy.deepcopy(good);bad[0]['content']=snapshots['v4']['texts']['team.base']+'\nrole'
    with pytest.raises(ValueError):trace_templates([good,bad],'v5',snapshots,question)
    with pytest.raises(ValueError):trace_templates([good],'v5',snapshots,'different question')


def test_batch_provenance_refuses_wrong_model_or_wire():
    from scripts.eval.v5_evidence_contract import check_batch
    import hashlib,json
    entries=[{'key':'synthetic'}];wire={'test':'strict serialized body'}
    job={'model':'gemini-3.1-pro-preview','state':'JOB_STATE_SUCCEEDED','collected':True,'entries':entries,'entries_sha256':hashlib.sha256(json.dumps(entries,sort_keys=True,ensure_ascii=False).encode()).hexdigest()}
    check_batch(job,wire,wire,entries)
    wrong=copy.deepcopy(job);wrong['model']='gemini-3.8-flash'
    with pytest.raises(ValueError):check_batch(wrong,wire,wire,entries)
    with pytest.raises(ValueError):check_batch(job,{'changed':True},wire,entries)


def test_bounded_baseline_usage_does_not_inflate_cost_comparison():
    from scripts.eval.clarification_v5 import select
    r=dict(expected=100,attempted=100,judged=100,generation_failures=0,usage_complete=True,correct=100,faithful=100,passed=100,required_recall_numerator=50,unsafe_commitments=0,fresh=100,no_write=100,unnecessary_all=0,p95_ms=100,cost_usd=.1)
    a=copy.deepcopy(r);a.update(judged=99,generation_failures=1,usage_complete=False,usage_accounted=True,correct=99,faithful=99,passed=98,unnecessary_all=1,cost_usd=.08,cost_upper_bound_usd=.2)
    b=copy.deepcopy(r);b['cost_usd']=.101
    assert not select({'v4':a,'v5':b})['candidate_passed']
    b['cost_usd']=.09;assert select({'v4':a,'v5':b})['candidate_passed']


def test_timeout_accounting_keeps_unknown_usage_and_requires_real_reservation(tmp_path,monkeypatch):
    from scripts.eval import v5_evidence_contract as c
    from scripts.eval.cache_artifacts import save_json
    row={'case_id':'synthetic','condition':'v4','cost_usd':None,'input_key':'bound','error':{'reason':'timeout'}}
    tickets={'ticket':{'stage':'comparison','micros':2845,'settled':0}}
    save_json(tmp_path/'bounded-timeouts.json',{'cases':{'synthetic':{'input_key':'bound','tickets':tickets}}})
    monkeypatch.setattr(c,'reservations',lambda:tickets)
    assert c.bounded_costs(tmp_path,[row])=={'synthetic':.002845}
    assert row['cost_usd'] is None
    monkeypatch.setattr(c,'reservations',lambda:{})
    with pytest.raises(ValueError):c.bounded_costs(tmp_path,[row])


def test_partial_timeout_keeps_known_cost_and_adds_only_unknown_upper(tmp_path,monkeypatch):
    from scripts.eval import v5_evidence_contract as c
    from scripts.eval.cache_artifacts import save_json
    row={'case_id':'partial','condition':'v4','status':'failed','cost_usd':.001,'input_key':'bound','error':{'reason':'timeout'}}
    tickets={'ticket':{'stage':'comparison','micros':4000,'settled':1}}
    save_json(tmp_path/'bounded-timeouts.json',{'cases':{'partial':{'input_key':'bound','tickets':tickets}}})
    monkeypatch.setattr(c,'reservations',lambda:tickets)
    assert c.bounded_costs(tmp_path,[row])=={'partial':.003}
    assert row['cost_usd']==.001


def test_unknown_baseline_timeout_is_reportable_but_not_approvable(tmp_path,monkeypatch):
    from scripts.eval import v5_evidence_contract as c
    row={'case_id':'unknown','condition':'v4','status':'failed','cost_usd':None,'input_key':'bound','error':{'reason':'timeout'}}
    monkeypatch.setattr(c,'reservations',lambda:{})
    with pytest.raises(ValueError):c.bounded_costs(tmp_path,[row])
    assert c.bounded_costs(tmp_path,[row],allow_unaccounted=True)=={}


@pytest.mark.parametrize('mutation',['cohort','source_inventory'])
def test_protocol_cannot_self_attest_changed_cohort_or_history(tmp_path,mutation):
    from scripts.eval import clarification_v5 as p
    from scripts.eval.cache_artifacts import save_json
    from app.core.prompt_release_control import digest
    candidate=p.read(p.FOLDER/'candidate.json');cohort=p.cases();protocol=p.read(p.FOLDER/'protocol.json')
    protocol['code_sha256']=p.code_sha()
    if mutation=='cohort':
        cohort[0]['question']+=' changed';protocol['cases_sha256']=digest(cohort)
    else:
        protocol['source_hashes']['approved.json']='0'*64
    for n,v in [('candidate.json',candidate),('frozen.json',cohort),('protocol.json',protocol)]:save_json(tmp_path/n,v)
    with pytest.raises(ValueError):p.validate(tmp_path)
