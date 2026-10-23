import copy
import json
from datetime import date
import pytest


def module():
    from app.core import trace_policy
    return trace_policy


def test_production_masks_health_prose_nested_values_and_metadata():
    p=module()
    body={'messages':[{'kwargs':{'content':'홍길동 010-1234-5678 체중 73kg', 'tool_calls':[{'args':{'email':'private@example.com'}}]}}], 'user_id':'private-uuid'}
    original=copy.deepcopy(body)
    result=p.mask_body(body)
    text=json.dumps(result,ensure_ascii=False)
    for secret in ['홍길동','010-1234-5678','73','private@example.com','private-uuid']:
        assert secret not in text
    assert body==original
    assert 'messages' in result
    meta=p.safe_metadata({'thread_id':'thread-'+'a'*24,'user_id':'private-uuid','ls_model_name':'gemini-3.8-flash','prompt_release':'release-v4','free_text':'홍길동'})
    assert meta['ls_model_name']=='gemini-3.8-flash'
    assert meta['thread_id']=='thread-'+'a'*24
    assert 'private' not in json.dumps(meta)
    assert 'free_text' not in meta


def test_server_cannot_enable_cleartext_and_synthetic_requires_attestation():
    p=module()
    assert p.trace_mode({'RENDER':'true','TRACE_DATA_MODE':'synthetic','TRACE_SYNTHETIC_ONLY':'true'})=='production'
    assert p.trace_mode({'TRACE_DATA_MODE':'synthetic'})=='production'
    assert p.trace_mode({'TRACE_DATA_MODE':'synthetic','TRACE_SYNTHETIC_ONLY':'true'})=='synthetic'
    assert p.trace_mode({})=='production'


def test_cost_cache_discount_and_reasoning_is_not_counted_twice():
    p=module()
    usage={'input_tokens':1000,'output_tokens':200,'total_tokens':1200,'input_token_details':{'cache_read':400},'output_token_details':{'reasoning':150}}
    result=p.priced_usage('gemini-3.8-flash',usage,day=date(2026,10,23))
    assert result['input_cost']==pytest.approx(.00048)
    assert result['output_cost']==pytest.approx(.00075)
    assert result['total_cost']==pytest.approx(.00123)
    assert usage.get('input_cost') is None


@pytest.mark.parametrize('usage',[{}, {'input_tokens':1,'output_tokens':2,'total_tokens':2}, {'input_tokens':1,'output_tokens':2,'total_tokens':3,'input_token_details':{'cache_read':2}}])
def test_unknown_or_invalid_usage_never_becomes_zero_cost(usage):
    assert module().priced_usage('gemini-3.8-flash',usage,day=date(2026,10,23)) is None


def test_unknown_models_and_expired_price_are_not_guessed():
    p=module(); u={'input_tokens':2,'output_tokens':1,'total_tokens':3}
    assert p.priced_usage('future-model',u,day=date(2026,10,23)) is None
    assert p.priced_usage('gemini-3.8-flash',u,day=date(2027,1,1)) is None


def test_real_langchain_callbacks_pass_sanitized_bodies_and_model_usage(monkeypatch):
    from langsmith import Client,tracing_context
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from langchain_core.messages import AIMessage
    p=module(); captured=[]
    monkeypatch.setattr(Client,'create_run',lambda self,name,inputs,run_type,**kw:captured.append({'inputs':inputs,**kw}))
    monkeypatch.setattr(Client,'update_run',lambda self,run_id,**kw:captured.append(kw))
    client=p.PolicyClient(api_key='test-key',auto_batch_tracing=False)
    model=FakeMessagesListChatModel(responses=[AIMessage(content='홍길동 73kg',usage_metadata={'input_tokens':1000,'output_tokens':200,'total_tokens':1200})])
    with tracing_context(enabled=True,client=client,project_name='unit-test'):
        model.invoke('010-1234-5678',config={'metadata':{'ls_model_name':'gemini-3.8-flash','thread_id':'thread-'+'a'*24}})
    from langchain_core.tracers.langchain import wait_for_all_tracers
    wait_for_all_tracers()
    assert len(captured)==2
    assert '홍길동' not in json.dumps(captured,ensure_ascii=False,default=str)
    assert '010-1234-5678' not in json.dumps(captured,default=str)
    assert captured[-1]['extra']['metadata']['usage_metadata']['total_tokens']==1200
    assert captured[-1]['extra']['metadata']['usage_metadata']['total_cost']==pytest.approx(.0015)


def test_synthetic_preserves_question_and_answer_without_mutating_payload():
    p=module(); data={'inputs':{'question':'synthetic question'},'outputs':{'answer':'synthetic answer'}}
    result=p.sanitize_run(data,'synthetic')
    assert result['inputs']==data['inputs']
    assert result['outputs']==data['outputs']


@pytest.mark.asyncio
async def test_http_always_uses_masking_even_with_synthetic_environment(monkeypatch):
    from langsmith.run_helpers import get_tracing_context
    p=module(); seen=[]
    monkeypatch.setenv('LANGSMITH_API_KEY','test-key')
    monkeypatch.setenv('LANGSMITH_TRACING','true')
    monkeypatch.setenv('TRACE_DATA_MODE','synthetic')
    from types import SimpleNamespace
    monkeypatch.setattr(p,'runtime_client',lambda:SimpleNamespace(trace_data_mode='production'))
    async def app(scope,receive,send): seen.append(get_tracing_context()['client'].trace_data_mode)
    await p.TracePolicyMiddleware(app)({'type':'http'},None,None)
    assert seen==['production']


def test_unknown_model_keeps_observed_usage_but_no_fabricated_cost():
    result=module().sanitize_run({'extra':{'metadata':{'ls_model_name':'new-model','usage_metadata':{'input_tokens':11,'output_tokens':2,'total_tokens':13}}}},'production')
    meta=result['extra']['metadata']
    assert meta['usage_metadata']['total_tokens']==13
    assert 'total_cost' not in meta['usage_metadata']
    assert meta['cost_basis']=='unknown_or_unsupported'


def test_synthetic_mode_redacts_credentials_and_rejects_unattested_client(monkeypatch):
    p=module()
    monkeypatch.delenv('TRACE_SYNTHETIC_ONLY',raising=False)
    with pytest.raises(ValueError): p.PolicyClient(mode='synthetic',api_key='test-key')
    result=p.sanitize_run({'inputs':{'question':'synthetic question','api_key':'secret-value','authorization':'Bearer abc'}},'synthetic')
    assert result['inputs']['question']=='synthetic question'
    assert 'secret-value' not in json.dumps(result)
    assert 'Bearer abc' not in json.dumps(result)


def test_masked_messages_keep_only_safe_serialization_discriminators():
    p=module()
    value={'lc':1,'type':'constructor','id':['langchain','schema','messages','HumanMessage'],'kwargs':{'content':'private health','type':'human','id':'private-user-id'}}
    masked=p.mask_body(value)
    assert masked['id']==['langchain','schema','messages','HumanMessage']
    assert masked['lc']==1
    assert masked['kwargs']['content']=='[REDACTED]'
    assert masked['kwargs']['type']=='human'
    assert 'private-user-id' not in json.dumps(masked)
