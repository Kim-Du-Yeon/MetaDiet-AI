import pytest
from app.agents.execution_stream import set_event_sink, reset_event_sink


async def test_stage_timer_records_failure_without_exception_content():
    from app.agents.execution_stream import measure_stage
    events = []
    async def sink(kind, payload):
        events.append((kind, payload))
    token = set_event_sink(sink)
    try:
        with pytest.raises(ValueError):
            async with measure_stage('model_meal'):
                raise ValueError('private data')
    finally:
        reset_event_sink(token)
    assert events[0][0] == 'stage_timing'
    assert events[0][1]['stage'] == 'model_meal'
    assert events[0][1]['elapsed_ms'] >= 0
    assert 'private' not in str(events)


async def test_timings_are_separate_from_progress_and_replay(monkeypatch):
    from app.agents.execution_stream import measure_stage, get_or_create_journal
    from app.api.routes.main import _run_and_stream
    class Graph:
        async def ainvoke(self, *args, **kwargs):
            async with measure_stage('db_read'):
                pass
            return {}
        async def aupdate_state(self, *args, **kwargs):
            pass
    config = {'configurable': {'thread_id': 'timing-owned'}}
    assert [x async for x in _run_and_stream(Graph(), {}, config, 'timing-run')] == []
    journal, _ = get_or_create_journal('timing-run', 'timing-owned')
    assert {'db_read', 'graph_total', 'terminal_checkpoint'} <= set(journal.timings)
    assert all(v >= 0 for v in journal.timings.values())


async def test_completed_response_contains_duration_buckets(monkeypatch):
    import json
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from app.api.routes import main
    graph = SimpleNamespace(aget_state=AsyncMock(return_value=SimpleNamespace(
        values={'response': '완료', 'user_id': 'u'}, next=())))
    monkeypatch.setattr(main, '_public_stats', AsyncMock(return_value={}))
    events = [json.loads(x.split('data: ', 1)[1]) async for x in
              main._stream(graph, {'configurable': {'thread_id': 'u_t'}}, 'no-journal')]
    assert set(events[-1]['stage_timings_ms']) == {'response_snapshot', 'public_stats'}
    assert events[-1]['seq'] == 100000
