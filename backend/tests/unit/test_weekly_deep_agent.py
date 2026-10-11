from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage


def tool_call(name, args):
    return AIMessage(content="", tool_calls=[
        {"name": name, "args": args, "id": name, "type": "tool_call"}
    ])


class ScriptedModel:
    def __init__(self, responses):
        self.responses = iter(responses)

    def bind_tools(self, schemas):
        self.schemas = schemas
        return self

    async def ainvoke(self, messages, config=None):
        return next(self.responses)


def test_weekly_deep_agent_has_two_delegates_and_human_gated_write(fake_sb):
    from app.agents.weekly_deep import WeeklyDeepTeam

    team = WeeklyDeepTeam({"user_id": "u1", "run_id": "r1", "thread_id": "t1",
                           "message": "주간 분석", "execution_usage": {}},
                          db=fake_sb, model_factory=lambda: None)
    assert [tool.name for tool in team.supervisor_tools()] == [
        "delegate_weekly_analysis", "delegate_weekly_evidence", "propose_strategy"
    ]
    assert team.supervisor_tools()[-1].effect == "proposal"


def test_weekly_supervisor_respects_readonly_tool_policy(fake_sb):
    from app.agents.weekly_deep import WeeklyDeepTeam

    team = WeeklyDeepTeam({"user_id": "u1", "run_id": "r1", "thread_id": "t1",
                           "message": "주간 분석", "execution_usage": {},
                           "tool_policy": ["read_profile", "search_evidence"]},
                          db=fake_sb, model_factory=lambda: None)
    assert team.supervisor_allowed_tools() == {
        "delegate_weekly_analysis", "delegate_weekly_evidence"
    }
    assert "propose_strategy" not in team.supervisor_allowed_tools()


@pytest.mark.asyncio
async def test_weekly_evidence_delegate_uses_mcp(monkeypatch, fake_sb):
    from app.agents.weekly_deep import WeeklyDeepTeam

    calls = []

    async def fake_call(name, arguments):
        calls.append((name, arguments))
        return {"grounded": True, "evidence": [{"evidence_id": "e1", "source": "WHO", "page": "1", "excerpt": "x"}]}

    monkeypatch.setattr("app.agents.weekly_deep.call_readonly_tool", fake_call)
    team = WeeklyDeepTeam({"user_id": "u1", "run_id": "r1", "thread_id": "t1",
                           "message": "주간 분석", "execution_usage": {}},
                          db=fake_sb, model_factory=lambda: None)
    result = await team.search_evidence_mcp(SimpleNamespace(query="감량 속도"))
    assert calls == [("search_evidence", {"query": "감량 속도", "k": 4})]
    assert result["grounded"] is True
    assert "e1" in team.evidence


def test_weekly_deep_budget_uses_separate_limits(monkeypatch, fake_sb):
    from app.agents.weekly_deep import WeeklyDeepTeam

    settings = SimpleNamespace(deep_agent_max_model_calls=20, deep_agent_max_tool_calls=30,
                               deep_agent_timeout_seconds=180,
                               agent_max_validation_attempts=3, agent_max_replans=2)
    monkeypatch.setattr("app.agents.weekly_deep.get_settings", lambda: settings)
    team = WeeklyDeepTeam({"user_id": "u1", "run_id": "r1", "thread_id": "t1",
                           "message": "주간 분석", "execution_usage": {}},
                          db=fake_sb, model_factory=lambda: None)
    assert (team.budget.max_model_calls, team.budget.max_tool_calls, team.budget.timeout_seconds) == (20, 30, 180)


@pytest.mark.asyncio
async def test_weekly_supervisor_delegates_both_specialists(monkeypatch, fake_sb):
    from app.agents.weekly_deep import WeeklyDeepTeam
    from tests.unit.test_diet_team import Model, call

    root = Model([call("delegate_weekly_analysis", {"query": "최근 기록 분석"}),
                  call("delegate_weekly_evidence", {"query": "감량 전략 근거"}),
                  AIMessage(content="기록 완전성을 고려한 주간 요약")])
    analysis = Model([AIMessage(content="최근 기록 분석 완료")])
    evidence = Model([call("search_evidence", {"query": "감량 전략 근거"}),
                      AIMessage(content="공식 근거 확인 완료")])
    models = iter([root, analysis, evidence])

    async def fake_mcp(name, arguments):
        return {"grounded": True, "evidence": [{"source": "KDRI", "page": "10", "excerpt": "근거"}]}

    monkeypatch.setattr("app.agents.weekly_deep.call_readonly_tool", fake_mcp)
    team = WeeklyDeepTeam({"user_id": "u1", "run_id": "r1", "thread_id": "t1",
                           "message": "주간 분석", "execution_usage": {}},
                          db=fake_sb, repository=AsyncMock(), model_factory=lambda: next(models))
    result = await team.execute()
    assert result["execution_status"] == "completed"
    assert team.delegations == {"weekly_analysis": 1, "weekly_evidence": 1}
    assert result["awaiting_confirmation"] is False


@pytest.mark.asyncio
async def test_weekly_budget_storage_failure_is_fail_closed(monkeypatch):
    from app.agents.weekly_deep import weekly_deep_node

    class BrokenBudget:
        def __init__(self, *args, **kwargs):
            pass
        async def update(self, **kwargs):
            raise ConnectionError("db unavailable")

    monkeypatch.setattr("app.db.execution_budget.DurableBudget", BrokenBudget)
    result = await weekly_deep_node({"user_id": "u1", "run_id": "r1", "message": "주간 분석"})
    assert result["execution_status"] == "blocked"
    assert result["agent_events"][0]["reason"] == "budget_storage_unavailable"


