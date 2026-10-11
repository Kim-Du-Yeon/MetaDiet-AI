import json

import pytest
from app.core.llm import ConfiguredChatModel

import app.rag.retriever as retriever_module
import app.tools.agent_tools as agent_tools_module
from app.agents.inbody.node import inbody_node
from app.rag.region_guidance import REGION_GUIDANCE
from tests.conftest import FakeSupabase

_INBODY_ROW = {
    "id": "log1", "measured_date": "2026-06-01", "weight_kg": 70.0,
    "skeletal_muscle_kg": 30.0, "body_fat_pct": 20.0, "bmr_kcal": 1500,
}

_LLM_JSON_RESPONSE = json.dumps({
    "analysis": "분석", "muscle_change": "maintained", "fat_change": "decreased",
    "new_daily_calories": 1800, "new_protein_g": 140, "new_carbs_g": 180, "new_fat_g": 60,
    "strategy_note": "근거", "user_message": "메시지",
}, ensure_ascii=False)


@pytest.fixture
def fake_agent_tools_sb(monkeypatch):
    fake = FakeSupabase({"inbody_logs": [_INBODY_ROW], "diet_strategies": []})
    monkeypatch.setattr(agent_tools_module, "sb", fake)
    return fake


@pytest.fixture
def _stub_rag_and_llm(monkeypatch):
    """region_guidance 와이어링 검증: RAG는 grounded 고정 응답, LLM 호출은 프롬프트만 캡처."""
    async def fake_retrieve(*a, **k):
        return {"grounded": True, "context": "some nutrition evidence", "max_score": 0.9}

    monkeypatch.setattr(retriever_module, "retrieve", fake_retrieve)

    captured = []

    async def fake_ainvoke(self, messages, *a, **k):
        captured.append(messages)

        class _Resp:
            content = _LLM_JSON_RESPONSE
        return _Resp()

    monkeypatch.setattr(ConfiguredChatModel, "ainvoke", fake_ainvoke)
    return captured


async def test_inbody_prompt_includes_intl_guidance_when_region_set(fake_agent_tools_sb, _stub_rag_and_llm):
    await inbody_node({"user_id": "u1", "user_region": "INTL"})

    prompt_text = str(_stub_rag_and_llm[-1])
    assert REGION_GUIDANCE["INTL"] in prompt_text
    assert REGION_GUIDANCE["KR"] not in prompt_text


async def test_inbody_prompt_defaults_to_kr_guidance_when_region_missing(fake_agent_tools_sb, _stub_rag_and_llm):
    await inbody_node({"user_id": "u1"})

    prompt_text = str(_stub_rag_and_llm[-1])
    assert REGION_GUIDANCE["KR"] in prompt_text
