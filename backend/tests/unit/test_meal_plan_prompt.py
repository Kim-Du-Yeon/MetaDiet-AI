import json

import pytest
from app.core.llm import ConfiguredChatModel

import app.agents.meal_plan.node as meal_plan_module
import app.db.supabase_client as supabase_client_module
import app.rag.retriever as retriever_module
from tests.conftest import FakeSupabase

_PLAN_JSON = json.dumps({
    "plan_date": "2026-06-22",
    "meals": [{"meal_type": "dinner", "food_name": "닭가슴살", "quantity_g": 200,
               "calories": 330, "protein_g": 62, "carbs_g": 0, "fat_g": 7}],
    "total_calories": 330, "total_protein": 62,
    "message": "전날 2540kcal 섭취(목표 대비 +236kcal 초과).",
}, ensure_ascii=False)


@pytest.fixture
def _stub_meal_plan_deps(monkeypatch):
    monkeypatch.setattr(supabase_client_module, "get_supabase", lambda: FakeSupabase({"meal_logs": []}))

    async def fake_yesterday(user_id):
        return {"has_data": False}
    async def fake_pattern(user_id, days=7):
        return {"has_data": False}
    monkeypatch.setattr(meal_plan_module, "get_yesterday_summary", fake_yesterday)
    monkeypatch.setattr(meal_plan_module, "get_pattern_analysis", fake_pattern)

    async def fake_retrieve(*a, **k):
        return {"grounded": True, "context": "evidence", "max_score": 0.9}
    monkeypatch.setattr(retriever_module, "retrieve", fake_retrieve)

    captured = []

    async def fake_ainvoke(self, messages, *a, **k):
        captured.append(messages)
        content = "english search query" if len(captured) == 1 else _PLAN_JSON
        class _Resp:
            pass
        r = _Resp()
        r.content = content
        return r

    monkeypatch.setattr(ConfiguredChatModel, "ainvoke", fake_ainvoke)
    return captured


async def test_prompt_enforces_90pct_floor_and_remaining_budget(_stub_meal_plan_deps):
    await meal_plan_module.meal_plan_node({
        "user_id": "u1", "message": "내일 식단 짜줘",
        "target_calories": 2304, "target_protein": 150,
    })

    plan_prompt = str(_stub_meal_plan_deps[-1])
    assert "90% 이상" in plan_prompt
    assert "재계산 금지" in plan_prompt
