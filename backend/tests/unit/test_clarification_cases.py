import copy
import pytest
from scripts.eval.clarification_cases import validate_cases,request_key,can_reuse,summarize


def example(required=False):
    return {'id':'a','split':'evaluation','family':'missing_label' if required else 'meal_choice','question':'단백질 수치를 비교해줘' if required else '그럼 점심은 뭘 먹을까?', 'verified_context':{'scope':'fresh_current_request','calories':600,'target':2000},'recent_messages':[], 'expected':'ask_required' if required else 'answer_now','required_fields':['product_label'] if required else [],'rationale':'숫자 비교는 제품 표가 필요함' if required else '일반 조언 가능','provenance':'synthetic_control'}


def test_essential_question_requires_identified_missing_field():
    c=example(True);c['required_fields']=[]
    with pytest.raises(ValueError,match='missing'):validate_cases([c],balanced=False)


def test_reuse_requires_full_input_prompt_model_and_settings_match():
    c=example();spec={'prompt_identity':'abc','model':'flash','settings':{'thinking':'low'}}
    row={'status':'completed','input_key':request_key(c,spec),'answer':'식사 조언'}
    assert can_reuse(row,c,spec)
    changed=copy.deepcopy(c);changed['verified_context']['calories']=601
    assert not can_reuse(row,changed,spec)
    assert not can_reuse(row,c,{**spec,'prompt_identity':'def'})
    assert not can_reuse(row,c,{**spec,'settings':{'thinking':'high'}})
    assert not can_reuse({'status':'failed','input_key':row['input_key']},c,spec)


def test_ungraded_or_failed_results_never_become_passes():
    cases=[example(),{**example(True),'id':'b'}]
    result=summarize(cases,[],[])
    assert result['expected']==2 and result['judged']==0 and result['passed']==0
    assert not result['gate_passed']


def test_question_mark_is_not_the_semantic_metric():
    cases=[example()]
    attempts=[{'case_id':'a','status':'completed','answer':'좋은 선택입니다?','fresh':True,'no_write':True}]
    grades=[{'case_id':'a','status':'completed','correct':True,'faithful':True,'unnecessary_request':False,'focused_required_question':False,'unsafe_commitment':False}]
    assert summarize(cases,attempts,grades)['passed']==1
    grades[0]['unnecessary_request']=True
    assert summarize(cases,attempts,grades)['passed']==0


def test_required_recall_not_satisfied_by_silence():
    cases=[example(True)]
    attempt={'case_id':'a','status':'completed','answer':'확인할 수 없습니다','fresh':True,'no_write':True}
    grade={'case_id':'a','status':'completed','correct':True,'faithful':True,'unnecessary_request':False,'focused_required_question':False,'unsafe_commitment':False}
    assert summarize(cases,[attempt],[grade])['required_recall_numerator']==0
    grade['focused_required_question']=True
    assert summarize(cases,[attempt],[grade])['required_recall_numerator']==1


def test_frozen_cohort_is_balanced_and_development_is_disjoint():
    import json,hashlib
    from pathlib import Path
    from scripts.eval.followup_question_experiment import ROOT
    folder=ROOT/'docs/prompt_control/clarification-balanced'
    cases=json.loads((folder/'frozen100.json').read_text(encoding='utf-8'))
    dev=json.loads((folder/'development20.json').read_text(encoding='utf-8'))
    protocol=json.loads((folder/'protocol.json').read_text(encoding='utf-8'))
    assert validate_cases(cases) and len(dev)==20
    assert not {x['id'] for x in cases}&{x['id'] for x in dev}
    assert not {x['question'] for x in cases}&{x['question'] for x in dev}
    assert hashlib.sha256((folder/'frozen100.json').read_bytes()).hexdigest()==protocol['frozen_sha256']


def test_saved_examples_match_original_source_bytes_and_json_pointer():
    import json,hashlib
    from scripts.eval.followup_question_experiment import ROOT
    rows=json.loads((ROOT/'docs/prompt_control/clarification-balanced/saved-examples10.json').read_text(encoding='utf-8'))
    assert len(rows)==10
    for row in rows:
        path=ROOT/row['source'];assert hashlib.sha256(path.read_bytes().replace(b'\r\n',b'\n')).hexdigest()==row['source_lf_sha256']
        v=json.loads(path.read_text(encoding='utf-8'))
        for key in row['pointer'].strip('/').split('/'):v=v[int(key)] if isinstance(v,list) else v[key]
        assert row['answer']==v.get('answer',v.get('response'))


def test_grade_binding_changes_with_answer_or_rubric():
    from scripts.eval.clarification_cases import grade_key
    c=example();key=grade_key(c,'밥과 채소','a'*64)
    assert key!=grade_key(c,'밥만','a'*64)
    assert key!=grade_key(c,'밥과 채소','b'*64)


def test_100_percent_freshness_is_a_separate_hard_gate():
    cases=[{**example(i>=50),'id':str(i)} for i in range(100)]
    attempts=[{'case_id':c['id'],'status':'completed','fresh':c['id']!='0','no_write':True} for c in cases]
    grades=[{'case_id':c['id'],'status':'completed','correct':True,'faithful':True,'unnecessary_request':False,'focused_required_question':True,'unsafe_commitment':False} for c in cases]
    result=summarize(cases,attempts,grades)
    assert not result['gate_passed']
