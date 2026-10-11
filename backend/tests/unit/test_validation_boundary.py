from app.agents.validator.node import route_after_validator, validator_node


def test_exhausted_validation_never_reaches_confirmation():
    assert route_after_validator({"validation_passed": False, "can_improve": False}) == "blocked"


def test_missing_validation_cannot_pass():
    assert route_after_validator({}) == "blocked"


async def test_missing_meals_are_blocked():
    result = await validator_node({"pending_meals": []})
    assert result["validation_passed"] is False
    assert result["awaiting_confirmation"] is False


async def test_exhausted_validation_clears_unapproved_proposal():
    result = await validator_node({"pending_meals": [{"food_name": "test"}],
                                   "validation_attempts": 3})
    assert result["validation_passed"] is False
    assert result["pending_meals"] is None
    assert result["can_improve"] is False


async def test_parent_graph_does_not_interrupt_at_confirm_after_validation_failure(monkeypatch):
    from langgraph.checkpoint.memory import MemorySaver
    import app.agents.graph as graph_module

    async def no_op(state):
        return {}

    async def route_plan(state):
        return {"intent": "meal_plan"}

    async def propose(state):
        return {"pending_meals": [{"food_name": "test"}], "awaiting_confirmation": True}

    async def reject(state):
        from app.agents.validator.node import blocked_proposal
        return blocked_proposal(3, "test rejection")

    monkeypatch.setattr(graph_module, "load_state_node", no_op)
    monkeypatch.setattr(graph_module, "supervisor_node", route_plan)
    monkeypatch.setattr(graph_module, "meal_plan_node", propose)
    monkeypatch.setattr(graph_module, "validator_node", reject)
    monkeypatch.setattr(graph_module, "save_chat_node", no_op)
    graph = graph_module.build_graph(MemorySaver(), model_driven=False)
    config = {"configurable": {"thread_id": "reject-test"}}
    result = await graph.ainvoke({"user_id": "test", "message": "plan"}, config)
    snapshot = await graph.aget_state(config)
    assert snapshot.next == ()
    assert result["pending_meals"] is None
    assert result["awaiting_confirmation"] is False
