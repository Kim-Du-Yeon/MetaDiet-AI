from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4
import pytest
from fastapi import HTTPException
from app.api.routes import main
from app.tools.meal_choices import choice_card
from app.tools.simple_meals import parse_simple_meal


@pytest.mark.parametrize('action', ['generic', 'label', 'exclude', 'cancel', 'stale'])
async def test_owned_checkpoint_buttons_prepare_only_and_cancel_writes_nothing(monkeypatch, action):
    card = choice_card(parse_simple_meal('아침 밥 돼지바', allow_unknown=True), '아침 밥 돼지바')
    graph, repo = AsyncMock(), AsyncMock()
    graph.aget_state.return_value = SimpleNamespace(values={'food_selection': card})
    repo.create.side_effect = lambda user, thread, payload, key: {'id':'proposal', 'version':1, 'kind':'intake', 'payload':payload}
    @asynccontextmanager
    async def lock(*args):
        yield
    monkeypatch.setattr(main, 'get_graph', lambda:graph)
    monkeypatch.setattr(main, 'ProposalRepository', lambda:repo)
    monkeypatch.setattr(main, 'conversation_lock', lock)
    choices = [] if action in {'cancel','stale'} else [{'index':1, 'action':action}]
    if action == 'label':
        choices[0]['label'] = dict(food_name='돼지바', basis_g=70, quantity_g=70, calories=180, protein_g=2, carbs_g=20, fat_g=10)
    req = main.MealChoicesRequest(thread_id='t', selection_id='0'*64 if action=='stale' else card['id'],
        request_id=uuid4(), choices=choices, cancel=action=='cancel')
    if action=='stale':
        with pytest.raises(HTTPException) as error:
            await main.resolve_food_choices(req, 'owner')
        assert error.value.status_code == 409
        repo.create.assert_not_called()
    else:
        result = await main.resolve_food_choices(req, 'owner')
        if action=='cancel':
            assert result['cancelled']
            repo.create.assert_not_called()
        else:
            assert len(result['payload']['meals']) == (1 if action=='exclude' else 2)
            assert repo.create.call_args.args[:2] == ('owner', 't')
            graph.aget_state.assert_awaited_once_with({'configurable':{'thread_id':'owner_t'}})
            # Retry the same request cannot prepare a second proposal.
            graph.aget_state.return_value = SimpleNamespace(values=graph.aupdate_state.call_args.args[1])
            assert await main.resolve_food_choices(req, 'owner') == result
            assert repo.create.await_count == 1
    repo.resolve.assert_not_called()


async def test_all_excluded_is_cancel_instead_of_empty_record():
    from app.tools.meal_choices import resolve_meal_choices
    from app.tools.food_catalog import FoodCatalog
    with pytest.raises(ValueError, match='all_foods_excluded'):
        await resolve_meal_choices(parse_simple_meal('돼지바', allow_unknown=True), [{'index':0,'action':'exclude'}], FoodCatalog())


async def test_direct_decision_clears_mixed_source_checkpoint(monkeypatch):
    from app.schemas.proposals import ProposalDecision
    graph, repo = AsyncMock(), AsyncMock()
    identity = uuid4()
    repo.resolve.return_value = {'id':str(identity), 'thread_id':'t', 'payload':{'meals':[{'source':'csv'},{'source':'user_label'}]}}
    graph.aget_state.return_value = SimpleNamespace(values={'pending_proposal':{'id':str(identity)}})
    @asynccontextmanager
    async def lock(*args):
        yield
    monkeypatch.setattr(main,'ProposalRepository',lambda:repo)
    monkeypatch.setattr(main,'get_graph',lambda:graph)
    monkeypatch.setattr(main,'conversation_lock',lock)
    await main.decide_proposal(ProposalDecision(proposal_id=identity,version=1,action='confirm'),'owner')
    assert graph.aupdate_state.call_args.args[1]['pending_proposal'] is None
    assert graph.aupdate_state.call_args.args[1]['food_selection'] is None
