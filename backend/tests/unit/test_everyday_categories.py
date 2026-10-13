import pytest
from app.tools.simple_meals import parse_simple_meal, calculate_simple_meal
from app.tools.food_catalog import FoodCatalog


@pytest.mark.parametrize('text,grams', [
    ('소보로 빵을 먹었어', [80]), ('메론빵으 ㄹ먹었어', [80]),
    ('도미노피자를 먹었어', [200]), ('냉동피자르 먹었어', [200]),
    ('물만두를 머겅써', [150]), ('군만두를 먹었어', [150]),
    ('물만두 8개 군만두 3개', [120, 90]),
    ('도미노 피자 3조각', [300]), ('피자 반판', [400]),
    ('소보루빵 2개 멜론빵 100g', [160, 100]),
    ('베이글 크로와상 단팥빵', [100, 60, 80]),
    ('만두 김치만두 햄버거', [150, 150, 200]),
])
async def test_everyday_categories_make_complete_quote_without_questions(text, grams):
    parsed = parse_simple_meal(text, allow_unknown=True)
    assert parsed is not None
    assert not any(item.get('unresolved') for item in parsed['items'])
    assert [item['quantity_g'] for item in parsed['items']] == grams
    result = await calculate_simple_meal(parsed, FoodCatalog())
    assert len(result['meals']) == len(grams)
    assert all(meal['source'] == 'csv' and meal['calories'] > 0 for meal in result['meals'])


async def test_brand_and_melon_keep_explicit_approximation_not_exact_product_claim():
    result = await calculate_simple_meal(parse_simple_meal('도미노피자 메론빵'), FoodCatalog())
    for meal in result['meals']:
        portion = meal['nutrition_metadata']['portion']
        assert portion['representative'] is True
        assert portion['basis_note']
        assert portion['policy_version'] == 'simple-v4'
    assert '도미노' in result['meals'][0]['nutrition_metadata']['portion']['display_name']
    assert '도미노' not in result['meals'][0]['food_name']


@pytest.mark.parametrize('text', ['도미노피자 추천해줘', '내일 메론빵 먹을 예정',
    '군만두 -3개', '소보로빵 0개', '피자알수없는토핑'])
def test_new_aliases_do_not_record_advice_invalid_counts_or_partial_products(text):
    parsed = parse_simple_meal(text, allow_unknown=True)
    assert parsed is None or any(item.get('unresolved') for item in parsed['items'])
