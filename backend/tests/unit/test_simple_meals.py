import pytest
from app.tools.simple_meals import parse_simple_meal, calculate_simple_meal
from app.tools.food_catalog import FoodCatalog


@pytest.mark.parametrize('message,grams', [
    ('닭가슴살 밥 한공기 김치', [100, 200, 40]),
    ('달각슴살 2개 밥 1.5공기 김치', [200, 300, 40]),
    ('닭가슴살 150g 밥 250g 김치 30g', [150, 250, 30]),
    ('닭가슴살 2개 150g 밥 1공기 250g 김치', [150, 250, 40]),
])
def test_portions(message, grams):
    assert [item['quantity_g'] for item in parse_simple_meal(message)['items']] == grams


@pytest.mark.parametrize('message', ['닭가슴살 밥 김치 피자', '닭가슴살 추천해줘',
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
async def test_fast_path_creates_only_pending_proposal_without_model_or_domain_write():
    from unittest.mock import AsyncMock
    from app.agents.team import DietTeam
    repository = AsyncMock()
    repository.create.side_effect = lambda user, thread, payload, key: {
        'id': 'p', 'version': 1, 'payload': payload, 'kind': 'intake', 'status': 'pending'}
    def no_model():
        raise AssertionError('simple meals must not call the model')
    team = DietTeam({'user_id': 'test', 'message': '닭가슴살 밥 한공기 김치', 'run_id': 'run'},
                    model_factory=no_model, repository=repository, db=object())
    result = await team.execute()
    assert result['pending_proposal']['status'] == 'pending'
    assert result['execution_usage']['model_calls'] == 0
    assert result['execution_usage']['tool_calls'] == 2
    assert len(result['pending_meals']) == 3
    repository.resolve.assert_not_called()
