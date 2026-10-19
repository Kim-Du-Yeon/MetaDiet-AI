from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.agents.runtime import ExecutionBudget
from app.core.jev import Decision
from scripts.eval.jev_model_router import RoutingRequest,select_model


SETTINGS=SimpleNamespace(gemini_model='flash',gemini_simple_model='lite',
    gemini_vision_model='vision',gemini_eval_model='pro')


async def test_rules_select_without_an_external_call():
    client=SimpleNamespace(choose=AsyncMock())
    result=await select_model(RoutingRequest(task='extraction',text='밥200g'),
        mode='rules',settings=SETTINGS,client=client,budget=ExecutionBudget())
    assert result['model']=='lite'
    client.choose.assert_not_awaited()


@pytest.mark.parametrize('route_input,expected',[
    ({'task':'extraction','deterministic':True},None),
    ({'task':'agent'},'flash'),({'task':'vision'},'vision'),({'task':'eval'},'pro'),
    ({'task':'extraction','pending':True},'flash'),
    ({'task':'extraction','tools_required':True},'flash')])
async def test_locked_paths_never_delegate_model_choice(route_input,expected):
    client=SimpleNamespace(choose=AsyncMock())
    result=await select_model(RoutingRequest(text='synthetic',**route_input),mode='jev',
        settings=SETTINGS,client=client,budget=ExecutionBudget())
    assert result['model']==expected
    client.choose.assert_not_awaited()


async def test_low_confidence_or_failed_decision_falls_back_to_flash():
    client=SimpleNamespace(choose=AsyncMock(return_value=Decision(('fast','standard'),fallback_reason='low_confidence')))
    result=await select_model(RoutingRequest(task='classification',text='모호한 합성 입력'),mode='jev',
        settings=SETTINGS,client=client,budget=ExecutionBudget())
    assert result['model']=='flash' and result['status']=='fallback'


async def test_offered_choice_is_resolved_by_server_model_mapping():
    client=SimpleNamespace(choose=AsyncMock(return_value=Decision(('fast','standard'),choice='fast',confidence=.99)))
    result=await select_model(RoutingRequest(task='query_translation',text='synthetic query'),mode='jev',
        settings=SETTINGS,client=client,budget=ExecutionBudget())
    assert result['model']=='lite' and result['status']=='completed'


async def test_server_rechecks_confidence_even_if_injected_client_omits_fallback():
    client=SimpleNamespace(choose=AsyncMock(return_value=Decision(('fast','standard'),choice='fast',confidence=.2)))
    result=await select_model(RoutingRequest(task='extraction',text='synthetic'),mode='jev',
        settings=SETTINGS,client=client,budget=ExecutionBudget())
    assert result['status']=='fallback' and result['model']=='flash'
