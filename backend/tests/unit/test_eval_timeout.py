from types import SimpleNamespace
from unittest.mock import Mock


def test_judge_has_separate_deadline_from_service(monkeypatch):
    import app.core.llm as llm
    settings = SimpleNamespace(gemini_api_key="synthetic-key", gemini_model="service",
        gemini_vision_model="vision", gemini_eval_model="judge", model_timeout_seconds=30,
        eval_model_timeout_seconds=90, model_max_retries=0)
    monkeypatch.setattr(llm, "get_settings", lambda: settings)
    provider = Mock()
    monkeypatch.setattr(llm, "ChatGoogleGenerativeAI", provider)
    llm.ConfiguredChatModel(role="eval")._client()
    assert provider.call_args.kwargs["timeout"] == 90
    llm.ConfiguredChatModel(role="chat")._client()
    assert provider.call_args.kwargs["timeout"] == 30
