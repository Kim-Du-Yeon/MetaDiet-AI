"""Request-scoped execution events for SSE progress and reconnect replay."""
from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Awaitable, Callable


EventSink = Callable[[str, dict[str, Any]], Awaitable[None]]
_event_sink: ContextVar[EventSink | None] = ContextVar("execution_event_sink", default=None)


async def emit_runtime_event(kind: str, **payload: Any) -> None:
    sink = _event_sink.get()
    if sink is not None:
        await sink(kind, payload)


@asynccontextmanager
async def measure_stage(stage: str):
    """Fixed internal labels only; never include arguments, output or errors."""
    started = time.perf_counter()
    try:
        yield
    finally:
        await emit_runtime_event('stage_timing', stage=stage,
                                 elapsed_ms=round((time.perf_counter() - started) * 1000, 3))


def set_event_sink(sink: EventSink):
    return _event_sink.set(sink)


def reset_event_sink(token) -> None:
    _event_sink.reset(token)


@dataclass
class ExecutionEventJournal:
    run_id: str
    events: list[dict[str, Any]] = field(default_factory=list)
    finished: bool = False
    task: asyncio.Task | None = None
    timings: dict[str, float] = field(default_factory=dict)
    _condition: asyncio.Condition = field(default_factory=asyncio.Condition)

    async def publish(self, event_type: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        async with self._condition:
            event = {"type": event_type, "run_id": self.run_id,
                     "seq": len(self.events) + 1, **(payload or {})}
            self.events.append(event)
            self._condition.notify_all()
            return event

    async def finish(self) -> None:
        async with self._condition:
            self.finished = True
            self._condition.notify_all()

    async def subscribe(self, after_seq: int = 0) -> AsyncIterator[dict[str, Any]]:
        index = max(0, after_seq)
        while True:
            async with self._condition:
                await self._condition.wait_for(lambda: index < len(self.events) or self.finished)
                batch = self.events[index:]
                index = len(self.events)
                finished = self.finished
            for event in batch:
                yield event
            if finished and index >= len(self.events):
                return


_journals: dict[str, ExecutionEventJournal] = {}
_MAX_JOURNALS = 128


def get_or_create_journal(run_id: str, scope: str = "") -> tuple[ExecutionEventJournal, bool]:
    key = f"{scope}:{run_id}"
    existing = _journals.get(key)
    if existing is not None:
        return existing, False
    if len(_journals) >= _MAX_JOURNALS:
        for key, journal in list(_journals.items()):
            if journal.finished:
                _journals.pop(key, None)
                if len(_journals) < _MAX_JOURNALS:
                    break
    journal = ExecutionEventJournal(run_id)
    _journals[key] = journal
    return journal, True


def find_journal(run_id: str, scope: str = "") -> ExecutionEventJournal | None:
    return _journals.get(f"{scope}:{run_id}")


_TOOL_PHASES = {
    "read_profile": ("records", "사용자 정보 확인 중"),
    "read_intake": ("records", "오늘 섭취 기록 확인 중"),
    "read_recent_intake": ("records", "최근 식사 기록 확인 중"),
    "read_measurements": ("records", "인바디 기록 확인 중"),
    "assess_goal_progress": ("analysis", "목표 진행 상황 분석 중"),
    "search_foods": ("nutrition", "음식 정보 검색 중"),
    "nutrition_lookup": ("nutrition", "영양 성분 계산 중"),
    "search_evidence": ("evidence", "근거 자료 검색 중"),
    "propose_meal": ("validation", "식단 제안 검토 중"),
    "propose_strategy": ("validation", "전략 변경안 검토 중"),
    "propose_meal_change": ("validation", "기록 변경안 검토 중"),
}


def progress_for_runtime_event(kind: str, **payload: Any) -> dict[str, Any] | None:
    if kind == "coaching_context_ready" or (kind == "model_started" and payload.get("context_verified")):
        return {"phase": "coaching_context", "label": "확인한 기록을 바탕으로 답변 준비 중"}
    if kind == "model_started" and payload.get("agent") == "supervisor":
        return {"phase": "intent", "label": "요청 의도 분석 중"}
    if kind == "delegated":
        labels = {"meal": "식사 전문 Agent에 위임 중", "goal": "목표 전문 Agent에 위임 중",
                  "evidence": "근거 전문 Agent에 위임 중"}
        agent = payload.get("agent")
        return {"phase": "delegation", "label": labels.get(agent, "전문 Agent에 위임 중"), "agent": agent}
    if kind == "tool_started":
        tool = payload.get("tool")
        if tool in _TOOL_PHASES:
            phase, label = _TOOL_PHASES[tool]
            return {"phase": phase, "label": label, "tool": tool, "agent": payload.get("agent")}
    return None
