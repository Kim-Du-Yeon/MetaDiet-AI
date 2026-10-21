"""Offline budget safety: no provider clients or credentials."""
import importlib.util
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import pytest

PATH=Path(__file__).resolve().parents[2]/"scripts/eval/eval_budget.py"
spec=importlib.util.spec_from_file_location("eval_budget",PATH)
budget=importlib.util.module_from_spec(spec)
spec.loader.exec_module(budget)

def test_stage_total_restart_and_unknown_usage(tmp_path):
    path=tmp_path/"budget.sqlite"
    b=budget.Budget(path)
    ticket=b.reserve("development",.20)
    with pytest.raises(budget.BudgetStop): b.reserve("development",.06)
    b.settle(ticket,None)  # No usage: retain full reservation.
    other=budget.Budget(path)
    with pytest.raises(budget.BudgetStop): other.reserve("development",.06)
    assert other.summary()["committed_usd"]==pytest.approx(.20)
    with pytest.raises(budget.BudgetStop): other.reserve("probe",.001)
    assert other.summary()["stopped"]

def test_concurrent_reservations_are_atomic(tmp_path):
    b=budget.Budget(tmp_path/"budget.sqlite")
    def attempt(_):
        try: return b.reserve("probe",.06)
        except budget.BudgetStop: return None
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(x is not None for x in pool.map(attempt,range(16)))==1

def test_settlement_releases_only_verified_cost(tmp_path):
    b=budget.Budget(tmp_path/"budget.sqlite")
    t=b.reserve("probe",.09)
    b.settle(t,.01)
    b.reserve("probe",.09)
    with pytest.raises(budget.BudgetStop): b.settle(t,0)
    with pytest.raises(budget.BudgetStop): b.reserve("probe",float("nan"))

def test_request_bound_rejects_unknown_and_reserves_thinking():
    amount=budget.request_bound("models/gemini-3.8-flash:generateContent",
        {"contents":[{"parts":[{"text":"hello"}]}],"generationConfig":{"maxOutputTokens":100,"thinkingConfig":{"thinkingBudget":50}}})
    assert amount > 150*3.75/1e6
    with pytest.raises(budget.BudgetStop): budget.request_bound("models/unknown:generateContent",{})
    with pytest.raises(budget.BudgetStop): budget.request_bound("models/gemini-3.8-flash:generateContent",{"tools":[{}]})

def test_batch_bound_and_unknown_endpoint():
    request={"batch":{"inputConfig":{"requests":{"requests":[{"request":{"contents":[{"parts":[{"text":"hi"}]}],"generationConfig":{"maxOutputTokens":100}}}]}}}}
    assert budget.request_bound("models/gemini-3.1-pro-preview:batchGenerateContent",request)>0
    with pytest.raises(budget.BudgetStop): budget.request_bound("files:upload",{})

def test_guard_blocks_transport_and_unknown_usage_keeps_reservation(tmp_path):
    class Client:
        def request(self,method,path,request_dict,http_options=None): raise AssertionError("paid transport called")
        async def async_request(self,method,path,request_dict,http_options=None): raise AssertionError("paid transport called")
    b=budget.Budget(tmp_path/"budget.sqlite")
    b.reserve("probe",.1)
    budget.install_transport_guard(b,"probe",Client)
    with pytest.raises(budget.BudgetStop):
        Client().request("post","models/gemini-3.8-flash:generateContent",{"generationConfig":{"maxOutputTokens":10}})

def test_total_limit_independent_of_stage_limits(tmp_path,monkeypatch):
    monkeypatch.setattr(budget,"TOTAL",.15)
    b=budget.Budget(tmp_path/"budget.sqlite")
    b.reserve("probe",.10)
    with pytest.raises(budget.BudgetStop): b.reserve("development",.06)

def test_missing_caps_and_bad_usage_fail_closed(tmp_path):
    from types import SimpleNamespace
    path="models/gemini-3.8-flash:generateContent"
    with pytest.raises(budget.BudgetStop): budget.request_bound(path,{"contents":[]})
    assert budget.response_cost(path,SimpleNamespace(body='{}')) is None
    assert budget.response_cost(path,SimpleNamespace(body='{"usageMetadata":{"promptTokenCount":1}}')) is None
    assert budget.response_cost(path,SimpleNamespace(body='{"usageMetadata":{"promptTokenCount":1,"candidatesTokenCount":2,"thoughtsTokenCount":3}}'))==pytest.approx((.75+5*3.75)/1e6)

