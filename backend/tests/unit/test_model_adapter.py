from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.core import llm


def test_model_is_lazy_and_missing_key_is_actionable(monkeypatch):
    monkeypatch.setattr(llm, "get_settings", lambda: SimpleNamespace(gemini_api_key=""))
    model = llm.get_chat_model()
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        model.invoke("hello")


def test_role_and_key_are_explicit_and_tools_stay_native(monkeypatch):
    settings = SimpleNamespace(gemini_api_key="test-key", gemini_model="chat-test",
        gemini_vision_model="vision-test", gemini_eval_model="judge-test",
        model_timeout_seconds=30, model_max_retries=0)
    monkeypatch.setattr(llm, "get_settings", lambda: settings)
    factory = MagicMock()
    monkeypatch.setattr(llm, "ChatGoogleGenerativeAI", factory)
    model = llm.get_chat_model(role="vision")
    model.bind_tools(["fake-tool"])
    assert factory.call_args.kwargs["model"] == "vision-test"
    assert factory.call_args.kwargs["api_key"] == "test-key"
    factory.return_value.bind_tools.assert_called_once_with(["fake-tool"])


def test_text_blocks_exclude_thought_and_tool_payloads():
    assert llm.response_text(SimpleNamespace(content=[
        {"type": "text", "text": "answer"},
        {"type": "reasoning", "text": "hidden"},
        {"type": "text", "text": "private", "thought": True},
    ])) == "answer"


async def test_async_model_passes_config_to_provider(monkeypatch):
    from unittest.mock import AsyncMock
    provider = SimpleNamespace(ainvoke=AsyncMock(return_value="answer"))
    model = llm.get_chat_model()
    monkeypatch.setattr(model, "_client", lambda: provider)
    assert await model.ainvoke("hello", config={"tags": ["test"]}) == "answer"
    from app.core.prompts import prompt_metadata
    provider.ainvoke.assert_awaited_once_with("hello", config={"tags": ["test"], "metadata":prompt_metadata()})
