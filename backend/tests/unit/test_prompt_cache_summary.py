import copy
import pytest
from scripts.eval.analyze_prompt_cache import analyze

def test_cache_summary_keeps_failure_and_missing_grades_in_denominator():
    paired={'scope':'synthetic','rows':[]};judges={'model':'gemini-3.1-pro-preview','rows':[]}
    for i in range(100):
        for label in ['ordinary','explicit']:
            paired['rows'].append({'case_id':str(i),'condition':label,'status':'completed','ms':100,'ttft_ms':20,'cache_stage':'ordinary' if label=='ordinary' else 'reuse','model_cost_usd':.01 if label=='ordinary' else .001})
        judges['rows'].append({'case_id':str(i),'status':'completed','mapping':{'a':'ordinary','b':'explicit'},'grades':{'a':{'correct':True,'faithful':True},'b':{'correct':True,'faithful':True}},'usage':[]})
    paired['rows'][-1].update(status='failed',model_cost_usd=None,ttft_ms=None)
    judges['rows'][-1]['status']='failed'
    result=analyze(paired,judges)
    assert result['conditions']['explicit']['failures']==1
    assert result['conditions']['ordinary']['correct']==99
    assert result['conditions']['explicit']['correct']==99
    assert not result['cache_adoption']
    assert not result['gates']['complete_usage']
    judges['rows'][-1]['status']='completed'
    repaired=analyze(paired,judges)
    assert repaired['conditions']['ordinary']['correct']==100
    assert repaired['conditions']['explicit']['correct']==99
    assert repaired['conditions']['explicit']['graded']==99
    assert repaired['gates']['all_pairs_judged']
    with pytest.raises(ValueError):analyze({'scope':'x','rows':paired['rows'][:-1]},judges)
