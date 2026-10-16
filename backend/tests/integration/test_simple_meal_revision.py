from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4
import pytest
from fastapi import HTTPException
from app.api.routes import main
from app.tools.simple_meals import parse_simple_meal, calculate_simple_meal
from app.tools.food_catalog import FoodCatalog


@pytest.mark.parametrize('stale', [False, True])
@pytest.mark.parametrize('message,amount,unit,grams', [('밥 한공기', 1.5, '공기', 300),
    ('도미노피자', .5, '판', 400), ('물만두', 2, '회분', 300),
    ('김치찌개', 350, 'g', 350), ('간장불고기', 2, '인분', 400),
    ('제육볶음', 1.5, '인분', 300)])
async def test_revision_recalculates_and_syncs_checkpoint_without_confirming(monkeypatch, stale, message, amount, unit, grams):
    payload = await calculate_simple_meal(parse_simple_meal(message), FoodCatalog())
    proposal_id = uuid4()
    old = {'id': str(proposal_id), 'version': 1, 'kind': 'intake', 'status': 'pending',
           'thread_id': 't', 'payload': payload}
    repo = AsyncMock()
    repo.get.return_value = old
    repo.create.side_effect = lambda user, thread, value, key, **kw: {**old, 'id': 'new', 'version': 2, 'payload': value}
    graph = AsyncMock()
    graph.aget_state.return_value = SimpleNamespace(values={'pending_proposal': {**old, 'version': 0 if stale else 1}})
    @asynccontextmanager
    async def lock(*args):
        yield
    monkeypatch.setattr(main, 'ProposalRepository', lambda: repo)
    monkeypatch.setattr(main, 'get_graph', lambda: graph)
    monkeypatch.setattr(main, 'conversation_lock', lock)
    request = main.MealRevision(version=1, log_date=payload['log_date'], meal_type='lunch', items=[{'amount': amount, 'unit': unit}])
    if stale:
        with pytest.raises(HTTPException) as error:
            await main.revise_meal(proposal_id, request, 'owner')
        assert error.value.status_code == 409
        repo.create.assert_not_called()
    else:
        result = await main.revise_meal(proposal_id, request, 'owner')
        assert result['payload']['meals'][0]['quantity_g'] == grams
        expected = await FoodCatalog().lookup(payload['meals'][0]['food_id'], grams)
        assert result['payload']['meals'][0]['calories'] == expected['calories']
        assert result['payload']['meals'][0]['nutrition_metadata']['portion'].get('basis_note') == payload['meals'][0]['nutrition_metadata']['portion'].get('basis_note')
        assert graph.aupdate_state.call_args.args[1]['pending_proposal']['version'] == 2
        repo.get.assert_awaited_once_with('owner', str(proposal_id))
    repo.resolve.assert_not_called()


async def test_restore_reconciles_revision_committed_before_checkpoint_failure(monkeypatch, fake_sb):
    old = {'id': 'old', 'version': 1}
    new = {'id': 'new', 'version': 2, 'kind': 'intake', 'status': 'pending',
           'payload': {'meals': [], 'log_date': '2026-10-13'}}
    repository = AsyncMock()
    repository.get.return_value = {**old, 'status': 'superseded'}
    repository.latest_pending.return_value = new
    graph = AsyncMock()
    graph.aget_state.return_value = SimpleNamespace(values={'pending_proposal': old}, next=('confirm',))
    @asynccontextmanager
    async def lock(*args):
        yield
    monkeypatch.setattr(main, 'ProposalRepository', lambda: repository)
    monkeypatch.setattr(main, 'get_graph', lambda: graph)
    monkeypatch.setattr(main, 'conversation_lock', lock)
    result = await main.restore_session('t', 'owner')
    assert result['pending_proposal']['id'] == 'new'
    assert graph.aupdate_state.call_args.args[1]['pending_proposal']['version'] == 2
    graph.ainvoke.assert_not_called()
    repository.resolve.assert_not_called()


@pytest.mark.parametrize('exclude_all', [False, True])
async def test_excluding_food_recalculates_without_confirmation(monkeypatch, exclude_all):
    payload = await calculate_simple_meal(parse_simple_meal('밥 닭가슴살'), FoodCatalog())
    proposal_id = uuid4()
    old = {'id': str(proposal_id), 'version': 1, 'kind': 'intake', 'status': 'pending', 'thread_id': 't', 'payload': payload}
    repo = AsyncMock()
    repo.get.return_value = old
    repo.create.side_effect = lambda user, thread, value, key, **kw: {**old, 'version': 2, 'payload': value}
    graph = AsyncMock()
    graph.aget_state.return_value = SimpleNamespace(values={'pending_proposal': old})
    @asynccontextmanager
    async def lock(*args):
        yield
    monkeypatch.setattr(main, 'ProposalRepository', lambda: repo)
    monkeypatch.setattr(main, 'get_graph', lambda: graph)
    monkeypatch.setattr(main, 'conversation_lock', lock)
    request = main.MealRevision(version=1, log_date=payload['log_date'], meal_type='lunch', items=[
        {'amount': 1, 'unit': '공기', 'exclude': True}, {'amount': 100, 'unit': 'g', 'exclude': exclude_all}])
    if exclude_all:
        with pytest.raises(HTTPException) as error:
            await main.revise_meal(proposal_id, request, 'owner')
        assert error.value.status_code == 422
        repo.create.assert_not_called()
    else:
        result = await main.revise_meal(proposal_id, request, 'owner')
        assert len(result['payload']['meals']) == 1
        assert result['payload']['meals'][0]['nutrition_metadata']['excluded_foods'] == ['밥']
    repo.resolve.assert_not_called()
