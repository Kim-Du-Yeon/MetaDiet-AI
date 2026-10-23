import pytest
from scripts.demo_langsmith_agent import MemoryProposals, NoDatabase, demo_state, execute_demo

@pytest.mark.asyncio
async def test_demo_uses_real_team_boundary_with_only_synthetic_state():
    seen={}
    class Team:
        def __init__(self,state,**kwargs): seen.update(state=state,kwargs=kwargs)
        async def execute(self): return {'response':'가상 제안','awaiting_confirmation':True}
    result=await execute_demo(Team)
    assert result['awaiting_confirmation']
    assert seen['state']['user_id'].startswith('synthetic-')
    assert seen['state']['tool_policy']==['search_foods','nutrition_lookup','propose_meal']
    assert seen['kwargs']['simple_meals_enabled'] is False
    assert isinstance(seen['kwargs']['repository'],MemoryProposals)
    with pytest.raises(RuntimeError,match='disabled'): seen['kwargs']['db'].table('users')

@pytest.mark.asyncio
async def test_demo_proposal_is_pending_and_not_persisted():
    repo=MemoryProposals()
    result=await repo.create('synthetic-interview','demo',{'kind':'intake'},'key')
    assert result['status']=='pending'
    assert result['id'].startswith('synthetic-')
    with pytest.raises(ValueError): await repo.create('real-user','demo',{},'key')

def test_fixed_fixture_is_fresh_and_cannot_accept_personal_input():
    a=demo_state();a['message']='personal'
    assert demo_state()['message']!='personal'
    assert demo_state()['requested_action']=='record_only'

def test_visibility_allows_redacted_provider_signatures_but_not_hidden_content():
    from scripts.demo_langsmith_agent import visible_payload
    assert visible_payload({'content':'합성 답변','extras':{'signature':'[REDACTED]'}})
    assert visible_payload({'tool_calls':[{'name':'search_foods','args':{'query':'쌀밥'}}],
        'additional_kwargs':{'__gemini_function_call_thought_signatures__':'[REDACTED]'}})
    assert not visible_payload({'content':'[REDACTED]'})
    assert not visible_payload({})
