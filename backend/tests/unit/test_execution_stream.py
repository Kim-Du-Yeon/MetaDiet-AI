import asyncio

import pytest

from app.agents.execution_stream import ExecutionEventJournal, progress_for_runtime_event
from app.api.routes.main import _follow_or_resume_run, _run_and_stream


@pytest.mark.asyncio
async def test_blocked_graph_result_is_not_overwritten_as_completed():
    class BlockedGraph:
        async def ainvoke(self, graph_input, config=None):
            return {'execution_status': 'blocked'}

        async def aupdate_state(self, config, values):
            assert values['execution_status'] == 'blocked'

    assert [frame async for frame in _run_and_stream(
        BlockedGraph(), {'message': 'food'}, {'configurable': {'thread_id': 'u_t'}}, 'blocked-test'
    )] == []


@pytest.mark.asyncio
async def test_journal_replays_only_events_after_sequence_and_finishes():
    journal = ExecutionEventJournal("run-1")
    await journal.publish("progress", {"phase": "intent", "label": "의도 분석 중"})
    await journal.publish("progress", {"phase": "records", "label": "기록 조회 중"})
    await journal.finish()

    replay = [event async for event in journal.subscribe(after_seq=1)]

    assert [event["seq"] for event in replay] == [2]
    assert replay[0]["run_id"] == "run-1"


@pytest.mark.asyncio
async def test_subscriber_waits_for_live_event_without_restarting_execution():
    journal = ExecutionEventJournal("run-2")

    async def collect():
        return [event async for event in journal.subscribe()]

    task = asyncio.create_task(collect())
    await asyncio.sleep(0)
    await journal.publish("progress", {"phase": "evidence", "label": "근거 검색 중"})
    await journal.finish()

    assert (await task)[0]["phase"] == "evidence"


def test_runtime_events_map_to_truthful_user_visible_phases():
    assert progress_for_runtime_event("model_started", agent="supervisor")["phase"] == "intent"
    assert progress_for_runtime_event("delegated", agent="meal")["phase"] == "delegation"
    assert progress_for_runtime_event("tool_started", tool="read_intake")["phase"] == "records"
    assert progress_for_runtime_event("tool_started", tool="search_evidence")["phase"] == "evidence"
    assert progress_for_runtime_event("tool_started", tool="propose_strategy")["phase"] == "validation"
    assert progress_for_runtime_event("tool_finished", tool="read_profile") is None


@pytest.mark.asyncio
async def test_graph_runtime_events_are_forwarded_before_execution_completes():
    from app.agents.execution_stream import emit_runtime_event

    class FakeGraph:
        invocation_id = None

        async def ainvoke(self, graph_input, config=None):
            self.invocation_id = str(config["run_id"])
            assert config["metadata"]["trace_id"] == self.invocation_id
            await emit_runtime_event("model_started", agent="supervisor")
            await emit_runtime_event("delegated", agent="meal")
            await emit_runtime_event("tool_started", agent="meal", tool="read_intake")

        async def aupdate_state(self, config, values):
            from uuid import UUID
            UUID(values["trace_id"])
            assert values["trace_id"] == self.invocation_id
            assert {k: v for k, v in values.items() if k != "trace_id"} == {"execution_status": "completed", "execution_error": None}

    frames = [frame async for frame in _run_and_stream(
        FakeGraph(), {"message": "저녁 추천"}, {"configurable": {"thread_id": "u_t"}}, "run-live"
    )]

    assert [f'"seq": {seq}' in frame for seq, frame in enumerate(frames, start=1)] == [True, True, True]
    assert '"phase": "intent"' in frames[0]
    assert '"phase": "records"' in frames[-1]


@pytest.mark.asyncio
async def test_failed_run_is_terminal_and_same_run_is_not_invoked_twice():
    class FailingGraph:
        calls = 0

        async def ainvoke(self, graph_input, config=None):
            self.calls += 1
            raise RuntimeError("provider detail must not leak")

        async def aupdate_state(self, config, values):
            from uuid import UUID
            UUID(values["trace_id"])
            assert {k: v for k, v in values.items() if k != "trace_id"} == {"execution_status": "failed", "execution_error": "execution_failed"}

    graph = FailingGraph()
    config = {"configurable": {"thread_id": "user-thread-failure"}}
    for _ in range(2):
        frames = []
        with pytest.raises(RuntimeError):
            async for frame in _run_and_stream(graph, {}, config, "terminal-run"):
                frames.append(frame)
        assert any('"type": "failed"' in frame for frame in frames)
        assert all("provider detail" not in frame for frame in frames)
    assert graph.calls == 1


@pytest.mark.asyncio
async def test_running_checkpoint_without_local_journal_resumes_after_pod_change():
    from app.agents.execution_stream import emit_runtime_event

    class FakeGraph:
        inputs = []
        async def aget_state(self, config):
            from types import SimpleNamespace
            from app.core.prompt_release_control import local_snapshot
            return SimpleNamespace(values={"prompt_pin":local_snapshot().wire})

        async def ainvoke(self, graph_input, config=None):
            self.inputs.append(graph_input)
            await emit_runtime_event("tool_started", agent="meal", tool="read_intake")

        async def aupdate_state(self, config, values):
            from uuid import UUID
            UUID(values["trace_id"])
            assert {k: v for k, v in values.items() if k != "trace_id"} == {"execution_status": "completed", "execution_error": None}

    graph = FakeGraph()
    config = {"configurable": {"thread_id": "pod-recovery-thread"}}
    frames = [frame async for frame in _follow_or_resume_run(
        graph, config, "pod-recovery-run", after_seq=0
    )]

    assert graph.inputs == [None]
    assert any('"phase": "records"' in frame for frame in frames)
