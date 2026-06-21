import pytest
from langchain_openai import ChatOpenAI

import app.agents.confirm.node as confirm_module
import app.db.supabase_client as supabase_client_module
import app.tools.agent_tools as agent_tools_module
from tests.conftest import FakeSupabase


class _Resp:
    def __init__(self, content):
        self.content = content


def _pending():
    return [{"meal_type": "lunch", "food_name": "닭가슴살", "quantity_g": 200,
              "calories": 330, "protein_g": 62, "carbs_g": 0, "fat_g": 7, "sodium_mg": 80}]


async def test_unrelated_utterance_keeps_pending_and_does_not_save(monkeypatch):
    async def fake_ainvoke(self, messages, *a, **k):
        return _Resp("unrelated")

    monkeypatch.setattr(ChatOpenAI, "ainvoke", fake_ainvoke)

    state = {
        "user_id": "u1", "pending_meals": _pending(), "plan_date": "2026-06-21",
        "message": "오늘 날씨 어때?", "agent_used": "diet_logger",
    }
    result = await confirm_module.confirm_node(state)

    assert "확정하시겠어요" in result["response"]
    assert "pending_meals" not in result
    assert "awaiting_confirmation" not in result


async def test_confirm_utterance_still_saves(monkeypatch):
    async def fake_ainvoke(self, messages, *a, **k):
        return _Resp("confirm")

    monkeypatch.setattr(ChatOpenAI, "ainvoke", fake_ainvoke)

    fake_sb = FakeSupabase()
    monkeypatch.setattr(supabase_client_module, "get_supabase", lambda: fake_sb)
    monkeypatch.setattr(agent_tools_module, "sb", fake_sb)

    state = {
        "user_id": "u1", "pending_meals": _pending(), "plan_date": "2026-06-21",
        "message": "응 저장해줘", "agent_used": "diet_logger",
    }
    result = await confirm_module.confirm_node(state)

    assert result["pending_meals"] is None
    assert result["awaiting_confirmation"] is False
