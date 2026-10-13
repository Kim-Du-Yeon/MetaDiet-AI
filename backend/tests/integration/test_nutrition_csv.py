import pytest

import app.tools.nutrition_db as nutrition_db_module
from app.tools.nutrition_db import nutrition_db_tool

_COLUMN_MAPPING = {
    "food_name": "식품명", "food_group": "식품군", "calories": "에너지",
    "protein": "단백질", "fat": "지방", "carbs": "탄수화물", "sodium": "나트륨",
}


@pytest.fixture(autouse=True)
def _stub_llm_steps(monkeypatch):
    """실제 외부 API 호출 금지 — 컬럼매핑은 전역 캐시에 직접 주입하고 키워드 분해만 스텁한다.
    CSV 로드·AND 검색·g당 환산은 전부 실제 로직(real CSV 파일)을 그대로 거친다."""
    monkeypatch.setattr(nutrition_db_module, "_column_mapping", _COLUMN_MAPPING)

    async def fake_decompose(food_name):
        return {"닭가슴살": ["닭고기", "가슴"]}.get(food_name, [food_name])

    monkeypatch.setattr(nutrition_db_module, "_decompose_keywords_with_llm", fake_decompose)
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    monkeypatch.setattr(nutrition_db_module, "get_chat_model", lambda **kwargs:
        SimpleNamespace(ainvoke=AsyncMock(return_value=SimpleNamespace(content="닭고기, 가슴, 생것"))))


async def test_chicken_breast_200g_golden_value():
    result = await nutrition_db_tool.ainvoke({"food_name": "닭가슴살", "quantity_g": 200})

    assert result["found_in_db"] is True
    assert result["calories"] == 254.0
    assert result["protein_g"] == 56.2
