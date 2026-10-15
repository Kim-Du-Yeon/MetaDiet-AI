import pytest
from app.tools.simple_meals import PORTIONS, CATEGORY_DEFAULTS, parse_simple_meal, calculate_simple_meal
from app.tools.food_catalog import FoodCatalog


@pytest.mark.parametrize('message,grams,defaulted', [
    ('김치찌개 간장불고기 밥 한공기 먹었어', [200, 200, 200], [True, True, False]),
    ('김치찌개 간장불고기 200g 먹었어', [200, 200], [True, False]),
    ('김치찌개 350g 간장 불고기 150g', [350, 150], [False, False]),
    ('김치찌개 2인분 불고기 2인분', [400, 400], [False, False]),
])
@pytest.mark.asyncio
async def test_stew_and_bulgogi_go_directly_to_editable_proposal(message, grams, defaulted):
    parsed = parse_simple_meal(message)
    assert parsed is not None
    proposal = await calculate_simple_meal(parsed, FoodCatalog())
    assert [m['quantity_g'] for m in proposal['meals']] == grams
    assert [m['nutrition_metadata']['portion']['defaulted'] for m in proposal['meals']] == defaulted
    assert all(m['calories'] > 0 for m in proposal['meals'])
    assert proposal['meals'][0]['nutrition_metadata']['source_date'] == '2026-06-18'


@pytest.mark.parametrize('message,grams', [
    ('고구마 사과 우유', [150, 200, 200]),
    ('계란후라이 식빵 두장 플레인 요거트', [50, 60, 100]),
    ('오트밀 바나나 아몬드', [30, 100, 20]),
    ('방울 토마토 다섯개 브로콜리 오이', [75, 80, 150]),
    ('닭 가슴살, 밥 반공기, 깍두기', [100, 100, 40]),
    ('고구마랑 우유 먹었어요', [150, 200]),
    ('삶은계란 2개와 사과 반개', [100, 100]),
    ('고구마 2개 180g 우유 한컵', [180, 200]),
    ('닭가슴살 계란후라이 브로콜리', [100, 50, 80]),
])
@pytest.mark.asyncio
async def test_expanded_everyday_inputs_need_no_question_and_use_real_catalog(message, grams):
    parsed = parse_simple_meal(message)
    assert parsed is not None
    assert [i['quantity_g'] for i in parsed['items']] == grams
    result = await calculate_simple_meal(parsed, FoodCatalog())
    assert len(result['meals']) == len(grams)
    assert all(m['source'] == 'csv' and m['calories'] >= 0 for m in result['meals'])


@pytest.mark.parametrize('message', ['고구마빵 우유', '그릭요거트', '우유 200ml',
    '사과주스', '밥하고 미등록새제품', '계란후라이 추천해줘', '아몬드 -2개'])
def test_expansion_never_turns_unknown_product_or_unit_into_partial_meal(message):
    parsed = parse_simple_meal(message)
    if message in {'고구마빵 우유', '그릭요거트', '사과주스'}:
        assert parsed is not None
        assert parsed['items'][0]['portion']['representative']
        assert parsed['items'][0]['portion']['display_name'] == message.split()[0]
        assert len(parsed['items']) == (2 if message == '고구마빵 우유' else 1)
    else:
        assert parsed is None


@pytest.mark.parametrize('aliases,canonical,grams,unit,food_id', [p for p in PORTIONS if not p[4]])
@pytest.mark.asyncio
async def test_every_standard_mapping_has_unique_complete_catalog_nutrients(aliases, canonical, grams, unit, food_id):
    # A release gate against misspelled catalog names, missing nutrients, or duplicate rows.
    result = await calculate_simple_meal(parse_simple_meal(aliases[0]), FoodCatalog())
    meal = result['meals'][0]
    assert meal['food_name'] == canonical
    assert meal['quantity_g'] == grams * CATEGORY_DEFAULTS.get(canonical, (1, {}))[0]
    assert all(meal[k] >= 0 for k in ('calories', 'protein_g', 'carbs_g', 'fat_g'))


@pytest.mark.parametrize('message,grams', [
    ('닭가슴살 밥 한공기 김치', [100, 200, 40]),
    ('달각슴살 2개 밥 1.5공기 김치', [200, 300, 40]),
    ('닭가슴살 150g 밥 250g 김치 30g', [150, 250, 30]),
    ('닭가슴살 2개 150g 밥 1공기 250g 김치', [150, 250, 40]),
])
def test_portions(message, grams):
    assert [item['quantity_g'] for item in parse_simple_meal(message)['items']] == grams


@pytest.mark.parametrize('message', ['닭가슴살 밥 김치 미등록새제품', '닭가슴살 추천해줘',
    '밥 -200g', '내일 밥 먹을 예정', '제품 선택: mfds:test', '닭가슴살 0개'])
def test_never_silently_discards_or_records_advice(message):
    assert parse_simple_meal(message) is None


@pytest.mark.asyncio
async def test_cooked_lookup_and_metadata():
    result = await calculate_simple_meal(parse_simple_meal('닭가슴살 밥 한공기 김치'), FoodCatalog())
    assert len(result['meals']) == 3
    assert '삶은것' in result['meals'][0]['food_name']
    assert result['meals'][0]['nutrition_metadata']['portion']['defaulted'] is True
    assert result['meals'][1]['nutrition_metadata']['portion']['amount'] == 1


def test_explicit_cooking_wins():
    assert parse_simple_meal('생 닭가슴살 100g')['items'][0]['canonical'] == '닭고기, 가슴, 생것'


@pytest.mark.asyncio
async def test_ricepaper_uses_reviewed_dry_wrapper_not_name_only_outlier():
    from unittest.mock import AsyncMock
    catalog = AsyncMock()
    catalog.lookup.return_value = {
        'food_name': '라이스페이퍼', 'quantity_g': 80,
        'calories': 272, 'carbs_g': 68, 'protein_g': .4, 'fat_g': 0,
        'source': 'mfds', 'food_id': 'mfds:P108-007000300-0013',
        'nutrition_metadata': {},
    }
    result = await calculate_simple_meal(parse_simple_meal('라이스페이퍼 8장'), catalog)
    catalog.lookup.assert_awaited_once_with('mfds:P108-007000300-0013', 80)
    catalog.search.assert_not_awaited()
    assert result['meals'][0]['calories'] == 272
    assert result['meals'][0]['nutrition_metadata']['portion']['representative'] is True


@pytest.mark.asyncio
@pytest.mark.parametrize('message', ['닭가슴살 밥 한공기 김치',
    '오늘 점심에 김치찌개 간장불고기 200g 밥 한공기 먹었어',
    '김치찌개 간장 불고기 밥 먹었어'])
async def test_fast_path_creates_only_pending_proposal_without_model_or_domain_write(message):
    from unittest.mock import AsyncMock
    from app.agents.team import DietTeam
    repository = AsyncMock()
    repository.create.side_effect = lambda user, thread, payload, key: {
        'id': 'p', 'version': 1, 'payload': payload, 'kind': 'intake', 'status': 'pending'}
    def no_model():
        raise AssertionError('simple meals must not call the model')
    team = DietTeam({'user_id': 'test', 'message': message, 'run_id': 'run'},
                    model_factory=no_model, repository=repository, db=object())
    result = await team.execute()
    assert result['pending_proposal']['status'] == 'pending'
    assert result['execution_usage']['model_calls'] == 0
    assert result['execution_usage']['tool_calls'] == 2
    assert len(result['pending_meals']) == 3
    assert result['food_selection'] is None
    repository.resolve.assert_not_called()
