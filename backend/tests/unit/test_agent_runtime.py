from unittest.mock import AsyncMock
from langchain_core.messages import AIMessage
from pydantic import BaseModel, ConfigDict
from app.agents.runtime import AgentTool, ExecutionBudget, run_agent


class Query(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str


class ScriptedModel:
    def __init__(self, responses):
        self.ainvoke = AsyncMock(side_effect=responses)
    def bind_tools(self, schemas):
        self.schemas = schemas
        return self


def call(name="lookup", args=None):
    return AIMessage(content="", tool_calls=[{"id": "call1", "name": name,
                     "args": args or {"query": "food"}, "type": "tool_call"}])


async def test_model_receives_tool_result_and_decides_to_finish():
    execute = AsyncMock(return_value={"calories": 100})
    model = ScriptedModel([call(), AIMessage(content="done")])
    budget = ExecutionBudget()
    result = await run_agent(model=model, instruction="help", request="food",
        tools=[AgentTool("lookup", "lookup food", Query, execute)], budget=budget)
    assert result.status == "completed"
    assert budget.model_calls == 2 and budget.tool_calls == 1
    assert '"calories": 100' in model.ainvoke.call_args.args[0][-2].content


async def test_policy_cannot_be_overridden_by_model_and_feedback_is_returned():
    execute = AsyncMock()
    model = ScriptedModel([call(), AIMessage(content="cannot search")])
    result = await run_agent(model=model, instruction="help", request="no search",
        tools=[AgentTool("lookup", "lookup", Query, execute)], budget=ExecutionBudget(), allowed_tools=set())
    execute.assert_not_called()
    assert result.status == "completed"
    assert "tool_not_allowed" in model.ainvoke.call_args.args[0][-2].content


async def test_same_error_twice_stops_and_never_leaks_exception():
    execute = AsyncMock(side_effect=ConnectionError("secret-token"))
    model = ScriptedModel([call(), call()])
    result = await run_agent(model=model, instruction="help", request="food",
        tools=[AgentTool("lookup", "lookup", Query, execute)], budget=ExecutionBudget())
    assert result.reason == "repeated_tool_failure"
    assert "secret-token" not in str(model.ainvoke.call_args_list)


async def test_shared_budget_counts_delegated_model_calls():
    budget = ExecutionBudget(max_model_calls=1)
    child = ScriptedModel([AIMessage(content="child")])
    async def delegate(args):
        return (await run_agent(model=child, instruction="child", request=args.query,
                               tools=[], budget=budget)).status
    parent = ScriptedModel([call("delegate")])
    result = await run_agent(model=parent, instruction="parent", request="food",
        tools=[AgentTool("delegate", "delegate", Query, delegate, "delegate")], budget=budget)
    assert result.reason == "model_call_limit"
    child.ainvoke.assert_not_called()


async def test_untrusted_identity_is_rejected_by_schema():
    execute = AsyncMock()
    model = ScriptedModel([call(args={"query": "food", "user_id": "other"}), AIMessage(content="correct")])
    result = await run_agent(model=model, instruction="help", request="food",
        tools=[AgentTool("lookup", "lookup", Query, execute)], budget=ExecutionBudget())
    execute.assert_not_called()
    assert result.status == "completed"


async def test_malformed_tool_call_is_not_a_successful_final_answer():
    model = ScriptedModel([AIMessage(content="", invalid_tool_calls=[
        {"name": "lookup", "args": "not-json", "id": "bad", "error": "parse error", "type": "invalid_tool_call"}])])
    result = await run_agent(model=model, instruction="help", request="food", tools=[], budget=ExecutionBudget())
    assert result.status == "blocked"
    assert result.reason == "invalid_tool_call"


async def test_successful_delegate_can_return_child_response_without_parent_synthesis():
    execute = AsyncMock(return_value={"agent": "meal", "response": "검증된 결과", "proposal_prepared": False})
    model = ScriptedModel([call("delegate")])
    budget = ExecutionBudget()

    result = await run_agent(
        model=model, instruction="parent", request="meal", budget=budget,
        tools=[AgentTool("delegate", "delegate", Query, execute, "delegate")],
        finish_after_successful_delegate=True,
    )

    assert result.status == "completed"
    assert result.content == "검증된 결과"
    assert budget.model_calls == 1
    assert model.ainvoke.await_count == 1


async def test_identical_successful_read_is_replayed_without_second_tool_charge():
    execute = AsyncMock(return_value={"calories": 100})
    model = ScriptedModel([call(), call(), AIMessage(content="done")])
    budget = ExecutionBudget()

    result = await run_agent(
        model=model, instruction="help", request="food", budget=budget,
        tools=[AgentTool("lookup", "lookup food", Query, execute, "read")],
    )

    assert result.status == "completed"
    assert execute.await_count == 1
    assert budget.tool_calls == 1
    assert any(event["type"] == "tool_cache_hit" for event in result.events)