def test_sdk_sync_batch_and_async_shapes_without_network(tmp_path,monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from google import genai
    from google.genai import types
    from google.genai._api_client import BaseApiClient
    calls=[]
    def transport(self,*args,**kwargs):
        calls.append(args)
        return SimpleNamespace(headers={},response_stream=['{"usageMetadata":{"promptTokenCount":1,"candidatesTokenCount":1},"candidates":[{"content":{"role":"model","parts":[{"text":"ok"}]}}]}'])
    async def async_transport(self,*args,**kwargs): return transport(self,*args,**kwargs)
    monkeypatch.setattr(BaseApiClient,"_request",transport)
    monkeypatch.setattr(BaseApiClient,"_async_request",async_transport)
    # monkeypatch records restoration after install_transport_guard replaces these.
    monkeypatch.setattr(BaseApiClient,"request",BaseApiClient.request)
    monkeypatch.setattr(BaseApiClient,"async_request",BaseApiClient.async_request)
    monkeypatch.setattr(BaseApiClient,"request_streamed",BaseApiClient.request_streamed)
    monkeypatch.setattr(BaseApiClient,"async_request_streamed",BaseApiClient.async_request_streamed)
    b=budget.Budget(tmp_path/"sdk.sqlite")
    budget.install_transport_guard(b,"probe")
    client=genai.Client(api_key="offline-placeholder")
    client.models.generate_content(model="gemini-3.8-flash",contents="hello",config={"max_output_tokens":10})
    asyncio.run(client.aio.models.generate_content(model="gemini-3.8-flash",contents="hello",config={"max_output_tokens":10}))
    assert len(calls)==2
    from google.genai.batches import _CreateBatchJobParameters_to_mldev
    request=types.InlinedRequest(contents=[types.Content(role="user",parts=[types.Part(text="hello")])],
        config=types.GenerateContentConfig(max_output_tokens=100,system_instruction="grade"))
    body=_CreateBatchJobParameters_to_mldev(client._api_client,{"model":"gemini-3.1-pro-preview","src":[request]})
    body.pop("_url",None)
    assert budget.request_bound("models/gemini-3.1-pro-preview:batchGenerateContent",body)>0
    client.close()

def test_provider_exception_charges_reservation_and_disables_internal_retries(tmp_path):
    received=[]
    class Client:
        def request(self,method,path,request_dict,http_options=None):
            received.append(http_options)
            raise RuntimeError("provider failure")
        async def async_request(self,*args): raise RuntimeError("provider failure")
    b=budget.Budget(tmp_path/"error.sqlite")
    budget.install_transport_guard(b,"probe",Client)
    with pytest.raises(RuntimeError):
        Client().request("post","models/gemini-3.8-flash:generateContent",{"generationConfig":{"maxOutputTokens":10}})
    assert b.summary()["committed_usd"]>0
    assert received[0]["retry_options"]["attempts"]==1

def test_default_cli_has_no_paid_authorization():
    import argparse
    p=argparse.ArgumentParser()
    budget.add_budget_args(p)
    with pytest.raises(budget.BudgetStop,match="Offline default"):
        budget.activate_budget(p.parse_args([]),"comparison")

def test_actual_overrun_is_retained_and_persistently_stops_campaign(tmp_path):
    path=tmp_path/"overrun.sqlite"
    b=budget.Budget(path)
    ticket=b.reserve("probe",.01)
    with pytest.raises(budget.BudgetStop): b.settle(ticket,.11)
    other=budget.Budget(path)
    assert other.summary()["committed_usd"]==pytest.approx(.11)
    with pytest.raises(budget.BudgetStop): other.reserve("comparison",.001)

def test_structured_output_function_schema_has_only_token_cost():
    payload={"generationConfig":{"maxOutputTokens":512},
             "tools":[{"functionDeclarations":[{"name":"Assessment","parameters":{"type":"OBJECT","properties":{"sufficient":{"type":"BOOLEAN"}}}}]}]}
    assert budget.request_bound("models/gemini-3.1-flash-lite:generateContent",payload)>0
    payload["tools"]=[{"googleSearch":{}}]
    with pytest.raises(budget.BudgetStop):
        budget.request_bound("models/gemini-3.1-flash-lite:generateContent",payload)

def test_batch_judge_feasibility_stops_before_any_generation(tmp_path):
    b=budget.Budget(tmp_path/"preflight.sqlite")
    budget.preflight_batch_judge(b,pairs=100,output_cap=2048)
    assert b.summary()["committed_usd"]==0
    assert not b.summary()["stopped"]
    with pytest.raises(budget.BudgetStop,match="Budget exhausted: judge"):
        budget.preflight_batch_judge(b,pairs=100,output_cap=2048,chunk_size=100)
    assert b.summary()["committed_usd"]==0
    assert b.summary()["stopped"]
