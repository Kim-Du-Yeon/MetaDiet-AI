import pytest
from app.core.llm import ConfiguredChatModel

from app.agents.supervisor.node import _heuristic_intent, route_to_agent, supervisor_node


@pytest.mark.parametrize("message,expected", [
    ("닭가슴살 200g 먹었어", "diet_logger"),
    ("아아 한잔 했어", "diet_logger"),
    ("인바디 결과 분석해줘", "inbody"),
    ("체성분 변화 알려줘", "inbody"),
    ("목표 체중까지 얼마나 남았어?", "goal_manager"),
    ("목표 달성률 어때?", "goal_manager"),
    ("이번 주 식단 리포트 보여줘", "reporter"),
    ("지난달 통계 알려줘", "reporter"),
    ("아까 기록한 저녁 삭제해줘", "edit"),
    ("어제 저장한 점심 칼로리 수정해줘", "edit"),
    ("내일 하루 식단 좀 짜줘", "meal_plan"),
    ("오늘 총평 알려줘", "strategy"),
    ("오늘 날씨 어때", None),
])
def test_heuristic_intent_keywords(message, expected):
    assert _heuristic_intent(message, has_pending=False) == expected


def test_heuristic_intent_confirm_requires_pending():
    assert _heuristic_intent("응 확정해줘", has_pending=True) == "confirm"
    assert _heuristic_intent("응 확정해줘", has_pending=False) != "confirm"


def test_route_to_agent_forces_confirm_when_awaiting():
    state = {
        "intent": "reporter",
        "pending_meals": [{"meal_type": "lunch", "food_name": "닭가슴살"}],
        "awaiting_confirmation": True,
        "message": "오늘 날씨 어때",
    }
    assert route_to_agent(state) == "confirm"


def test_route_to_agent_allows_safe_intents_when_awaiting():
    state = {
        "intent": "diet_logger",
        "pending_meals": [{"meal_type": "lunch", "food_name": "닭가슴살"}],
        "awaiting_confirmation": True,
        "message": "오늘 날씨 어때",
    }
    assert route_to_agent(state) == "diet_logger"


def test_route_to_agent_confirm_without_pending_falls_back_to_strategy():
    state = {
        "intent": "confirm",
        "pending_meals": None,
        "awaiting_confirmation": False,
        "message": "이거 아니야",
    }
    assert route_to_agent(state) == "strategy"


async def test_supervisor_node_keeps_off_topic_llm_classification(monkeypatch):
    class _Resp:
        content = "off_topic"

    async def fake_ainvoke(self, *a, **k):
        return _Resp()

    monkeypatch.setattr(ConfiguredChatModel, "ainvoke", fake_ainvoke)

    result = await supervisor_node({"message": "미국 대통령이 누구야?", "messages": []})

    assert result["intent"] == "off_topic"
