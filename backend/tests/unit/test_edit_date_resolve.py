from datetime import date, timedelta

from app.agents.edit.node import _resolve_target_date

_TODAY = date(2026, 6, 19)


def test_resolve_no_keyword_falls_back_to_today():
    assert _resolve_target_date("아까 기록한 저녁 삭제해줘", _TODAY) == _TODAY.isoformat()


def test_resolve_yesterday():
    expected = (_TODAY - timedelta(days=1)).isoformat()
    assert _resolve_target_date("어제 저장한 점심 칼로리 수정해줘", _TODAY) == expected


def test_resolve_day_before_yesterday():
    expected = (_TODAY - timedelta(days=2)).isoformat()
    assert _resolve_target_date("그저께 먹은거 지워줘", _TODAY) == expected
    assert _resolve_target_date("그제 먹은거 지워줘", _TODAY) == expected


def test_resolve_empty_or_none_message_falls_back_to_today():
    assert _resolve_target_date("", _TODAY) == _TODAY.isoformat()
    assert _resolve_target_date(None, _TODAY) == _TODAY.isoformat()
