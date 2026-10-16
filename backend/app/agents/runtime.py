"""Bounded model-driven tool loop shared by supervisors and specialist agents.

Tools receive authenticated context via closures, never model-supplied user IDs.
Only reads and proposal creation belong here; approved writes use application APIs.
"""
import asyncio
import json
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Literal

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.utils.function_calling import convert_to_openai_function
from pydantic import BaseModel, ValidationError


class ExecutionStopped(RuntimeError):
    """A deterministic execution boundary was reached."""


class ToolFeedback(ValueError):
    def __init__(self, error: str, correction: str, *, retryable: bool):
        self.feedback = {"ok": False, "error": error, "correction": correction, "retryable": retryable}


@dataclass
class ExecutionBudget:
    max_model_calls: int = 12
    max_tool_calls: int = 20
    timeout_seconds: float = 120
    model_calls: int = 0
    tool_calls: int = 0
    started: float = field(default_factory=time.monotonic)
    failures: Counter = field(default_factory=Counter)
    persist: Callable[[str], Awaitable[None]] | None = None

    async def reserve(self, kind: Literal["model", "tool"]) -> None:
        self.remaining()
        attr, limit = ("model_calls", self.max_model_calls) if kind == "model" else ("tool_calls", self.max_tool_calls)
        if getattr(self, attr) >= limit:
            raise ExecutionStopped(f"{kind}_call_limit")
        if self.persist:
            try:
                await self.persist(kind)
            except ExecutionStopped:
                raise
            except Exception:
                raise ExecutionStopped("budget_storage_unavailable") from None
        self.charge(kind)

    def remaining(self) -> float:
        remaining = self.timeout_seconds - (time.monotonic() - self.started)
        if remaining <= 0:
            raise ExecutionStopped("execution_timeout")
        return remaining

    def charge(self, kind: Literal["model", "tool"]) -> None:
        self.remaining()
        attr, limit = ("model_calls", self.max_model_calls) if kind == "model" else ("tool_calls", self.max_tool_calls)
        if getattr(self, attr) >= limit:
            raise ExecutionStopped(f"{kind}_call_limit")
        setattr(self, attr, getattr(self, attr) + 1)


@dataclass(frozen=True)
class AgentTool:
    name: str
    description: str
    arguments: type[BaseModel]
    execute: Callable[[BaseModel], Awaitable[Any]]
    effect: Literal["read", "proposal", "delegate"] = "read"

    def schema(self) -> dict:
        function = convert_to_openai_function(self.arguments)
        return {"type": "function", "function": {"name": self.name,
                "description": self.description, "parameters": function["parameters"]}}


@dataclass
class AgentResult:
    status: Literal["completed", "blocked"]
    content: str
    events: list[dict]
    reason: str | None = None


