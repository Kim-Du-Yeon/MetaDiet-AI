from unittest.mock import AsyncMock
from langgraph.checkpoint.memory import MemorySaver
from app.agents.graph import build_graph


async def test_intake_approval_summary_uses_resolved_meals(monkeypatch):
    import app.agents.approval as approval
    proposal = {'id': 'p1', 'version': 1, 'kind': 'intake'}
    repo = AsyncMock()
    repo.resolve.return_value = {**proposal, 'status': 'confirmed', 'payload': {
        'log_date': '2026-10-16', 'meals': [{'food_name': '제육볶음', 'quantity_g': 300,
            'calories': 600, 'meal_type': 'breakfast'}]}}
    monkeypatch.setattr(approval, 'ProposalRepository', lambda: repo)
    state = {'user_id': 'u1', 'pending_proposal': proposal, 'message': '확정'}
    result = await approval.approval_node(state)
    assert '2026-10-16 · 아침' in result['response']
    assert '제육볶음 · 300g · 600 kcal' in result['response']
    assert '합계 600 kcal' in result['response']
    repo.resolve.return_value = {**proposal, 'status': 'cancelled'}
    cancelled = await approval.approval_node({**state, 'message': '취소'})
    assert '제육볶음' not in cancelled['response']
    assert '저장했습니다' not in cancelled['response']


async def test_production_graph_pauses_before_approval_and_resumes_without_llm(monkeypatch):
    import app.agents.team as team
    import app.agents.approval as approval
    import app.agents.graph as graph_module
    proposal = {"id": "p1", "version": 1, "kind": "plan", "payload": {"meals": []}, "status": "pending"}
    async def prepare(state, config=None):
        return {"pending_proposal": proposal, "awaiting_confirmation": True, "response": "review"}
    saved_turns = []
    async def no_op(state):
        saved_turns.append((state["message"], state["response"]))
        return {}
    monkeypatch.setattr(team, "team_node", prepare)
    monkeypatch.setattr(graph_module, "save_chat_node", no_op)
    repository = AsyncMock()
    repository.resolve.return_value = {**proposal, "status": "confirmed"}
    monkeypatch.setattr(approval, "ProposalRepository", lambda: repository)
    graph = build_graph(MemorySaver())
    config = {"configurable": {"thread_id": "u1-t1"}}
    await graph.ainvoke({"user_id": "u1", "message": "plan"}, config)
    assert (await graph.aget_state(config)).next == ("confirm",)
    assert saved_turns == [("plan", "review")]
    repository.resolve.assert_not_called()
    await graph.aupdate_state(config, {"message": "확정", "proposal_decision": {"proposal_id": "p1", "version": 1, "action": "confirm"}})
    result = await graph.ainvoke(None, config)
    repository.resolve.assert_awaited_once_with("u1", "p1", 1, "confirm")
    assert result["pending_proposal"] is None
    assert saved_turns[-1][0] == "확정"
    assert not (await graph.aget_state(config)).next


async def test_stale_button_never_resolves_proposal(monkeypatch):
    import app.agents.approval as approval
    repo = AsyncMock()
    monkeypatch.setattr(approval, "ProposalRepository", lambda: repo)
    result = await approval.approval_node({"user_id": "u1", "pending_proposal": {"id": "p2", "version": 2},
        "proposal_decision": {"proposal_id": "p1", "version": 1, "action": "confirm"}})
    assert "변경" in result["response"]
    repo.resolve.assert_not_called()


async def test_public_stats_reads_confirmed_data_and_does_not_invent_target(fake_sb):
    from app.api.routes import main
    fake_sb.tables["meal_logs"] = [{"calories": 300}, {"calories": 450}]
    fake_sb.tables["diet_strategies"] = [{"daily_calories": 1800}]
    assert await main._public_stats("u1") == {"today_calories": 750, "target_calories": 1800}
    fake_sb.tables["diet_strategies"] = []
    assert await main._public_stats("u1") == {}


async def test_rollback_discards_resolved_proposal_and_preserves_budget(monkeypatch):
    from types import SimpleNamespace
    from contextlib import asynccontextmanager
    from app.api.routes import main
    proposal = {"id": "p1"}
    old = SimpleNamespace(values={"pending_proposal": proposal, "pending_meals": [{}],
        "execution_usage": {"model_calls": 2}}, metadata={"step": 1})
    current = SimpleNamespace(values={"execution_usage": {"model_calls": 8}}, metadata={})
    graph = AsyncMock()
    graph.aget_state.side_effect = [old, current, current]
    monkeypatch.setattr(main, "get_graph", lambda: graph)
    repository = AsyncMock()
    repository.get.return_value = {"status": "confirmed"}
    monkeypatch.setattr(main, "ProposalRepository", lambda: repository)
    locks = []
    @asynccontextmanager
    async def lock(user, thread):
        locks.append((user, thread))
        yield
    monkeypatch.setattr(main, "conversation_lock", lock)
    await main.rollback_to_checkpoint("t1", "c1", "u1")
    restored = graph.aupdate_state.call_args.args[1]
    assert restored["pending_proposal"] is None
    assert restored["execution_usage"]["model_calls"] == 8
    assert locks == [("u1", "t1")]


