"""Lazy Gemini models; importing the application never requires a Gemini key."""
from typing import Any, Literal
import asyncio
import hashlib
from dataclasses import dataclass

from langchain_core.runnables import Runnable
from langchain_google_genai import ChatGoogleGenerativeAI

from app.core.config import get_settings


@dataclass(repr=False)
class _SharedProvider:
    loop: Any
    key: tuple
    provider: Any


# One bounded slot, only for opted-in coaching. No messages or bound tools.
_shared_provider: _SharedProvider | None = None


async def close_shared_model_client():
    """Shutdown in the owning loop, after in-flight requests have drained."""
    global _shared_provider
    entry = _shared_provider
    if entry is None:
        return
    if entry.loop is not asyncio.get_running_loop():
        return
    _shared_provider = None
    await entry.provider.aclose()


def response_text(response: Any) -> str:
    content = response.content
    if isinstance(content, str):
        return content
    return "".join(
        block if isinstance(block, str) else block.get("text", "") for block in content
        if isinstance(block, str) or (isinstance(block, dict) and block.get("type") == "text"
        and not block.get("thought", False))
    )


class ConfiguredChatModel(Runnable):
    """Keep provider construction lazy while preserving native tools and tracing."""

    def __init__(self, *, role: str = "chat", temperature: float = 0,
                 task: str = "agent",
                 max_tokens: int | None = None,
                 model_name: str | None = None,
                 reuse_provider: bool = False,
                 transport_timing: bool = False,
                 thinking_level: Literal['low', 'medium', 'high'] | None = None):
        if role not in {"chat", "vision", "eval"}:
            raise ValueError(f"Unknown model role: {role}")
        if task not in {'agent', 'extraction', 'classification', 'query_translation'}:
            raise ValueError(f"Unknown model task: {task}")
        if role != 'chat' and task != 'agent':
            raise ValueError('Bounded task routing is only allowed for chat')
        self.task = task
        self._selection = None
        self.role = role
        self.transport_timing = transport_timing
        if reuse_provider and role != 'chat':
            raise ValueError('Provider reuse is only allowed for chat')
        self.reuse_provider = reuse_provider
        if model_name is not None and role != 'chat':
            raise ValueError('Model override is only allowed for chat')
        self.model_name = model_name
        if thinking_level not in {None, 'low', 'medium', 'high'}:
            raise ValueError(f'Unsupported thinking level: {thinking_level}')
        self.thinking_level = thinking_level
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._provider = None
        self.provider_reused = False

    def selection_metadata(self) -> dict:
        """Fixed-purpose labels and selected model ID only; never user content/keys."""
        if self._selection is not None:
            return dict(self._selection)
        settings = get_settings()
        routed = (self.role == 'chat' and self.task != 'agent' and
                  getattr(settings, 'model_routing_enabled', False) and self.model_name is None)
        model = self.model_name or (settings.gemini_simple_model if routed else {
            'chat': settings.gemini_model, 'vision': settings.gemini_vision_model,
            'eval': settings.gemini_eval_model}[self.role])
        return {'model_name': model, 'model_task': self.task, 'model_routing': bool(routed)}

    def _client(self):
        global _shared_provider
        if self._provider is None:
            settings = get_settings()
            if not settings.gemini_api_key.strip():
                raise ValueError("Set GEMINI_API_KEY in backend/.env before calling Gemini")
            self._selection = self.selection_metadata()
            model = self._selection['model_name']
            from app.core.prompts import prompt_metadata
            prompt_info = prompt_metadata()
            try:
                loop = asyncio.get_running_loop() if self.reuse_provider else None
            except RuntimeError:
                loop = None
            timeout = settings.eval_model_timeout_seconds if self.role == 'eval' else settings.model_timeout_seconds
            key = (ChatGoogleGenerativeAI, hashlib.sha256(settings.gemini_api_key.encode()).digest(),
                   model, self.role, self.task, self.temperature, self.max_tokens, self.thinking_level,
                   timeout, settings.model_max_retries, self.transport_timing,
                   prompt_info['prompt_bundle_sha256'])
            if loop is not None and _shared_provider is not None and (
                    _shared_provider.loop is loop and _shared_provider.key == key):
                self._provider = _shared_provider.provider
                self.provider_reused = True
                return self._provider
            transport_args = {}
            if self.transport_timing:
                from app.core.provider_transport import TimedTransport
                transport_args = {'client_args': {'transport': TimedTransport()}}
            self._provider = ChatGoogleGenerativeAI(
                model=model, api_key=settings.gemini_api_key,
                metadata={**prompt_info,'model_task':self.task,'model_role':self.role},
                temperature=self.temperature, max_tokens=self.max_tokens,
                timeout=timeout,
                max_retries=settings.model_max_retries,
                **transport_args,
                **({'thinking_level': self.thinking_level} if self.thinking_level is not None else {}),
            )
            if loop is not None and _shared_provider is None:
                _shared_provider = _SharedProvider(loop, key, self._provider)
        return self._provider

    def invoke(self, input, config=None, **kwargs):
        return self._text_response(self._client().invoke(input, config=config, **kwargs))

    def prepare(self):
        """Build only the stateless provider, before timing its external call."""
        self._client()

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
