import importlib.util
from pathlib import Path


def load_harness():
    spec=importlib.util.spec_from_file_location('feedback_scale',Path(__file__).resolve().parents[2]/'scripts/check_feedback_scale.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_frozen_cases_cover_filters_and_failures_stay_in_denominator():
    module=load_harness()
    cases=module.frozen_cases()
    assert len(cases)==100 and len({str(case) for case in cases})==100
    result=module.summarize([{'ok':True,'ms':1},{'ok':False,'ms':10,'status':503}])
    assert result['attempts']==2 and result['passed']==1 and result['failed']==1
    assert result['failure_rate']==0.5


def test_incomplete_races_are_not_reported_as_a_perfect_run():
    result=load_harness().summarize_races([{'ok':True,'http_statuses':[200,409]}])
    assert result['planned_rounds']==100 and result['completed_rounds']==1
    assert result['failed_rounds']==99 and result['passed']==1
