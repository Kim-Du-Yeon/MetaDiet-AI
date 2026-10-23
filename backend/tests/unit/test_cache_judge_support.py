from scripts.eval.cache_judge_support import pair_payload,needs_grade

def test_failed_condition_does_not_suppress_completed_counterpart():
    payload=pair_payload({'question':'q','gold_answer':'gold','context':'source'}, {'ordinary':{'status':'completed','answer':'real answer'},'explicit':{'status':'failed','answer':'partial output'}},['ordinary','explicit'])
    assert payload['a']=='real answer' and payload['b']==''
    assert needs_grade({'status':'failed','error':{'reason':'generation_failed_or_truncated'}})
    assert not needs_grade({'status':'completed'})

    assert needs_grade({'status':'failed','error':{'reason':'timeout'}})
    assert not needs_grade({'status':'failed','error':{'reason':'quota_exhausted'}})
