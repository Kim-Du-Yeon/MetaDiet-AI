from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest


def test_verified_records_survive_evidence_failure_without_new_targets():
    from app.agents.coaching_review import build_review
    text, card = build_review(profile={'strategy':{'daily_calories':2000}},
        intake={'date':'2026-10-16','calories':600,'meals':[{'food_name':'밥','quantity_g':200}]},
        measurements=None, assessment=None, reason='search_unavailable')
    assert '600' in text and '2,000' in text and '1,400' in text
    assert '검색 도구' in text and '기록되지 않은 식사 내역을 먼저' not in text
    assert card['optional_input'] is None and card['reason'] == 'search_unavailable'


def test_missing_measurement_is_optional_but_empty_intake_is_not_missing_food():
    from app.agents.coaching_review import build_review
    text, card = build_review(profile={'strategy':{'daily_calories':2000}},
        intake={'date':'2026-10-16','calories':0,'meals':[]}, measurements=[],
        assessment={'status':'insufficient_data'}, reason='insufficient_evidence')
    assert '0 kcal' in text and card['optional_input'] == 'measurements'
    assert '식사 내역을 먼저' not in text


async def test_failed_retrieval_is_cached_and_distinguished_from_low_score(monkeypatch):
    from app.agents.team import DietTeam, Query
    import app.rag.retriever as retriever
    retrieve = AsyncMock(side_effect=ConnectionError('private credentials must not leak'))
    monkeypatch.setattr(retriever,'retrieve',retrieve)
    team=DietTeam({'user_id':'u1','message':'목표 검토'},db=object(),repository=AsyncMock())
    one=await team.search_evidence(Query(query='weight loss'))
    two=await team.search_evidence(Query(query='weight loss'))
    assert one == two and one['status'] == 'search_unavailable'
    assert retrieve.await_count == 1
    result=await team.finalize_result(SimpleNamespace(status='completed',content='줄여야 할 목표 900 kcal',events=[]),'goal')
    assert '900' not in result['response']
    assert 'private' not in str(result)
    assert result['coaching_review']['reason']=='search_unavailable'


async def test_successful_but_ungrounded_search_is_not_a_tool_failure(monkeypatch):
    from app.agents.team import DietTeam, Query
    import app.rag.retriever as retriever
    monkeypatch.setattr(retriever,'retrieve',AsyncMock(return_value={'grounded':False,'docs':[],'max_score':.1}))
    team=DietTeam({'user_id':'u1','message':'목표 검토'},db=object(),repository=AsyncMock())
    result=await team.search_evidence(Query(query='weight loss'))
    assert result['status']=='insufficient_evidence'


async def test_grounded_review_can_offer_optional_measurements_without_overwriting_analysis():
    from app.agents.team import DietTeam
    team=DietTeam({'user_id':'u1','message':'목표 검토'},db=object(),repository=AsyncMock())
    team.goal_assessment={'status':'insufficient_data'}
    result=await team.finalize_result(SimpleNamespace(status='completed',content='확인된 기록에 대한 분석',events=[]),'goal')
    assert result['response']=='확인된 기록에 대한 분석'
    assert result['coaching_review']['optional_input']=='measurements'


async def test_search_outage_is_not_retried_with_different_queries(monkeypatch):
    from app.agents.team import DietTeam, Query
    import app.rag.retriever as retriever
    retrieve=AsyncMock(side_effect=ValueError('Gemini RAG build is not activated; rebuild and select activation.json settings'))
    monkeypatch.setattr(retriever,'retrieve',retrieve)
    team=DietTeam({'user_id':'u1','message':'목표 검토'},db=object(),repository=AsyncMock())
    assert (await team.search_evidence(Query(query='weight loss')))['status']=='search_unavailable'
    assert (await team.search_evidence(Query(query='muscle retention')))['status']=='search_unavailable'
    assert retrieve.await_count==1
