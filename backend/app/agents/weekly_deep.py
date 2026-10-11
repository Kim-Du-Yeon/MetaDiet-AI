"""Bounded weekly deep analysis with two specialist delegates and HITL writes."""
import asyncio
import hashlib
import json
import re
import time
from uuid import uuid4

from app.agents.runtime import AgentTool, ExecutionBudget, ExecutionStopped, run_agent
from app.agents.team import BASE_INSTRUCTION, DietTeam, Empty, Query, StrategyDraft
from app.core.config import get_settings
from app.db.proposals import ProposalRepository
from app.mcp.server import call_readonly_tool


WEEKLY_INSTRUCTION = BASE_INSTRUCTION + """
주간 분석에서는 기록 완전성을 먼저 밝히고, 미기록을 미섭취로 단정하지 마세요.
분석 Agent와 근거 Agent를 각각 필요한 경우 한 번씩 사용하세요.
전략 변경은 충분한 개인 기록과 공식 근거가 있을 때만 propose_strategy로 제안하세요.
propose_strategy 결과는 사용자 확인 전에는 적용되지 않습니다.
"""


class WeeklyDeepTeam(DietTeam):
    def __init__(self, state, **kwargs):
        super().__init__(state, **kwargs)
        settings = get_settings()
        usage = self.state.get("execution_usage") or {}
        self.budget = ExecutionBudget(
            max_model_calls=settings.deep_agent_max_model_calls,
            max_tool_calls=settings.deep_agent_max_tool_calls,
            timeout_seconds=max(0, settings.deep_agent_timeout_seconds - usage.get("elapsed_seconds", 0)),
            model_calls=usage.get("model_calls", 0), tool_calls=usage.get("tool_calls", 0))
        self.previous_elapsed = usage.get("elapsed_seconds", 0)

    async def search_evidence_mcp(self, args):
        # The retriever translates Korean with Gemini inside the MCP tool.
        # Reserve that nested model call in the shared deep-run budget.
        if re.search(r"[가-힣]", args.query):
            await self.budget.reserve("model")
        result = await call_readonly_tool("search_evidence", {"query": args.query, "k": 4})
        for item in result.get("evidence", []):
            evidence_id = item.get("evidence_id") or hashlib.sha256(
                json.dumps(item, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
            self.evidence[evidence_id] = item
            item["evidence_id"] = evidence_id
        return result

    def analysis_tools(self):
        allowed = {"read_profile", "read_intake", "read_recent_intake", "read_measurements", "assess_goal_progress"}
        return [tool for tool in self.tools("goal") if tool.name in allowed]

    async def _delegate(self, role: str, query: str):
        if self.delegations.get(role, 0):
            raise ExecutionStopped("weekly_delegate_limit")
        if self.budget.persist:
            await self.budget.persist(f"delegate:{role}")
        self.delegations[role] = 1
        tools = self.analysis_tools() if role == "weekly_analysis" else [
            AgentTool("search_evidence", "공식 문서 근거를 MCP로 검색", Query, self.search_evidence_mcp)]
        result = await run_agent(model=self.model_factory(), instruction=WEEKLY_INSTRUCTION + f"\n담당: {role}",
            request=json.dumps({"task": query, "original_request": self.state["message"]}, ensure_ascii=False),
            tools=tools, allowed_tools=self.allowed, budget=self.budget, config=self.config, agent_name=role)
        self.events.extend({**event, "agent": role} for event in result.events)
        if result.status == "blocked":
            raise ExecutionStopped(result.reason or "weekly_specialist_blocked")
        return {"agent": role, "response": result.content}

    def supervisor_tools(self):
        async def analysis(args):
            return await self._delegate("weekly_analysis", args.query)

        async def evidence(args):
            return await self._delegate("weekly_evidence", args.query)

        return [
            AgentTool("delegate_weekly_analysis", "최근 7일 기록·측정·목표 추세 분석을 위임", Query, analysis, "delegate"),
            AgentTool("delegate_weekly_evidence", "전략 판단에 필요한 공식 근거 검색을 위임", Query, evidence, "delegate"),
            AgentTool("propose_strategy", "근거가 충분할 때 새 전략을 사용자 확인 대상으로 제안", StrategyDraft, self.propose_strategy, "proposal"),
        ]

    def supervisor_allowed_tools(self):
        if self.allowed is None:
            return None
        allowed = set()
        if self.allowed & {"read_profile", "read_intake", "read_recent_intake",
                           "read_measurements", "assess_goal_progress"}:
            allowed.add("delegate_weekly_analysis")
        if "search_evidence" in self.allowed:
            allowed.add("delegate_weekly_evidence")
        if "propose_strategy" in self.allowed:
            allowed.add("propose_strategy")
        return allowed

    async def execute(self):
        result = await run_agent(model=self.model_factory(), instruction=WEEKLY_INSTRUCTION +
            "\n당신은 Weekly Supervisor입니다. 두 전문 Agent 결과를 종합해 실행 가능한 주간 리포트를 작성하세요.",
            request=json.dumps({"message": self.state["message"]}, ensure_ascii=False),
            tools=self.supervisor_tools(), allowed_tools=self.supervisor_allowed_tools(),
            budget=self.budget, config=self.config, agent_name="weekly_supervisor")
        self.events.extend({**event, "agent": "weekly_supervisor"} for event in result.events)
        proposal = self.state.get("pending_proposal")
        if result.status == "completed" and self.proposal:
            digest = hashlib.sha256(json.dumps(self.proposal, sort_keys=True).encode()).hexdigest()
            try:
                proposal = await asyncio.wait_for(self.repository.create(
                    self.state["user_id"], self.state.get("thread_id", "default"), self.proposal,
                    f"{self.state.get('run_id', str(uuid4()))}:{digest}"), self.budget.remaining())
            except (TimeoutError, ExecutionStopped):
                result.status = "blocked"
                result.content = "실행 시간이 초과되어 주간 전략 제안을 보류했습니다."
                self.proposal = None
        return {"response": result.content, "agent_used": "weekly_supervisor",
                "pending_proposal": proposal, "pending_meals": None,
                "awaiting_confirmation": bool(proposal), "agent_events": self.events,
                "execution_usage": {"model_calls": self.budget.model_calls,
                    "tool_calls": self.budget.tool_calls,
                    "elapsed_seconds": self.previous_elapsed + time.monotonic() - self.budget.started,
                    "validation_attempts": self.validation_attempts, "replans": self.replans},
                "execution_status": result.status}


async def weekly_deep_node(state, config=None):
    from app.db.execution_budget import DurableBudget

    settings = get_settings()
    durable = DurableBudget(state["user_id"], state["run_id"], {
        "model_calls": settings.deep_agent_max_model_calls,
        "tool_calls": settings.deep_agent_max_tool_calls,
        "validation_attempts": settings.agent_max_validation_attempts,
        "replans": settings.agent_max_replans,
        "elapsed_seconds": settings.deep_agent_timeout_seconds,
    })
    result = None
    try:
        try:
            usage = await durable.update(seed=state.get("execution_usage") or {})
        except ExecutionStopped:
            raise
        except Exception:
            raise ExecutionStopped("budget_storage_unavailable") from None
        team = WeeklyDeepTeam({**state, "execution_usage": usage}, config=config)
        team.budget.persist = durable.reserve
        result = await team.execute()
    except ExecutionStopped as exc:
        result = {"response": "주간 분석 실행 한도 또는 도구 오류로 변경 제안을 보류했습니다.",
                  "execution_status": "blocked",
                  "agent_events": [{"type": "execution_blocked", "reason": str(exc)}]}
    finally:
        try:
            usage = await durable.update(finish=True)
            if result is not None:
                result["execution_usage"] = usage
        except Exception:
            if result is not None:
                result["execution_status"] = "blocked"
                result["response"] = "실행 상태 저장을 확인할 수 없어 주간 분석을 중지했습니다."
    return result