async def test_session_restore_reads_state_stats_and_messages_without_running_graph(monkeypatch, fake_sb):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    import app.api.routes.main as main

    fake_sb.tables["meal_logs"] = [{"calories": 244.2}]
    fake_sb.tables["diet_strategies"] = [{"daily_calories": 1800}]
    fake_sb.tables["chat_history"] = [
        {"role": "assistant", "content": "답변", "agent_type": "meal", "created_at": "2026-10-11T01:01:00Z"},
        {"role": "user", "content": "저녁 추천", "agent_type": None, "created_at": "2026-10-11T01:00:00Z"},
    ]
    graph = SimpleNamespace(aget_state=AsyncMock(return_value=SimpleNamespace(values={
        "pending_proposal": {"id": "p1"}, "pending_meals": [{"food_name": "밥"}],
        "awaiting_confirmation": True, "plan_date": "2026-10-11", "agent_used": "meal",
    }, next=("confirm",))))
    monkeypatch.setattr(main, "get_graph", lambda: graph)
    repository = AsyncMock()
    repository.get.return_value = {"id": "p1", "version": 2, "status": "pending", "kind": "plan",
                                   "payload": {"kind": "plan", "meals": []}}
    monkeypatch.setattr(main, "ProposalRepository", lambda: repository)

    restored = await main.restore_session("thread", "u1")

    assert restored["today_calories"] == 244.2
    assert restored["target_calories"] == 1800
    assert [item["role"] for item in restored["messages"]] == ["user", "assistant"]
    assert restored["pending_proposal"]["id"] == "p1"
    assert restored["pending_state"]["awaiting_confirmation"] is True
    assert restored["interrupted"] is True
    graph.aget_state.assert_awaited_once()


async def test_session_restore_filters_messages_by_requested_thread(monkeypatch, fake_sb):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    import app.api.routes.main as main

    filters = []
    orders = []

    class Result:
        data = []

    class Query:
        def select(self, *args): return self
        def eq(self, key, value):
            filters.append((key, value))
            return self
        def order(self, *args, **kwargs):
            orders.append((args, kwargs))
            return self
        def limit(self, *args): return self
        def execute(self): return Result()

    class DB:
        def table(self, name): return Query()

    monkeypatch.setattr(main, "sb", DB())
    monkeypatch.setattr(main, "get_graph", lambda: SimpleNamespace(
        aget_state=AsyncMock(return_value=SimpleNamespace(values={}, next=()))))

    await main.restore_session("thread-b", "u1")

    assert ("thread_id", "thread-b") in filters
    assert orders == [(("created_at",), {"desc": True}), (("role",), {"desc": False})]


async def test_save_chat_persists_thread_identity(monkeypatch):
    import app.agents.graph as graph_module
    import app.db.supabase_client as db_module

    inserted = []

    class Query:
        def insert(self, payload):
            inserted.extend(payload)
            return self
        def execute(self):
            return type("Result", (), {"data": inserted})()

    class DB:
        def table(self, name):
            assert name == "chat_history"
            return Query()

    monkeypatch.setattr(db_module, "get_supabase", lambda: DB())

    await graph_module.save_chat_node({
        "user_id": "u1", "thread_id": "thread-b", "message": "질문",
        "response": "답변", "agent_used": "meal",
    })

    assert [row["thread_id"] for row in inserted] == ["thread-b", "thread-b"]
    assert inserted[0]["created_at"] < inserted[1]["created_at"]


async def test_ocr_creates_proposal_without_measurement_or_strategy_write(monkeypatch):
    from app.api.routes import main
    values = {"measured_date": "2026-10-08", "weight_kg": 56.1, "skeletal_muscle_kg": 23,
              "body_fat_kg": 12, "body_fat_pct": 21.4}
    monkeypatch.setattr(main, "extract_inbody_from_image", AsyncMock(return_value=values))
    repo = AsyncMock()
    repo.create.return_value = {"id": "p1", "version": 1, "kind": "measurement"}
    monkeypatch.setattr(main, "ProposalRepository", lambda: repo)
    result = await main._process_inbody("u1", b"synthetic image")
    assert result["strategy_updated"] is False
    assert repo.create.call_args.args[2]["weight_kg"] == 56.1
    assert repo.create.call_args.args[2]["measured_date"] == "2026-10-08"
    repo.resolve.assert_not_called()
