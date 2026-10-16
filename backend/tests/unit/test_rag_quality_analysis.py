import pytest


def test_analysis_rejects_a_missing_repeat(tmp_path):
    from scripts.eval.analyze_rag_memory_quality import compare
    with pytest.raises(ValueError):
        compare(tmp_path)


def test_full_denominator_does_not_exclude_unreturned_context():
    from scripts.eval.analyze_rag_memory_quality import rates
    result=rates([{'status':'completed','page_hit':True,'excerpt_hit':True},
                  {'status':'failed','seconds':90}])
    assert result['page_hit']==.5 and result['excerpt_hit']==.5


def test_missing_judge_is_unknown_not_a_zero_quality_score():
    from scripts.eval.rag_validation_support import summarize_rows
    assert summarize_rows([{'status':'completed','seconds':1}])['supported_correct_rate'] is None


def test_all_failed_conditions_cannot_pass_relative_screen(tmp_path):
    import json
    from scripts.eval.analyze_rag_memory_quality import compare
    from scripts.eval.rag_validation_support import digest
    cases=[{'id':str(i),'question':str(i),'case_group':str(i//2),'language':'en',
            'review_status':'reviewed','split':'development'} for i in range(40)]
    frozen={'cases':cases,'translations':{str(i):str(i) for i in range(40)}}
    frozen['identity']=digest(frozen)
    (tmp_path/'frozen.json').write_text(json.dumps(frozen))
    for mode in ('dense_fallback','hybrid'):
        for repeat in range(3):
            report={'identity':frozen['identity'],'mode':mode,'memory':{
                'peak_rss_bytes':100,'private_bytes':100},'rows':[
                    {'id':c['id'],'language':'en','repeat':repeat,'status':'failed',
                     'seconds':90} for c in cases]}
            (tmp_path/f'{mode}-r{repeat}.json').write_text(json.dumps(report))
    assert not compare(tmp_path)['retrieval_development_screen_passed']