async def run_agent(*, model, instruction: str, request: str,
                    tools: list[AgentTool], budget: ExecutionBudget,
                    allowed_tools: set[str] | None = None,
                    config: dict | None = None, decision_selector=None,
                    selection_mode: Literal["shadow", "enforce"] = "shadow",
                    select_first_only: bool = False,
                    finish_after_successful_delegate: bool = False,
                    agent_name: str = "specialist", context_verified: bool = False,
                    buffered_stream: bool = False) -> AgentResult:
    """Model selects zero or more tools repeatedly until done or budget exhausted.

    A delegated agent must receive the *same* budget. Policies can only remove
    tools. Raw exception messages are intentionally excluded from model feedback.
    """
    available = {tool.name: tool for tool in tools
                 if allowed_tools is None or tool.name in allowed_tools}
    if len({tool.name for tool in tools}) != len(tools):
        raise ValueError("Duplicate tool names")
    from app.agents.execution_stream import emit_runtime_event, measure_stage
    from app.core.llm import ConfiguredChatModel
    await emit_runtime_event('model_preparing', agent=agent_name)
    async with measure_stage('sdk_prepare_' + agent_name):
        if isinstance(model, ConfiguredChatModel):
            model.prepare()
            await emit_runtime_event('sdk_provider_ready', reused=model.provider_reused)
    async with measure_stage('tool_bind_' + agent_name):
        bound = model.bind_tools([tool.schema() for tool in available.values()]) if available else model
    messages = [SystemMessage(content=instruction), HumanMessage(content=request)]
    events = []
    read_cache: dict[tuple[str, str], dict] = {}
    selection_attempts = 0
    try:
        while True:
            turn_tools = available
            if decision_selector and (not select_first_only or selection_attempts == 0):
                selection_attempts += 1
                candidates = {name: tool.description for name, tool in available.items()}
                candidates["finish"] = "No further tool is needed; answer or ask for missing information"
                decision = await decision_selector(state={"original_request": request,
                    "recent_results": [{"type": message.type, "content": str(message.content)[:4000]}
                                       for message in messages[2:][-4:]]}, candidates=candidates, budget=budget)
                events.append(decision.event())
                if selection_mode == "enforce" and decision.choice in candidates:
                    turn_tools = {} if decision.choice == "finish" else {decision.choice: available[decision.choice]}
            if decision_selector:
                async with measure_stage('tool_bind_' + agent_name):
                    bound = model.bind_tools([tool.schema() for tool in turn_tools.values()]) if turn_tools else model
            async with measure_stage('model_budget_' + agent_name):
                await budget.reserve("model")
            from app.agents.execution_stream import emit_runtime_event, measure_stage
            await emit_runtime_event("model_started", agent=agent_name, context_verified=context_verified)
            async with measure_stage('model_' + agent_name):
                from app.agents.model_delivery import invoke_model
                from app.core.external_retry import retry_external
                response = await asyncio.wait_for(retry_external(
                    lambda: invoke_model(bound, messages, config, buffered_stream=buffered_stream),
                    operation='model', before_retry=lambda: budget.reserve('model')), budget.remaining())
            messages.append(response)
            if getattr(response, "invalid_tool_calls", []):
                raise ExecutionStopped("invalid_tool_call")
            calls = getattr(response, "tool_calls", [])
            if not calls:
                from app.core.llm import response_text
                content = response_text(response)
                if not content.strip():
                    raise ExecutionStopped("empty_model_response")
                return AgentResult("completed", content, events)
            for call in calls:
                name, args = call["name"], call["args"]
                action = (name, json.dumps(args, sort_keys=True, ensure_ascii=False))
                events.append({"type": "tool_requested", "tool": name})
                await emit_runtime_event("tool_started", agent=agent_name, tool=name)
                tool = turn_tools.get(name)
                if tool is not None and tool.effect == "read" and action in read_cache:
                    feedback = read_cache[action]
                    events.append({"type": "tool_cache_hit", "tool": name})
                else:
                    await budget.reserve("tool")
                    if tool is None:
                        feedback = {"ok": False, "error": "tool_not_allowed", "retryable": False}
                    else:
                        try:
                            validated = tool.arguments.model_validate(args, strict=True)
                            data = await asyncio.wait_for(tool.execute(validated), budget.remaining())
                            feedback = {"ok": True, "data": data}
                            if tool.effect == "read":
                                read_cache[action] = feedback
                        except ExecutionStopped:
                            raise
                        except ToolFeedback as exc:
                            feedback = exc.feedback
                        except ValidationError as exc:
                            feedback = {"ok": False, "error": "invalid_arguments", "retryable": False,
                                        "correction": "Use the tool schema; do not change user identity or permissions.",
                                        "fields": [{"field": ".".join(map(str, e["loc"])), "issue": e["type"]} for e in exc.errors(include_input=False, include_url=False)]}
                        except (TimeoutError, ConnectionError):
                            feedback = {"ok": False, "error": "tool_unavailable", "retryable": True}
                        except Exception:
                            feedback = {"ok": False, "error": "tool_execution_failed", "retryable": False}
                if feedback["ok"]:
                    for key in list(budget.failures):
                        if key[:2] == action:
                            del budget.failures[key]
                else:
                    key = (*action, feedback["error"])
                    budget.failures[key] += 1
                    if budget.failures[key] >= 2:
                        events.append({"type": "tool_failed", "tool": name, "error": feedback["error"]})
                        raise ExecutionStopped("food_not_found" if feedback["error"] == "food_not_found" else "repeated_tool_failure")
                events.append({"type": "tool_succeeded" if feedback["ok"] else "tool_failed", "tool": name})
                await emit_runtime_event("tool_finished", agent=agent_name, tool=name, ok=feedback["ok"])
                messages.append(ToolMessage(content=json.dumps(feedback, ensure_ascii=False), tool_call_id=call["id"]))
                if (finish_after_successful_delegate and feedback["ok"] and tool is not None
                        and tool.effect == "delegate" and isinstance(feedback.get("data"), dict)):
                    delegated_response = feedback["data"].get("response")
                    if isinstance(delegated_response, str) and delegated_response.strip():
                        return AgentResult("completed", delegated_response, events)
    except (ExecutionStopped, TimeoutError) as exc:
        reason = str(exc) if isinstance(exc, ExecutionStopped) else "execution_timeout"
        events.append({"type": "execution_blocked", "reason": reason})
        content = ("식품성분표에서 일치하는 제품을 찾지 못했습니다. 제품별 수치가 필요한 음식은 "
                   "포장지의 1회 제공량과 영양정보를 알려주세요. 확인되지 않은 수치로 기록하지 않았습니다."
                   if reason == "food_not_found" else "실행 한도 또는 도구 오류로 제안을 보류했습니다.")
        return AgentResult("blocked", content, events, reason)
