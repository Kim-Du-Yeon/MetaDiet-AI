import pytest
from scripts.eval.check_first_coaching_answers import remaining_calories


@pytest.mark.parametrize('text,expected', [
    ('오늘 남은 칼로리는 **1,400 kcal**입니다.',1400),
    ('목표 2000 kcal 중 1,400 kcal가 남아 있습니다.',1400),
    ('약 1,400 kcal의 여유가 있습니다.',1400),
    ('1800 kcal가 그대로 남아 있습니다.',1800),
    ('남은 열량은 1234.5 kcal입니다.',1234.5),
    ('목표 2000 kcal, 점심 500 kcal를 추천합니다.',None),
    ('남은 열량 1400 kcal입니다. 1700 kcal가 남아 있습니다.',None),
])
def test_remaining_value_must_be_bound_to_remaining_phrase(text,expected):
    assert remaining_calories(text)==expected
