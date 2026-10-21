import json
from types import SimpleNamespace
import pytest
from scripts.eval.cache_eval_budget import CacheAccounting
from scripts.eval.eval_budget import BudgetStop

def response(value):return SimpleNamespace(body=json.dumps(value))

def test_cache_creation_priced_with_full_ttl_and_unknown_references_blocked():
    account=CacheAccounting()
    body={'model':'models/gemini-3.8-flash','systemInstruction':{'parts':[{'text':'static'}]},'ttl':'300s'}
    assert account.bound('post','cachedContents',body)>0
    value=response({'name':'cachedContents/x','usageMetadata':{'totalTokenCount':1500}})
    cost=account.actual('cachedContents',body,value)
    assert cost==pytest.approx(1500*(.75+.5/12)/1e6)
    request={'cachedContent':'cachedContents/x','contents':[{'parts':[{'text':'fresh question'}]}],'generationConfig':{'maxOutputTokens':512}}
    assert account.bound('post','models/gemini-3.8-flash:generateContent',request)>cost
    usage=response({'usageMetadata':{'promptTokenCount':1600,'cachedContentTokenCount':1500,'candidatesTokenCount':20,'thoughtsTokenCount':10}})
    assert account.actual('models/gemini-3.8-flash:generateContent',request,usage)==pytest.approx((100*.75+1500*.075+30*3.75)/1e6)
    request['cachedContent']='cachedContents/unknown'
    with pytest.raises(BudgetStop):account.bound('post','models/gemini-3.8-flash:generateContent',request)

def test_cache_unknown_usage_and_invalid_ttl_do_not_get_free_cost():
    account=CacheAccounting()
    with pytest.raises(BudgetStop):account.bound('post','cachedContents',{'model':'models/gemini-3.8-flash','ttl':'90000s'})
    assert account.actual('cachedContents',{'model':'gemini-3.8-flash','ttl':'300s'},response({'name':'cachedContents/x'})) is None

@pytest.mark.asyncio
async def test_stream_guard_settles_final_usage_and_blocks_unknown_cache(tmp_path):
    from scripts.eval.cache_eval_budget import install_cache_guard
    from scripts.eval.eval_budget import Budget
    class Client:
        def request(*args):raise AssertionError()
        async def async_request(*args):raise AssertionError()
        async def async_request_streamed(self,method,path,body,options):
            assert options['retry_options']=={'attempts':1}
            async def values():
                yield response({'candidates':[{'content':{'parts':[{'text':'ok'}]}}]})
                yield response({'usageMetadata':{'promptTokenCount':30,'candidatesTokenCount':5}})
            return values()
    budget=Budget(tmp_path/'ledger.sqlite');account=CacheAccounting()
    install_cache_guard(budget,'comparison',account,Client)
    stream=await Client().async_request_streamed('post','models/gemini-3.8-flash:streamGenerateContent?alt=sse',{'contents':[{'parts':[{'text':'x'}]}],'generationConfig':{'maxOutputTokens':100}},None)
    assert len([value async for value in stream])==2
    assert budget.summary()['committed_usd']==pytest.approx(.000042,abs=.000001)

@pytest.mark.asyncio
async def test_interrupted_stream_keeps_full_reservation_after_interim_usage(tmp_path):
    from scripts.eval.cache_eval_budget import install_cache_guard
    from scripts.eval.eval_budget import Budget
    class Client:
        def request(*args):raise AssertionError()
        async def async_request(*args):raise AssertionError()
        async def async_request_streamed(self,*args):
            async def values():
                yield response({'usageMetadata':{'promptTokenCount':30,'candidatesTokenCount':1}})
                raise TimeoutError('stream interrupted')
            return values()
    budget=Budget(tmp_path/'ledger.sqlite');account=CacheAccounting()
    body={'contents':[{'parts':[{'text':'x'}]}],'generationConfig':{'maxOutputTokens':100}}
    path='models/gemini-3.8-flash:streamGenerateContent?alt=sse'
    expected=account.bound('post',path,body)
    install_cache_guard(budget,'comparison',account,Client)
    stream=await Client().async_request_streamed('post',path,body,None)
    with pytest.raises(TimeoutError):
        async for value in stream:pass
    assert budget.summary()['committed_usd']==pytest.approx(expected,abs=.000001)
