import pytest

import app.tools.agent_tools as agent_tools_module
import app.tools.nutrition_db as nutrition_db_module
from app.tools.agent_tools import get_active_strategy_tool, save_meal_tool, update_strategy_tool
from app.tools.nutrition_db import nutrition_db_tool
from tests.conftest import FakeSupabase


@pytest.fixture
def fake_agent_tools_sb(monkeypatch):
    """agent_tools.py의 모듈 레벨 sb를 FakeSupabase로 교체(호출 캡처용)."""
    fake = FakeSupabase()
    monkeypatch.setattr(agent_tools_module, "sb", fake)
    return fake


async def test_save_meal_tool_inserts_correct_payload(fake_agent_tools_sb):
    result = await save_meal_tool.ainvoke({
        "user_id": "u1", "log_date": "2026-06-19", "meal_type": "lunch",
        "food_name": "닭가슴살", "quantity_g": 200, "calories": 212.0,
        "protein_g": 45.9, "carbs_g": 0.0, "fat_g": 2.3, "sodium_mg": 80.0,
        "source": "csv",
    })

    assert result["success"] is True
    method, table, payload = fake_agent_tools_sb.calls[0]
    assert (method, table) == ("insert", "meal_logs")
    assert payload["user_id"] == "u1"
    assert payload["food_name"] == "닭가슴살"
    assert payload["calories"] == 212.0
    assert payload["source"] == "csv"


async def test_get_active_strategy_tool_returns_row(fake_agent_tools_sb):
    fake_agent_tools_sb.tables["diet_strategies"] = [
        {"daily_calories": 1800, "protein_g": 140, "is_active": True}
    ]
    result = await get_active_strategy_tool.ainvoke({"user_id": "u1"})
    assert result["daily_calories"] == 1800
    assert result["protein_g"] == 140


async def test_get_active_strategy_tool_empty_returns_empty_dict(fake_agent_tools_sb):
    fake_agent_tools_sb.tables["diet_strategies"] = []
    result = await get_active_strategy_tool.ainvoke({"user_id": "u1"})
    assert result == {}


async def test_update_strategy_tool_upserts_correct_payload(fake_agent_tools_sb):
    result = await update_strategy_tool.ainvoke({
        "user_id": "u1", "daily_calories": 1900, "protein_g": 150,
        "carbs_g": 200, "fat_g": 60, "strategy_note": "근손실 방지 우선",
        "triggered_by": "inbody_update", "inbody_log_id": "log1",
    })

    assert result["success"] is True
    methods = [c[0] for c in fake_agent_tools_sb.calls]
    assert methods == ["update", "insert"]  # 기존 비활성화 -> 신규 삽입 순서

    deactivate_payload = fake_agent_tools_sb.calls[0][2]
    assert deactivate_payload == {"is_active": False}

    insert_payload = fake_agent_tools_sb.calls[1][2]
    assert insert_payload["user_id"] == "u1"
    assert insert_payload["daily_calories"] == 1900
    assert insert_payload["triggered_by"] == "inbody_update"
    assert insert_payload["is_active"] is True


_COLUMN_MAPPING = {
    "food_name": "식품명", "food_group": "식품군", "calories": "에너지",
    "protein": "단백질", "fat": "지방", "carbs": "탄수화물", "sodium": "나트륨",
}


@pytest.fixture
def _stub_nutrition_llm(monkeypatch):
    """실제 외부 API 호출 금지 — 컬럼매핑 캐시 직접 주입 + 키워드 분해만 스텁(test_nutrition_csv.py와 동일 패턴)."""
    monkeypatch.setattr(nutrition_db_module, "_column_mapping", _COLUMN_MAPPING)

    async def fake_decompose(food_name):
        return {"닭가슴살": ["닭고기", "가슴"]}.get(food_name, [food_name])

    monkeypatch.setattr(nutrition_db_module, "_decompose_keywords_with_llm", fake_decompose)


async def test_nutrition_db_tool_csv_lookup_golden_value(_stub_nutrition_llm):
    result = await nutrition_db_tool.ainvoke({"food_name": "닭가슴살", "quantity_g": 200})
    assert result["found_in_db"] is True
    assert result["calories"] == 212.0
    assert result["protein_g"] == 45.9
