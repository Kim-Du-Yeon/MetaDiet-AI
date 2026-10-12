import pytest
import pandas as pd


def test_import_normalizes_serving_basis_and_preserves_zero():
    from app.tools.food_import import normalize_rows
    rows, report = normalize_rows([{'식품코드': 'P1', '식품명': '제품', '제조사명': '회사',
        '영양성분함량 기준량': '50g', '에너지(kcal)': '100', '단백질(g)': '0',
        '탄수화물(g)': '20', '지방(g)': '2'}])
    assert rows[0]['nutrients']['calories'] == 200
    assert rows[0]['nutrients']['protein_g'] == 0
    assert rows[0]['basis_g'] == 50
    assert report['accepted'] == 1


@pytest.mark.parametrize('field,value', [('단백질(g)', ''), ('지방(g)', '-1'),
    ('영양성분함량 기준량', '100ml'), ('에너지(kcal)', 'NaN')])
def test_import_rejects_missing_invalid_and_volume_basis(field, value):
    from app.tools.food_import import normalize_rows
    row = {'식품코드': 'P1', '식품명': '제품', '영양성분함량 기준량': '100g',
           '에너지(kcal)': '100', '단백질(g)': '1', '탄수화물(g)': '20', '지방(g)': '2'}
    row[field] = value
    rows, report = normalize_rows([row])
    assert not rows
    assert report['rejected'] == 1


def test_conflicting_duplicate_products_are_not_silently_selected():
    from app.tools.food_import import normalize_rows
    row = {'식품코드': 'P1', '식품명': '제품', '영양성분함량 기준량': '100g',
           '에너지(kcal)': '100', '단백질(g)': '1', '탄수화물(g)': '20', '지방(g)': '2'}
    rows, report = normalize_rows([row, {**row, '에너지(kcal)': '200'}])
    assert not rows
    assert report['conflicts'] == 1


async def test_catalog_uses_stable_ids_and_preserves_ambiguity():
    from app.tools.food_catalog import FoodCatalog
    frame = pd.DataFrame([{'식품명': '쌀밥', '식품코드': 'R1', '에너지': 150,
        '단백질': 3, '탄수화물': 33, '지방': 1, '나트륨': 2}])
    catalog = FoodCatalog(frame=frame, repository=None)
    matches = await catalog.search('쌀밥')
    assert matches[0]['food_id'] == 'csv:R1'
    quote = await catalog.lookup('csv:R1', 200)
    assert quote['calories'] == 300
    assert quote['food_id'] == 'csv:R1'
    assert await catalog.search('돼지바') == []


def test_label_nutrition_calculates_only_observed_values():
    from app.tools.food_catalog import LabelNutrition, quote_label
    label = LabelNutrition(food_name='제품', manufacturer='회사', basis_g=50, quantity_g=100,
        calories=100, protein_g=0, carbs_g=20, fat_g=2)
    quote = quote_label(label)
    assert quote['calories'] == 200
    assert quote['source'] == 'user_label'
    assert quote['nutrition_metadata']['basis_g'] == 50
    with pytest.raises(ValueError):
        LabelNutrition(food_name='제품', basis_g=0, quantity_g=100,
                       calories=100, protein_g=0, carbs_g=20, fat_g=2)


async def test_nutrition_api_does_not_choose_ambiguous_products(client, monkeypatch):
    from app.api.routes import main
    class Catalog:
        async def search(self, query):
            return [{'food_id': 'mfds:P1', 'name': query, 'manufacturer': '회사1'},
                    {'food_id': 'mfds:P2', 'name': query, 'manufacturer': '회사2'}]
        async def lookup(self, *args):
            raise AssertionError('ambiguous result cannot be calculated')
    monkeypatch.setattr('app.tools.food_catalog.default_catalog', lambda: Catalog())
    result = await client.post('/nutrition/lookup', json={'foods': [{'name': '제품', 'quantity_g': 50}]})
    assert result.status_code == 200
    assert result.json()['results'][0]['status'] == 'ambiguous'
    assert result.json()['results'][0]['calories'] is None


async def test_user_label_creates_pending_proposal_without_domain_write(client, mock_current_user, monkeypatch):
    from contextlib import asynccontextmanager
    from unittest.mock import AsyncMock
    from app.api.routes import main
    from app.db.proposals import ProposalRepository
    @asynccontextmanager
    async def lock(*args):
        yield
    monkeypatch.setattr(main, 'conversation_lock', lock)
    from types import SimpleNamespace
    monkeypatch.setattr(main, 'get_graph', lambda: SimpleNamespace(aupdate_state=AsyncMock()))
    create = AsyncMock(return_value={'kind': 'intake', 'status': 'pending'})
    monkeypatch.setattr(ProposalRepository, 'create', create)
    response = await client.post('/nutrition/label-proposal', json={
        'food_name': '제품', 'basis_g': 50, 'quantity_g': 100, 'calories': 100,
        'protein_g': 0, 'carbs_g': 20, 'fat_g': 2, 'meal_type': 'snack',
        'log_date': '2026-10-12', 'thread_id': 't',
        'request_id': '00000000-0000-4000-8000-000000000001'})
    assert response.status_code == 200
    payload = create.call_args.args[2]
    assert payload['meals'][0]['calories'] == 200
    assert payload['meals'][0]['source'] == 'user_label'


async def test_agent_cannot_self_confirm_ambiguous_product():
    from unittest.mock import AsyncMock
    from app.agents.team import DietTeam, FoodLookup
    from app.agents.runtime import ToolFeedback
    team = DietTeam({'user_id': 'u', 'message': '돼지바 먹었어'}, repository=AsyncMock(), db=object())
    team.food_catalog = AsyncMock()
    team.food_ids = {'mfds:P1', 'mfds:P2'}
    team.ambiguous_food_ids = set(team.food_ids)
    with pytest.raises(ToolFeedback):
        await team.nutrition_lookup(FoodLookup(food_id='mfds:P1', quantity_g=50, product_confirmed=True))
    team.food_catalog.lookup.assert_not_called()
    team.state['message'] = 'mfds:P1 또는 mfds:P2 중 뭐가 달라?'
    with pytest.raises(ToolFeedback):
        await team.nutrition_lookup(FoodLookup(food_id='mfds:P1', quantity_g=50, product_confirmed=True))
    team.food_catalog.lookup.assert_not_called()


async def test_pending_sql_label_is_restored_without_checkpoint_pointer(monkeypatch, fake_sb):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from app.api.routes import main
    proposal = {'id': 'p', 'status': 'pending', 'kind': 'intake',
                'payload': {'meals': [{'source': 'user_label'}]}}
    repository = AsyncMock()
    repository.latest_pending.return_value = proposal
    graph = SimpleNamespace(aget_state=AsyncMock(return_value=SimpleNamespace(values={}, next=())))
    monkeypatch.setattr(main, 'ProposalRepository', lambda: repository)
    monkeypatch.setattr(main, 'get_graph', lambda: graph)
    restored = await main.restore_session('t', 'u')
    assert restored['pending_proposal'] == proposal
    repository.latest_pending.assert_awaited_once_with('u', 't')
