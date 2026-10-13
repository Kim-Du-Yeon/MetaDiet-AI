import pytest
from app.tools.simple_meals import parse_simple_meal, calculate_simple_meal
from app.tools.food_catalog import FoodCatalog


def test_user_example_becomes_default_foods_and_one_optional_product():
    parsed = parse_simple_meal('오늘 아침에 밥 한공기랑 삼겹살 200g 그리고 돼지바 아이스크림 1개, 라이스페이퍼 8장', allow_unknown=True)
    assert parsed['meal_type'] == 'breakfast'
    assert [i['quantity_g'] for i in parsed['items']] == [200, 200, 70, 80]
    assert [i['portion']['display_name'] for i in parsed['items'] if i.get('unresolved')] == ['돼지바 아이스크림']


async def test_explicit_generic_choice_is_traced_and_exclusion_is_visible():
    from app.tools.meal_choices import resolve_meal_choices
    parsed = parse_simple_meal('밥 돼지바 아이스크림 1개', allow_unknown=True)
    result = await resolve_meal_choices(parsed, [{'index': 1, 'action': 'generic'}], FoodCatalog())
    assert len(result['meals']) == 2
    assert result['meals'][1]['nutrition_metadata']['substitution']['requested_name'] == '돼지바 아이스크림'
    excluded = await resolve_meal_choices(parsed, [{'index': 1, 'action': 'exclude'}], FoodCatalog())
    assert len(excluded['meals']) == 1
    assert excluded['meals'][0]['nutrition_metadata']['excluded_foods'] == ['돼지바 아이스크림']


async def test_unresolved_food_cannot_be_saved_without_choice():
    from app.tools.meal_choices import resolve_meal_choices
    parsed = parse_simple_meal('밥 돼지바', allow_unknown=True)
    with pytest.raises(ValueError):
        await resolve_meal_choices(parsed, [], FoodCatalog())


async def test_manual_label_joins_whole_meal_and_stays_local():
    from app.tools.meal_choices import resolve_meal_choices
    parsed = parse_simple_meal('밥 돼지바', allow_unknown=True)
    result = await resolve_meal_choices(parsed, [{'index': 1, 'action': 'label', 'label': {
        'food_name': '돼지바', 'basis_g': 70, 'quantity_g': 70, 'calories': 180,
        'protein_g': 2, 'carbs_g': 20, 'fat_g': 10}}], FoodCatalog())
    assert len(result['meals']) == 2
    assert result['meals'][1]['source'] == 'user_label'


def test_unknown_food_and_advice_remain_distinct():
    assert parse_simple_meal('밥 미등록제품 1개', allow_unknown=True)['items'][1]['unresolved']
    pizza = parse_simple_meal('밥 피자 1조각', allow_unknown=True)['items'][1]
    assert not pizza.get('unresolved') and pizza['quantity_g'] == 100
    assert parse_simple_meal('계란후라이 추천해줘', allow_unknown=True) is None
    assert parse_simple_meal('밥 -200g', allow_unknown=True) is None


async def test_user_example_does_not_enter_agent_loop_or_save():
    from app.agents.team import DietTeam
    from unittest.mock import AsyncMock
    repo = AsyncMock()
    def forbidden():
        raise AssertionError('No model call is needed for food choice buttons')
    result = await DietTeam({'user_id':'owner', 'message':'오늘 아침에 밥 한공기랑 삼겹살 200g 그리고 돼지바 아이스크림 1개, 라이스페이퍼 8장'},
        model_factory=forbidden, repository=repo, db=object()).execute()
    assert result['food_selection']['mode'] == 'meal_choices'
    assert len(result['food_selection']['items']) == 1
    assert result['execution_usage']['model_calls'] == 0
    repo.create.assert_not_called()


async def test_missing_reviewed_food_is_excludable_without_model_loop():
    from app.agents.team import DietTeam
    from unittest.mock import AsyncMock
    catalog = AsyncMock()
    catalog.search.return_value = []
    team = DietTeam({'user_id':'owner', 'message':'밥 한공기'},
        model_factory=lambda: (_ for _ in ()).throw(AssertionError('No model')), repository=AsyncMock(), db=object())
    team.food_catalog = catalog
    result = await team.execute()
    assert result['food_selection']['items'][0]['query'] == '밥'
