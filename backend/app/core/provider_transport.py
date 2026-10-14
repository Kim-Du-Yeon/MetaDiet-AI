"""Opt-in HTTPX experiment: fixed numeric labels, no trace metadata retained.

connect includes DNS/TCP; header wait includes network and opaque provider work.
These are observable transport intervals, not server thinking/GPU timings.
"""
import time
import httpx

from app.agents.execution_stream import emit_runtime_event


_PHASES = {
    'connection.connect_tcp': 'transport_connect',
    'connection.start_tls': 'transport_tls',
    'http11.send_request_headers': 'transport_send_headers',
    'http11.send_request_body': 'transport_send_body',
    'http11.receive_response_headers': 'transport_wait_headers',
    'http11.receive_response_body': 'transport_receive_body',
    'http2.send_request_headers': 'transport_send_headers',
    'http2.send_request_body': 'transport_send_body',
    'http2.receive_response_headers': 'transport_wait_headers',
    'http2.receive_response_body': 'transport_receive_body',
}


class PhaseTrace:
    """One trace per HTTP attempt; never read the SDK's sensitive info dict."""
    def __init__(self):
        self.started = {}

    async def __call__(self, event, info):
        phase, _, outcome = event.rpartition('.')
        label = _PHASES.get(phase)
        if label is None:
            return
        if outcome == 'started':
            self.started[phase] = time.perf_counter()
        elif outcome in {'complete', 'failed'} and phase in self.started:
            elapsed = (time.perf_counter() - self.started.pop(phase)) * 1000
            await emit_runtime_event('stage_timing', stage=label, elapsed_ms=round(elapsed, 3))


class TimedTransport(httpx.BaseTransport, httpx.AsyncBaseTransport):
    """Both interfaces are needed: LangChain passes client_args to both clients.

Delegate through standard clients so environment proxies, CA verification and
request timeout extensions remain supported. SDK owns this transport's lifetime.
No retry is added. The transport intentionally selects HTTPX instead of aiohttp.
"""
    def __init__(self):
        self.sync_client = httpx.Client()
        self.async_client = httpx.AsyncClient()

    def handle_request(self, request):
        return self.sync_client.send(request, stream=True)

    async def handle_async_request(self, request):
        request.extensions['trace'] = PhaseTrace()
        return await self.async_client.send(request, stream=True)

    def close(self):
        self.sync_client.close()

    async def aclose(self):
        await self.async_client.aclose()
