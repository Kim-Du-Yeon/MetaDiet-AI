import pytest
from app.tools.simple_meals import parse_simple_meal, calculate_simple_meal
from app.tools.food_catalog import FoodCatalog


@pytest.mark.parametrize('name,grams', [
    ('밤크림빵',80), ('버섯피자',200), ('새우만두',150), ('양념치킨',150),
    ('김치볶음밥',300), ('불고기버거',200), ('수제쿠키',30), ('딸기케이크',100),
    ('참치샌드위치',200), ('브랜드아이스크림',70), ('망고주스',200),
    ('탄산음료',200), ('제로콜라',200), ('컵라면',500), ('크림스파게티',300),
    ('치즈감자튀김',100), ('플레인요거트',100), ('아메리카노',200),
])
async def test_food_family_without_registered_exact_name_makes_quote(name, grams):
    parsed = parse_simple_meal(name+' 먹었어', allow_unknown=True)
    assert parsed is not None and len(parsed['items']) == 1
    assert not parsed['items'][0].get('unresolved')
    result = await calculate_simple_meal(parsed, FoodCatalog())
    meal = result['meals'][0]
    assert meal['quantity_g'] == grams
    expected_ids = {'김치볶음밥': 'mfds:D101-017070000-0001',
                    '크림스파게티': 'mfds:D303-161480000-0001'}
    if name in expected_ids:
        assert meal['food_id'] == expected_ids[name]
        assert meal['nutrition_metadata']['food_kind'] == 'standard'
    else:
        assert meal['source'] == 'csv'
    assert meal['nutrition_metadata']['portion']['display_name'] == name
    if name != '플레인요거트':
        assert meal['nutrition_metadata']['portion']['food_group']
        assert meal['nutrition_metadata']['portion']['representative']


async def test_multiple_group_items_are_not_swallowed_or_questions():
    parsed = parse_simple_meal('밤크림빵 감자빵 버섯피자 3조각 새우만두 4개', allow_unknown=True)
    assert [i['quantity_g'] for i in parsed['items']] == [80,80,300,120]
    assert len((await calculate_simple_meal(parsed, FoodCatalog()))['meals']) == 4


@pytest.mark.parametrize('text', ['빵가루', '치킨무', '피자 추천해줘', '내일 쿠키 먹을 예정',
    '양념치킨 -2인분', '새우만두 0개', '반려견사료빵'])
def test_group_matching_does_not_hide_non_food_or_invalid_input(text):
    parsed = parse_simple_meal(text, allow_unknown=True)
    assert parsed is None or any(i.get('unresolved') for i in parsed['items'])


async def test_exact_precedence_and_group_serving_units():
    parsed = parse_simple_meal('물만두 2회분 버섯피자 반판 바나나', allow_unknown=True)
    assert [i['quantity_g'] for i in parsed['items']] == [300,400,100]
    assert parsed['items'][0]['canonical'] == '만두, 물만두'
