from unittest.mock import AsyncMock
from langchain_core.messages import AIMessage
from pydantic import BaseModel
from app.agents.runtime import AgentTool, ExecutionBudget, run_agent
from app.core.jev import Decision


class Args(BaseModel):
    query: str


class Model:
    def __init__(self, messages):
        self.ainvoke = AsyncMock(side_effect=messages)
    def bind_tools(self, tools):
        self.tools = tools
        return self


async def test_selector_receives_only_user_allowed_tools():
    selector = AsyncMock(return_value=Decision(("read", "finish"), choice="read"))
    model = Model([AIMessage(content="Need clarification")])
    result = await run_agent(model=model, instruction="", request="no search", tools=[
        AgentTool("read", "read profile", Args, AsyncMock()), AgentTool("search", "search", Args, AsyncMock())],
        allowed_tools={"read"}, budget=ExecutionBudget(), decision_selector=selector, selection_mode="enforce")
    assert set(selector.call_args.kwargs["candidates"]) == {"read", "finish"}
    assert result.status == "completed"


async def test_gemini_cannot_execute_a_tool_removed_by_jev_selection():
    execute = AsyncMock()
    selector = AsyncMock(side_effect=[Decision(("read", "finish"), choice="finish"),
                                      Decision(("read", "finish"), fallback_reason="low_confidence")])
    model = Model([AIMessage(content="", tool_calls=[{"name": "read", "args": {"query": "x"}, "id": "1", "type": "tool_call"}]),
                   AIMessage(content="ask user")])
    result = await run_agent(model=model, instruction="", request="x", tools=[AgentTool("read", "read", Args, execute)],
        budget=ExecutionBudget(), decision_selector=selector, selection_mode="enforce")
    execute.assert_not_called()
    assert result.status == "completed"


async def test_shadow_keeps_all_allowed_tools_and_first_only_is_single_call():
    selector = AsyncMock(return_value=Decision(("read", "finish"), choice="finish"))
    execute = AsyncMock(return_value={"ok": True})
    model = Model([AIMessage(content="", tool_calls=[{"name": "read", "args": {"query": "x"}, "id": "1", "type": "tool_call"}]),
                   AIMessage(content="done")])
    result = await run_agent(model=model, instruction="", request="x", tools=[AgentTool("read", "read", Args, execute)],
        budget=ExecutionBudget(), decision_selector=selector, select_first_only=True)
    execute.assert_awaited_once()
    selector.assert_awaited_once()
    assert result.status == "completed"


async def test_first_only_enforce_restores_other_tools_after_first_result():
    selector = AsyncMock(return_value=Decision(("read", "other", "finish"), choice="read"))
    model = Model([AIMessage(content="", tool_calls=[{"name": "read", "args": {"query": "x"}, "id": "1", "type": "tool_call"}]),
                   AIMessage(content="done")])
    await run_agent(model=model, instruction="", request="x", tools=[
        AgentTool("read", "read", Args, AsyncMock(return_value={})), AgentTool("other", "other", Args, AsyncMock(return_value={}))],
        budget=ExecutionBudget(), decision_selector=selector, select_first_only=True, selection_mode="enforce")
    assert {tool["function"]["name"] for tool in model.tools} == {"read", "other"}
