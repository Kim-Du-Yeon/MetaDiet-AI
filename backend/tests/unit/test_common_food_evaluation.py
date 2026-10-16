import importlib.util
from pathlib import Path


def harness():
    path=Path(__file__).resolve().parents[2]/'scripts/eval/evaluate_common_foods.py'
    spec=importlib.util.spec_from_file_location('common_food_eval',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_cases_are_100_different_foods_not_alias_repetitions():
    cases,digest=harness().load_cases()
    assert len(cases)==100 and len({c['food'] for c in cases})==100
    assert digest=='777d033d04784180e9895472811a8474e791a61c463f0f3e6ecc65c95dfd4f8e'
    assert len({c['category'] for c in cases})==10


def test_only_valid_complete_pending_intake_counts_as_auto_card():
    module=harness()
    meal={'quantity_g':200,'calories':390,'carbs_g':9.5,'protein_g':24.3,'fat_g':28.4,
          'food_id':'mfds:fixture','food_name':'제육볶음'}
    result={'awaiting_confirmation':True,'pending_proposal':{'status':'pending','kind':'intake',
        'payload':{'kind':'intake','meals':[meal]}},'execution_status':'completed'}
    assert module.classify_result(result)=='auto_card'
    result['pending_proposal']['payload']['meals'][0]['calories']=None
    assert module.classify_result(result)=='invalid_card'


def test_choice_timeout_missing_and_blocked_are_not_hidden():
    module=harness()
    assert module.classify_result({'food_selection':{'mode':'meal_choices','items':[{}]}})=='manual_choice'
    assert module.classify_result({'food_selection':{'items':[{'candidates':[{}]}]}})=='product_choice'
    assert module.classify_result({'execution_status':'blocked'})=='blocked'
    summary=module.summarize([{'outcome':'auto_card'},{'outcome':'timeout'},{'outcome':'error'}],100)
    assert summary['planned']==100 and summary['completed_attempts']==3 and summary['not_attempted']==97
    assert summary['auto_card_count']==1 and summary['auto_card_rate_planned']==.01
