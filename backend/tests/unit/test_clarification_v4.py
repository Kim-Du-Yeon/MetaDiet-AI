import json
import pytest


def test_new_development_modes_are_disjoint_and_fixed(tmp_path):
    from scripts.eval.clarification_v4 import prepare,read,validate
    p=tmp_path/'experiment';prepare(p)
    dev=read(p/'development.json');old=read(p/'frozen.json')
    assert len(dev)==24 and len(old)==100
    assert all('calculation_mode' not in c['verified_context'] for c in dev)
    assert not {x['question'] for x in dev}&{x['question'] for x in old}
    assert {x['family'] for x in dev}=={'reference_portion','recipe_exact','known_reference','required_controls'}
    assert all(x['required_fields']==['consumed_amount'] for x in dev if x['family']=='reference_portion')
    assert all('ingredient_amounts' in x['required_fields'] for x in dev if x['family']=='recipe_exact')
    assert all(x['expected']=='answer_now' for x in dev if x['family']=='known_reference')
    validate(p)
    source=p/'source-answers.json';value=read(source);value['rows'][0]['answer']='tampered';source.write_text(json.dumps(value),encoding='utf-8')
    with pytest.raises(ValueError,match='evidence'):validate(p)


def test_candidate_distinguishes_reference_and_recipe_and_stays_unapproved(tmp_path):
    from scripts.eval.clarification_v4 import prepare,read
    from app.core.prompt_release_control import validate_snapshot
    p=tmp_path/'experiment';prepare(p);v=read(p/'candidate.json');old=read(p/'source-answers.json')['snapshots']['v3']
    changed={k for k,t in v['texts'].items() if t!=old['texts'][k]}
    assert changed=={'team.base','team.compact_followup'}
    assert '표준 성분표' in v['texts']['team.base'] and '레시피' in v['texts']['team.base']
    with pytest.raises(ValueError):validate_snapshot(v)


def test_adapter_preserves_original_rows_labels_and_isolation(tmp_path):
    from scripts.eval.clarification_v4 import prepare,read
    from scripts.eval import run_clarification_v3 as core
    from scripts.eval.run_clarification_v4 import bound,initialize
    p=tmp_path/'experiment';prepare(p);before=core.initialize
    with bound():
        r=initialize(p,False)
        assert r['labels']==['v1','v3','v4'] and len(r['rows'])==200
        assert {x['condition'] for x in r['rows']}=={'v1','v3'}
        assert core.initialize is initialize
        assert initialize(p,False)==r
    assert core.initialize is before


def test_adoption_needs_zero_extra_questions_and_preserved_quality():
    from scripts.eval.clarification_v4 import select
    def row():return dict(expected=100,judged=100,generation_failures=0,usage_complete=True,correct=100,faithful=100,correct_faithful=100,passed=100,required_recall_numerator=50,unsafe_commitments=0,fresh=100,no_write=100,unnecessary_requests=0,unnecessary_all=0,p95_ms=100,cost_usd=.1)
    v={k:row() for k in ['v1','v3','v4']};v['v1']['passed']=99;v['v3'].update(passed=97,unnecessary_all=3)
    assert select(v)['evaluation_preferred']=='v4'
    v['v4']['faithful']=99
    assert select(v)['evaluation_preferred']=='v1'
    v['v4']=row();v['v4']['unnecessary_all']=1
    assert select(v)['evaluation_preferred']=='v1'


def test_development_gate_rejects_silent_refusal_or_bad_calculation():
    from scripts.eval.clarification_v4 import development_gate
    conditions={k:dict(judged=24,generation_failures=0,usage_complete=True,passed=24,unsafe_commitments=0) for k in ['v3','v4']}
    families={k:{f:dict(expected=6,judged=6,correct=6,faithful=6,focused=6,unnecessary=0) for f in ['reference_portion','recipe_exact','known_reference','required_controls']} for k in ['v3','v4']}
    assert development_gate(conditions,families)
    conditions['v4']['passed']=23
    assert not development_gate(conditions,families)
    conditions['v4']['passed']=24
    families['v4']['reference_portion']['focused']=5
    assert not development_gate(conditions,families)
    families['v4']['reference_portion']['focused']=6;families['v4']['known_reference']['correct']=5
    assert not development_gate(conditions,families)


@pytest.mark.asyncio
async def test_offline_contract_never_seeds_paid_answers(tmp_path):
    from scripts.eval.clarification_v4 import prepare,read
    from scripts.eval.run_clarification_v4 import audit_routes
    p=tmp_path/'experiment';prepare(p);await audit_routes(p)
    assert read(p/'offline-route-audit.json')['passed'] is True
    assert len(read(p/'offline-route-audit.json')['rows'])==48
    assert not (p/'development/answers.json').exists()


def test_threeway_judge_uses_real_v4_labels_and_bindings(tmp_path):
    from scripts.eval.clarification_v4 import prepare,read
    from scripts.eval.run_clarification_v4 import bound,initialize
    from scripts.eval import run_clarification_v3 as core
    from scripts.eval.clarification_execution import request_spec
    from scripts.eval.clarification_cases import request_key
    from app.core.prompt_release_control import _snapshot
    p=tmp_path/'experiment';prepare(p)
    with bound():
        r=initialize(p,False);candidate=read(p/'candidate.json');cases={c['id']:c for c in read(p/'frozen.json')}
        for a in list(r['rows']):
            if a['condition']=='v3':r['rows'].append({**a,'condition':'v4','input_key':request_key(cases[a['case_id']],request_spec(candidate)),'prompt_metadata':_snapshot(candidate).metadata()})
        (p/'main/answers.json').write_text(json.dumps(r),encoding='utf-8')
        entries,requests=core.build_judges(p,False)
        assert len(entries)==len(requests)==100
        assert all(set(e['mapping'].values())=={'v1','v3','v4'} for e in entries)
        r['rows'][-1]['input_key']='tampered';(p/'main/answers.json').write_text(json.dumps(r),encoding='utf-8')
        with pytest.raises(ValueError,match='identity'):initialize(p,False)


def test_development_summary_never_claims_independent_holdout(tmp_path):
    from scripts.eval.clarification_v4 import prepare
    from scripts.eval.run_clarification_v4 import summarize_stage
    p=tmp_path/'experiment';prepare(p)
    assert summarize_stage(p,True)['not_independent_holdout'] is True
