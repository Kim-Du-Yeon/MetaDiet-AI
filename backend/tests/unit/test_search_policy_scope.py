from unittest.mock import AsyncMock
import pytest
from app.agents.team import DietTeam


@pytest.mark.parametrize('message', [
    '저녁 추천을 공식 영양 지침에서 검색한 근거와 함께 설명해줘. 실제로 참고한 자료만 인용하고, 저장이나 식사 제안 생성 없이 조언만 해줘.',
    '공식 근거를 검색하고 기록은 변경하지 마',
    '검색해서 알려줘. 저장하지 말고 설명만 해줘',
])
def test_unrelated_no_write_instruction_does_not_disable_search(message):
    team = DietTeam({'user_id':'u', 'message':message}, model_factory=lambda:None,
        repository=AsyncMock(), db=object())
    assert team.allowed is None or 'search_evidence' in team.allowed


@pytest.mark.parametrize('message', ['검색하지 마', '검색은 하지 말고 설명해줘', 'RAG 없이 설명',
    '검색을 사용하지 마', 'no search please', 'without RAG', 'do not search'])
def test_explicit_no_search_instruction_still_disables_search(message):
    team = DietTeam({'user_id':'u', 'message':message}, model_factory=lambda:None,
        repository=AsyncMock(), db=object())
    assert 'search_evidence' not in team.allowed
