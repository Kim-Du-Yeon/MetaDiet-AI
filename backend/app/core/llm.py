"""Lazy Gemini models; importing the application never requires a Gemini key."""
from typing import Any

from langchain_core.runnables import Runnable
from langchain_google_genai import ChatGoogleGenerativeAI

from app.core.config import get_settings


def response_text(response: Any) -> str:
    content = response.content
    if isinstance(content, str):
        return content
    return "".join(
        block.get("text", "") for block in content
        if isinstance(block, dict) and block.get("type") == "text"
        and not block.get("thought", False)
    )


class ConfiguredChatModel(Runnable):
    """Keep provider construction lazy while preserving native tools and tracing."""

    def __init__(self, *, role: str = "chat", temperature: float = 0,
                 max_tokens: int | None = None):
        if role not in {"chat", "vision", "eval"}:
            raise ValueError(f"Unknown model role: {role}")
        self.role = role
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._provider = None

    def _client(self):
        if self._provider is None:
            settings = get_settings()
            if not settings.gemini_api_key.strip():
                raise ValueError("Set GEMINI_API_KEY in backend/.env before calling Gemini")
            model = {"chat": settings.gemini_model,
                     "vision": settings.gemini_vision_model,
                     "eval": settings.gemini_eval_model}[self.role]
            self._provider = ChatGoogleGenerativeAI(
                model=model, api_key=settings.gemini_api_key,
                temperature=self.temperature, max_tokens=self.max_tokens,
                timeout=settings.eval_model_timeout_seconds if self.role == "eval" else settings.model_timeout_seconds,
                max_retries=settings.model_max_retries,
            )
        return self._provider

    def invoke(self, input, config=None, **kwargs):
        return self._text_response(self._client().invoke(input, config=config, **kwargs))

    async def ainvoke(self, input, config=None, **kwargs):
        return self._text_response(await self._client().ainvoke(input, config=config, **kwargs))

    @staticmethod
    def _text_response(response):
        # Legacy text/JSON nodes expect a string. Native tool-bound agents retain
        # the provider messages (including tool calls and thought signatures).
        if hasattr(response, "model_copy") and isinstance(response.content, list):
            return response.model_copy(update={"content": response_text(response)})
        return response

    async def astream(self, input, config=None, **kwargs):
        async for chunk in self._client().astream(input, config=config, **kwargs):
            yield chunk

    def bind_tools(self, tools, **kwargs):
        return self._client().bind_tools(tools, **kwargs)

    def with_structured_output(self, schema, **kwargs):
        return self._client().with_structured_output(schema, **kwargs)


def get_chat_model(**kwargs) -> ConfiguredChatModel:
    return ConfiguredChatModel(**kwargs)


def get_evaluation_model():
    """Ragas requires the provider BaseChatModel generate/agenerate interface."""
    return get_chat_model(role="eval")._client()
