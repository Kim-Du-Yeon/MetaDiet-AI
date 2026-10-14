"""One bounded retry for side-effect-free external generation and reads only."""
import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from typing import TypeVar

import httpx
from google.genai.errors import APIError

T = TypeVar('T')
logger = logging.getLogger(__name__)


def transient(exc: Exception) -> bool:
    if isinstance(exc, (httpx.TransportError, TimeoutError, ConnectionError)):
        return True
    # LangChain may wrap a provider exception; inspect typed causes, not text.
    for _ in range(4):
        if isinstance(exc, APIError):
            return exc.code in {408, 429, 500, 502, 503, 504}
        if isinstance(exc, httpx.HTTPStatusError):
            return exc.response.status_code in {408, 429, 500, 502, 503, 504}
        exc = exc.__cause__
        if exc is None:
            break
    return False


async def retry_external(call: Callable[[], Awaitable[T]], *, operation: str,
                         before_retry: Callable[[], Awaitable[None]] | None = None,
                         delay: float = 1) -> T:
    """Caller retains its overall deadline. Never wrap writes or a whole agent."""
    for attempt in range(2):
        try:
            return await call()
        except Exception as exc:
            retry = attempt == 0 and transient(exc)
            logger.warning('external_call_failure operation=%s error_type=%s retry=%s',
                           operation, type(exc).__name__, retry)
            from app.agents.execution_stream import emit_runtime_event
            await emit_runtime_event('external_failure', operation=operation,
                                     error_type=type(exc).__name__, retry=retry)
            if not retry:
                raise
            await asyncio.sleep(delay + random.uniform(0, delay / 4))
            if before_retry:
                await before_retry()
    raise AssertionError('unreachable')
