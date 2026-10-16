import asyncio
from uuid import uuid4
import pytest
from app.core.request_timing import RequestTimingMiddleware, request_ids


async def test_ids_are_validated_echoed_and_isolated(caplog):
    rows = []
    async def app(scope, receive, send):
        await asyncio.sleep(0)
        rows.append(dict(request_ids.get()))
        await send({'type':'http.response.start','status':200,'headers':[]})
        await send({'type':'http.response.body','body':b'ok'})
    middleware = RequestTimingMiddleware(app)
    async def call(request, attempt):
        messages = []
        async def send(message): messages.append(message)
        await middleware({'type':'http','path':'/chat','headers':[
            (b'x-request-id',request.encode()), (b'x-attempt-id',attempt.encode())]}, None, send)
        return dict(messages[0]['headers'])
    first, second = str(uuid4()), str(uuid4())
    result = await asyncio.gather(call(first, first), call(second, 'private\ninvalid'))
    assert {row['request_id'] for row in rows} == {first, second}
    assert result[0][b'x-request-id'].decode() == first
    assert result[1][b'x-attempt-id'] != b'private\ninvalid'
    assert 'private' not in caplog.text
    assert request_ids.get() == {}


async def test_exception_logs_finish_and_clears_context(caplog):
    async def app(*args): raise ValueError('private error')
    with pytest.raises(ValueError):
        await RequestTimingMiddleware(app)({'type':'http','path':'/chat','headers':[]}, None, None)
    assert request_ids.get() == {}
    assert 'request_finish' in caplog.text and 'private error' not in caplog.text
