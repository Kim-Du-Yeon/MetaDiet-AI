from types import SimpleNamespace
import asyncio
import httpx
import pytest


async def test_read_error_retries_on_new_client_and_preserves_owner_date(monkeypatch):
    from app.db import public_stats as stats
    clients, requests = [], []
    settings = SimpleNamespace(supabase_url='https://example.invalid', supabase_service_key='test-only')
    monkeypatch.setattr(stats, 'get_settings', lambda: settings)
    monkeypatch.setattr(stats, 'service_today', lambda: __import__('datetime').date(2026, 10, 16))
    real_client = httpx.AsyncClient
    def factory(**kwargs):
        index = len(clients)
        def handle(request):
            requests.append(request)
            if index == 0:
                raise httpx.ReadError('synthetic receive failure')
            return httpx.Response(200, json=[{'calories': 750}] if request.url.path.endswith('meal_logs') else [{'daily_calories': 1800}])
        client = real_client(transport=httpx.MockTransport(handle), **kwargs)
        clients.append(client)
        return client
    monkeypatch.setattr(stats, '_new_client', factory)
    assert await stats.read_public_stats('owner') == {'today_calories': 750, 'target_calories': 1800}
    assert len(clients) == 2 and all(c.is_closed for c in clients)
    assert all(r.url.params['user_id'] == 'eq.owner' for r in requests)
    assert requests[-2].url.params['log_date'] == 'eq.2026-10-16'


@pytest.mark.parametrize('status', [401, 403, 400])
async def test_permanent_http_failure_is_not_retried(monkeypatch, status):
    from app.db import public_stats as stats
    monkeypatch.setattr(stats, 'get_settings', lambda: SimpleNamespace(supabase_url='https://example.invalid', supabase_service_key='test-only'))
    real_client, clients = httpx.AsyncClient, []
    def factory(**kwargs):
        client = real_client(transport=httpx.MockTransport(lambda _: httpx.Response(status)), **kwargs)
        clients.append(client)
        return client
    monkeypatch.setattr(stats, '_new_client', factory)
    assert await stats.read_public_stats('owner') == {}
    assert len(clients) == 1 and clients[0].is_closed


async def test_cancellation_closes_transport_without_retry(monkeypatch):
    from app.db import public_stats as stats
    monkeypatch.setattr(stats, 'get_settings', lambda: SimpleNamespace(supabase_url='https://example.invalid', supabase_service_key='test-only'))
    real_client, clients = httpx.AsyncClient, []
    async def handle(_):
        raise asyncio.CancelledError()
    def factory(**kwargs):
        client = real_client(transport=httpx.MockTransport(handle), **kwargs)
        clients.append(client)
        return client
    monkeypatch.setattr(stats, '_new_client', factory)
    with pytest.raises(asyncio.CancelledError):
        await stats.read_public_stats('owner')
    assert len(clients) == 1 and clients[0].is_closed


@pytest.mark.parametrize('meals, strategy, expected', [
    ([], [{'daily_calories': 1800}], {'today_calories': 0, 'target_calories': 1800}),
    ([{'calories': 300}], [], {}),
])
async def test_missing_target_is_unavailable_not_invented_zero(monkeypatch, meals, strategy, expected):
    from app.db import public_stats as stats
    monkeypatch.setattr(stats, 'get_settings', lambda: SimpleNamespace(supabase_url='https://example.invalid', supabase_service_key='test-only'))
    real_client = httpx.AsyncClient
    monkeypatch.setattr(stats, '_new_client', lambda **kw: real_client(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json=meals if r.url.path.endswith('meal_logs') else strategy)), **kw))
    assert await stats.read_public_stats('owner') == expected


async def test_repeated_read_error_is_bounded_and_does_not_return_zero(monkeypatch):
    from app.db import public_stats as stats
    monkeypatch.setattr(stats, 'get_settings', lambda: SimpleNamespace(supabase_url='https://example.invalid', supabase_service_key='test-only'))
    real_client, clients = httpx.AsyncClient, []
    def handle(_):
        raise httpx.ReadError('synthetic receive failure')
    def factory(**kwargs):
        client = real_client(transport=httpx.MockTransport(handle), **kwargs)
        clients.append(client)
        return client
    monkeypatch.setattr(stats, '_new_client', factory)
    assert await stats.read_public_stats('owner') == {}
    assert len(clients) == 2 and all(c.is_closed for c in clients)


async def test_total_deadline_cancels_read_closes_client_and_reports_failure(monkeypatch):
    from app.db import public_stats as stats
    from app.agents.execution_stream import set_event_sink, reset_event_sink
    monkeypatch.setattr(stats, 'get_settings', lambda: SimpleNamespace(supabase_url='https://example.invalid', supabase_service_key='test-only'))
    monkeypatch.setattr(stats, '_TOTAL_TIMEOUT', .02)
    real_client, clients, events = httpx.AsyncClient, [], []
    async def handle(_):
        await asyncio.Event().wait()
    def factory(**kwargs):
        client = real_client(transport=httpx.MockTransport(handle), **kwargs)
        clients.append(client)
        return client
    async def sink(kind, payload):
        events.append((kind, payload))
    monkeypatch.setattr(stats, '_new_client', factory)
    context = set_event_sink(sink)
    try:
        assert await stats.read_public_stats('owner') == {}
    finally:
        reset_event_sink(context)
    assert len(clients) == 1 and clients[0].is_closed
    assert ('external_failure', {'operation':'public_stats', 'error_type':'TimeoutError', 'retry':False}) in events
