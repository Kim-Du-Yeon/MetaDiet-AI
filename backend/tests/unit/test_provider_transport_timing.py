import httpx
import pytest

from app.agents.execution_stream import set_event_sink, reset_event_sink


async def test_transport_records_numeric_phases_without_metadata():
    from app.core.provider_transport import TimedTransport
    events = []
    async def sink(kind, payload):
        events.append((kind, payload))
    async def handler(request):
        trace = request.extensions['trace']
        for phase in ('connection.connect_tcp', 'connection.start_tls',
                      'http11.send_request_body', 'http11.receive_response_headers',
                      'http11.receive_response_body'):
            await trace(phase + '.started', {'secret': 'never log'})
            await trace(phase + '.complete', {'return_value': 'private health'})
        return httpx.Response(200, json={'ok': True})
    transport = TimedTransport()
    await transport.aclose()
    transport.async_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    token = set_event_sink(sink)
    try:
        async with httpx.AsyncClient(transport=transport) as client:
            response = await client.get('https://example.invalid/?key=secret')
        assert response.json() == {'ok': True}
    finally:
        reset_event_sink(token)
        transport.close()
    assert {p['stage'] for k, p in events} == {
        'transport_connect', 'transport_tls', 'transport_send_body',
        'transport_wait_headers', 'transport_receive_body'}
    assert all(set(p) == {'stage', 'elapsed_ms'} and p['elapsed_ms'] >= 0 for _, p in events)
    assert 'secret' not in str(events) and 'private' not in str(events)


async def test_failed_trace_keeps_elapsed_without_exception_contents():
    from app.core.provider_transport import PhaseTrace
    events = []
    async def sink(kind, payload):
        events.append((kind, payload))
    token = set_event_sink(sink)
    try:
        trace = PhaseTrace()
        await trace('connection.connect_tcp.started', {})
        await trace('connection.connect_tcp.failed', {'exception': ValueError('secret')})
        await trace('unknown_event.complete', {'secret': 'secret'})
    finally:
        reset_event_sink(token)
    assert len(events) == 1 and events[0][1]['stage'] == 'transport_connect'
    assert 'secret' not in str(events)


async def test_parallel_trace_instances_do_not_mix_requests():
    import asyncio
    from app.core.provider_transport import PhaseTrace
    events = []
    async def sink(kind, payload):
        events.append((kind, payload))
    token = set_event_sink(sink)
    async def one():
        trace = PhaseTrace()
        await trace('http11.receive_response_headers.started', {})
        await asyncio.sleep(0)
        await trace('http11.receive_response_headers.complete', {})
    try:
        await asyncio.gather(*(one() for _ in range(10)))
    finally:
        reset_event_sink(token)
    assert len(events) == 10


async def test_installed_sdk_uses_injected_transport_and_closes_it(monkeypatch):
    from types import SimpleNamespace
    from app.core import llm
    from langchain_google_genai import ChatGoogleGenerativeAI
    settings = SimpleNamespace(gemini_api_key='synthetic-only', gemini_model='gemini-3.8-flash',
        gemini_vision_model='unused', gemini_eval_model='unused',
        model_timeout_seconds=5, eval_model_timeout_seconds=5, model_max_retries=0)
    monkeypatch.setattr(llm, 'get_settings', lambda: settings)
    monkeypatch.setattr(llm, 'ChatGoogleGenerativeAI', ChatGoogleGenerativeAI)
    model = llm.get_chat_model(transport_timing=True)
    provider = model._client()
    transport = provider.client_args['transport']
    await transport.aclose()
    seen = []
    async def handler(request):
        seen.append(request.method)
        assert isinstance(request.extensions.get('timeout'), dict)
        assert callable(request.extensions['trace'])
        return httpx.Response(200, json={'candidates': [{'content': {'role': 'model',
            'parts': [{'text': 'synthetic answer'}]}, 'finishReason': 'STOP'}],
            'usageMetadata': {'promptTokenCount': 2, 'candidatesTokenCount': 2, 'totalTokenCount': 4}})
    transport.async_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        response = await model.ainvoke('synthetic input')
        assert response.content == 'synthetic answer' and seen == ['POST']
    finally:
        await provider.aclose()
    assert transport.async_client.is_closed and transport.sync_client.is_closed