def test_weekly_request_accepts_goal_progress_read_tool():
    from app.api.routes.main import ChatRequest

    request = ChatRequest(message="주간 분석", requested_action="weekly_review",
                          tool_policy=["assess_goal_progress"])
    assert request.tool_policy == ["assess_goal_progress"]


@pytest.mark.asyncio
async def test_weekly_partial_records_are_disclosed_without_strategy_write(fake_sb):
    """Missing logs must remain unknown rather than becoming zero intake."""
    from app.agents.weekly_deep import WeeklyDeepTeam

    fake_sb.tables["meal_logs"] = []
    root = ScriptedModel([
        tool_call("delegate_weekly_analysis", {"query": "최근 7일 기록 완전성 확인"}),
        AIMessage(content="기록이 일부 없어 섭취량 추세를 확정할 수 없습니다."),
    ])
    child = ScriptedModel([
        tool_call("read_recent_intake", {}),
        AIMessage(content="기록 완전성은 unknown이며 미기록을 미섭취로 해석하지 않습니다."),
    ])
    models = iter([root, child])
    repository = AsyncMock()
    team = WeeklyDeepTeam(
        {"user_id": "u1", "run_id": "r1", "thread_id": "t1",
         "message": "지난주 분석", "execution_usage": {}},
        db=fake_sb, repository=repository, model_factory=lambda: next(models),
    )

    result = await team.execute()

    assert result["execution_status"] == "completed"
    assert "미기록" in result["response"] or "기록이 일부" in result["response"]
    assert result["awaiting_confirmation"] is False
    repository.create.assert_not_called()


@pytest.mark.asyncio
async def test_weekly_mcp_outage_is_reported_and_does_not_create_proposal(monkeypatch, fake_sb):
    from app.agents.weekly_deep import WeeklyDeepTeam

    async def unavailable(name, arguments):
        raise ConnectionError("simulated MCP outage")

    monkeypatch.setattr("app.agents.weekly_deep.call_readonly_tool", unavailable)
    root = ScriptedModel([
        tool_call("delegate_weekly_evidence", {"query": "감량 전략 근거"}),
        AIMessage(content="근거 서비스 장애로 전략 변경을 보류합니다."),
    ])
    child = ScriptedModel([
        tool_call("search_evidence", {"query": "감량 전략 근거"}),
        AIMessage(content="근거 도구를 사용할 수 없어 수치 조정을 보류합니다."),
    ])
    models = iter([root, child])
    repository = AsyncMock()
    team = WeeklyDeepTeam(
        {"user_id": "u1", "run_id": "r1", "thread_id": "t1",
         "message": "지난주 분석", "execution_usage": {}},
        db=fake_sb, repository=repository, model_factory=lambda: next(models),
    )

    result = await team.execute()

    assert result["execution_status"] == "completed"
    assert "보류" in result["response"]
    assert any(event["type"] == "tool_failed" for event in result["agent_events"])
    repository.create.assert_not_called()


@pytest.mark.asyncio
async def test_weekly_budget_exhaustion_blocks_without_write(monkeypatch, fake_sb):
    from app.agents.weekly_deep import WeeklyDeepTeam

    settings = SimpleNamespace(
        deep_agent_max_model_calls=1, deep_agent_max_tool_calls=30,
        deep_agent_timeout_seconds=180,
        agent_max_validation_attempts=3, agent_max_replans=2,
    )
    monkeypatch.setattr("app.agents.weekly_deep.get_settings", lambda: settings)
    root = ScriptedModel([
        tool_call("delegate_weekly_analysis", {"query": "최근 기록 분석"}),
    ])
    repository = AsyncMock()
    team = WeeklyDeepTeam(
        {"user_id": "u1", "run_id": "r1", "thread_id": "t1",
         "message": "지난주 분석", "execution_usage": {}},
        db=fake_sb, repository=repository, model_factory=lambda: root,
    )

    result = await team.execute()

    assert result["execution_status"] == "blocked"
    assert result["execution_usage"]["model_calls"] == 1
    repository.create.assert_not_called()


@pytest.mark.asyncio
async def test_weekly_conflicting_policy_blocks_strategy_before_human_gate(monkeypatch, fake_sb):
    from app.agents.runtime import ToolFeedback
    from app.agents.team import StrategyDraft
    from app.agents.weekly_deep import WeeklyDeepTeam

    team = WeeklyDeepTeam(
        {"user_id": "u1", "run_id": "r1", "thread_id": "t1",
         "message": "지난주 분석", "execution_usage": {}},
        db=fake_sb, repository=AsyncMock(), model_factory=lambda: None,
    )
    team.profile = {"region": "KR", "strategy": None}
    team.evidence["e1"] = {
        "source": "official-a", "page": "10", "excerpt": "상충하는 수치 A"
    }
    monkeypatch.setattr("app.rag.strategy_evidence.evaluate_strategy",
                        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("unresolved conflict")))
    draft = StrategyDraft(
        daily_calories=1800, protein_g=100, carbs_g=225, fat_g=55,
        strategy_note="충돌 검토", evidence_ids=["e1"],
    )

    with pytest.raises(ToolFeedback) as exc:
        await team.propose_strategy(draft)

    assert exc.value.feedback["error"] == "evidence_policy_blocked"
    assert team.proposal is None
    team.repository.create.assert_not_called()
