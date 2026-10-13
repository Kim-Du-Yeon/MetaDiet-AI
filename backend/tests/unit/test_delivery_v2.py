import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.api.routes import main


def events(frames):
    return [json.loads(f.split('data: ', 1)[1]) for f in frames]


async def test_health_exposes_commit_not_instance_or_credentials(monkeypatch):
    monkeypatch.setenv('RENDER_GIT_COMMIT', 'a' * 40)
    monkeypatch.setenv('RENDER_INSTANCE_ID', 'private-instance')
    result = await main.health()
    assert result['build']['commit'] == 'a' * 40
    assert 'private-instance' not in str(result)


async def test_v2_delivers_only_verified_answer_once_and_replays(monkeypatch):
    run = str(uuid4())
    config = {'configurable': {'thread_id': 'v2-user'}, 'metadata': {'stream_protocol': 2}}
    state = {'response': '**검증한 답변**', 'execution_status': 'completed', 'agent_used': 'meal'}
    graph = SimpleNamespace(ainvoke=AsyncMock(return_value=state),
        aget_state=AsyncMock(side_effect=lambda _: SimpleNamespace(values=state, next=())))
    async def update(_, values):
        state.update(values)
    graph.aupdate_state = AsyncMock(side_effect=update)
    monkeypatch.setattr(main, '_public_stats', AsyncMock(return_value={}))
    first = events([f async for f in main._run_and_stream(graph, {}, config, run)])
    assert [e['type'] for e in first] == ['started', 'answer_delta', 'completed']
    assert [e['seq'] for e in first] == [1, 2, 3]
    assert first[-1]['answer'] == state['response']
    assert first[-1]['build'] == first[0]['build']
    assert [f async for f in main._stream(graph, config, run)] == []
    replay = events([f async for f in main._replay_progress(config, run, 2)])
    assert replay == first[2:]
    graph.ainvoke.assert_awaited_once()


async def test_v2_missing_journal_never_restarts_model():
    graph = SimpleNamespace(ainvoke=AsyncMock())
    config = {'configurable': {'thread_id': 'lost-v2'}, 'metadata': {'stream_protocol': 2}}
    result = events([f async for f in main._follow_or_resume_run(graph, config, str(uuid4()), 8)])
    assert result[0]['type'] == 'failed' and result[0]['seq'] == 9
    graph.ainvoke.assert_not_awaited()


async def test_v2_completed_snapshot_recovers_final_answer_after_restart(monkeypatch):
    state = {'response': '최종 답변', 'execution_status': 'completed',
             'response_build': {'commit': 'previous-commit'}}
    graph = SimpleNamespace(aget_state=AsyncMock(return_value=SimpleNamespace(values=state, next=())))
    monkeypatch.setattr(main, '_public_stats', AsyncMock(return_value={}))
    config = {'configurable': {'thread_id': 'snapshot-v2'}, 'metadata': {'stream_protocol': 2}}
    result = events([f async for f in main._stream(graph, config, str(uuid4()), 17)])
    assert len(result) == 1 and result[0]['seq'] == 18
    assert result[0]['answer'] == '최종 답변'
    assert result[0]['build']['commit'] == 'previous-commit'


@pytest.mark.parametrize('after_seq,reconnect', [(1, False), (0, True)])
async def test_chat_retry_with_missing_checkpoint_does_not_invoke(monkeypatch, after_seq, reconnect):
    graph = SimpleNamespace(aget_state=AsyncMock(return_value=None), ainvoke=AsyncMock())
    monkeypatch.setattr(main, 'get_graph', lambda: graph)
    monkeypatch.setattr(main, 'serialized_stream', lambda generate, *args: generate())
    req = main.ChatRequest(message='점심 추천', stream_protocol=2, stream_run_id=str(uuid4()),
                           after_seq=after_seq, stream_reconnect=reconnect)
    response = await main.chat(req, 'synthetic-user')
    result = events([f async for f in response.body_iterator])
    graph.ainvoke.assert_not_awaited()
    assert result[0]['type'] == 'failed'


async def test_chat_replays_known_journal_even_when_checkpoint_is_superseded(monkeypatch):
    from app.agents.execution_stream import get_or_create_journal
    run = str(uuid4())
    journal, _ = get_or_create_journal(run, 'u_t')
    await journal.publish('completed', {'answer': '완료한 답변'})
    await journal.finish()
    graph = SimpleNamespace(aget_state=AsyncMock(return_value=SimpleNamespace(values={'run_id': 'other'}, next=())),
                            ainvoke=AsyncMock())
    monkeypatch.setattr(main, 'get_graph', lambda: graph)
    monkeypatch.setattr(main, 'serialized_stream', lambda generate, *args: generate())
    response = await main.chat(main.ChatRequest(message='점심 추천', thread_id='t',
        stream_protocol=2, stream_run_id=run, stream_reconnect=True), 'u')
    result = events([f async for f in response.body_iterator])
    assert result[0]['answer'] == '완료한 답변'
    graph.ainvoke.assert_not_awaited()
