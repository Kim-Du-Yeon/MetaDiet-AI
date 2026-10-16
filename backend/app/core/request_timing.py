"""Non-sensitive request correlation; identifiers are never authorization."""
import logging
import time
from contextvars import ContextVar
from uuid import UUID, uuid4

request_ids = ContextVar('request_ids', default={})


def safe_uuid(value):
    try:
        return str(UUID(value))
    except (ValueError, TypeError, AttributeError):
        return str(uuid4())


def timing(stage, elapsed_ms):
    logging.getLogger(__name__).warning('request_timing request_id=%s attempt_id=%s stage=%s elapsed_ms=%.3f',
        request_ids.get().get('request_id', 'none'), request_ids.get().get('attempt_id', 'none'), stage, elapsed_ms)


class RequestTimingMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope.get('path') not in {'/chat', '/chat/resume'}:
            return await self.app(scope, receive, send)
        headers = dict(scope.get('headers', []))
        ids = {key: safe_uuid(headers.get(header, b'').decode('ascii', errors='ignore'))
               for key, header in [('request_id', b'x-request-id'), ('attempt_id', b'x-attempt-id')]}
        token = request_ids.set(ids)
        started = time.perf_counter()
        first_body = False
        async def measured_send(message):
            nonlocal first_body
            if message['type'] == 'http.response.start':
                message = {**message, 'headers': [*message.get('headers', []),
                    (b'x-request-id', ids['request_id'].encode()), (b'x-attempt-id', ids['attempt_id'].encode())]}
                timing('response_headers', (time.perf_counter() - started) * 1000)
            if message['type'] == 'http.response.body' and message.get('body') and not first_body:
                first_body = True
                timing('first_body_send', (time.perf_counter() - started) * 1000)
            await send(message)
        try:
            await self.app(scope, receive, measured_send)
        finally:
            timing('request_finish', (time.perf_counter() - started) * 1000)
            request_ids.reset(token)
