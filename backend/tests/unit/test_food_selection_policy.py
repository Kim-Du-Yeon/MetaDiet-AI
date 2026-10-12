import pandas as pd
import pytest
from unittest.mock import AsyncMock
from app.tools.food_catalog import FoodCatalog


def frame(name):
    return pd.DataFrame([{'식품명': name, '식품코드': 'R1', '에너지': 150,
                         '단백질': 3, '탄수화물': 33, '지방': 1, '나트륨': 2}])


@pytest.mark.parametrize('query,name', [('쌀밥', '멥쌀, 백미, 밥'),
    ('삼겹살구이', '돼지고기, 삼겹살, 구운것(팬)'), ('고등어구이', '고등어, 구운것')])
async def test_generic_standard_precedes_exact_manufacturer_product(query, name):
    repository = AsyncMock()
    repository.search.return_value = [{'food_id': 'mfds:P1', 'name': query,
        'normalized_name': query, 'source': 'mfds', 'manufacturer': '회사'}]
    catalog = FoodCatalog(frame=frame(name), repository=repository)
    result = await catalog.search(query)
    assert len(result) == 1 and result[0]['food_id'] == 'csv:R1'
    assert result[0]['food_kind'] == 'standard'
    repository.search.assert_not_awaited()


async def test_single_processed_product_requires_explicit_selection():
    from app.agents.team import DietTeam, Query, FoodLookup
    from app.agents.runtime import ToolFeedback
    team = DietTeam({'user_id': 'u', 'message': '제품 50g 먹었어'}, repository=AsyncMock(), db=object())
    team.food_catalog = AsyncMock()
    team.food_catalog.lookup.return_value = {'food_id': 'mfds:P1', 'calories': 100}
    team.food_catalog.search.return_value = [{'food_id': 'mfds:P1', 'name': '제품',
        'source': 'mfds', 'food_kind': 'product', 'match_type': 'exact'}]
    await team.search_foods(Query(query='제품'))
    with pytest.raises(ToolFeedback):
        await team.nutrition_lookup(FoodLookup(food_id='mfds:P1', quantity_g=50))
    assert team.food_selection['items'][0]['quantity_g'] == 50
    team.food_catalog.lookup.assert_not_awaited()


async def test_explicit_packaged_product_search_does_not_use_generic_alias():
    repository = AsyncMock()
    repository.search.return_value = [{'food_id': 'mfds:P1', 'name': '쌀밥',
        'normalized_name': '쌀밥', 'source': 'mfds', 'manufacturer': '회사'}]
    catalog = FoodCatalog(frame=frame('멥쌀, 백미, 밥'), repository=repository)
    result = await catalog.search('쌀밥', kind='product')
    assert result[0]['food_id'] == 'mfds:P1'


async def test_unselected_product_cannot_be_omitted_from_meal_proposal():
    from app.agents.team import DietTeam, MealDraft
    from app.agents.runtime import ToolFeedback
    team = DietTeam({'user_id': 'u', 'message': '밥과 제품 먹었어'}, repository=AsyncMock(), db=object())
    team.food_selection = {'request': '밥과 제품 먹었어', 'items': [{'query': '제품', 'candidates': []}]}
    team.quotes['rice'] = {'food_name': '밥', 'quantity_g': 100, 'calories': 150,
        'protein_g': 3, 'carbs_g': 33, 'fat_g': 1, 'source': 'csv'}
    with pytest.raises(ToolFeedback, match='product_selection_required'):
        await team.propose_meal(MealDraft(kind='intake', log_date='2026-10-13', meals=[{'quote_id': 'rice', 'meal_type': 'dinner'}]))

async def test_missing_food_prevents_partial_proposal():
    from app.agents.team import DietTeam, MealDraft
    from app.agents.runtime import ToolFeedback
    team = DietTeam({'user_id': 'u', 'message': '밥과 미등록제품'}, repository=AsyncMock(), db=object())
    team.unresolved_foods.add('미등록제품')
    with pytest.raises(ToolFeedback, match='food_not_found'):
        await team.propose_meal(MealDraft(kind='intake', log_date='2026-10-13', meals=[{'quote_id': 'rice', 'meal_type': 'dinner'}]))

async def test_repeated_queries_do_not_duplicate_product_cards():
    from app.agents.team import DietTeam, Query
    team = DietTeam({'user_id': 'u', 'message': '제품 50g'}, repository=AsyncMock(), db=object())
    team.food_catalog = AsyncMock()
    team.food_catalog.search.return_value = [{'food_id': 'mfds:P1', 'name': '제품', 'source': 'mfds', 'match_type': 'exact'}]
    await team.search_foods(Query(query='제품'))
    await team.search_foods(Query(query='제품 별칭'))
    assert len(team.food_selection['items']) == 1

async def test_tentative_standard_classification_does_not_hide_registered_product():
    from app.agents.team import DietTeam, FoodSearch
    team = DietTeam({'user_id': 'u', 'message': '라이스페이퍼 80g'}, repository=AsyncMock(), db=object())
    team.food_catalog = AsyncMock()
    team.food_catalog.search.side_effect = [[], [{'food_id': 'mfds:P1', 'name': '라이스페이퍼', 'source': 'mfds', 'match_type': 'exact'}]]
    await team.search_foods(FoodSearch(query='라이스페이퍼', food_kind='standard'))
    assert team.food_selection['items'] and not team.unresolved_foods
