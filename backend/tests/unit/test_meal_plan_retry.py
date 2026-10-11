import json

import pytest
from app.core.llm import ConfiguredChatModel

import app.agents.meal_plan.node as meal_plan_module


class _Resp:
    def __init__(self, content):
        self.content = content


async def test_retries_once_on_malformed_json_then_succeeds(monkeypatch):
    calls = []
    responses = [_Resp("이건 JSON이 아님"), _Resp(json.dumps({"plan_date": "2026-01-01", "meals": []}))]

    async def fake_ainvoke(self, messages, *a, **k):
        calls.append(messages)
        return responses[len(calls) - 1]

    monkeypatch.setattr(ConfiguredChatModel, "ainvoke", fake_ainvoke)

    result = await meal_plan_module._generate_plan_json([])

    assert len(calls) == 2
    assert result["plan_date"] == "2026-01-01"


async def test_raises_after_second_failure(monkeypatch):
    async def fake_ainvoke(self, messages, *a, **k):
        return _Resp("여전히 JSON이 아님")

    monkeypatch.setattr(ConfiguredChatModel, "ainvoke", fake_ainvoke)

    with pytest.raises(json.JSONDecodeError):
        await meal_plan_module._generate_plan_json([])
