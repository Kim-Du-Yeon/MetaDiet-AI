from scripts.eval.analyze_prompt_control import analyze

def test_failures_and_missing_judges_are_in_denominator():
    result=analyze({'rows':[]},{'rows':[]})
    assert result['selection']=='v1' and not result['candidate_passed']
    assert result['summary']['v1']['quality_percent']==0
    assert result['summary']['v2']['failure_percent']==100

def test_ungraded_completed_answer_does_not_count_as_quality():
    result=analyze({'rows':[{'case_id':'x','condition':'v1','status':'completed','fresh':True,'no_write':True,'ms':10,'cost_usd':0,'usage':[]}]},{'rows':[]})
    assert result['summary']['v1']['quality_percent']==0
    assert not result['summary']['v1']['judge_complete']

# Remote approval never silently accepts incomplete judge usage.
def test_release_approval_rejects_partial_comparison():
    import importlib.util
    from pathlib import Path
    path=Path(__file__).resolve().parents[2]/'scripts/approve_prompt_release.py'
    spec=importlib.util.spec_from_file_location('approve_prompts',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    import pytest
    with pytest.raises(ValueError):module.approved_selection({'selection':'v1','summary':{'v1':{'attempts':99,'judge_complete':False,'usage_complete':True}}})
