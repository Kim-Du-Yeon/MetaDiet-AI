from unittest.mock import AsyncMock
import pandas as pd
from langchain_core.messages import AIMessage
from app.agents.team import DietTeam


async def test_missing_branded_foods_stop_search_and_request_label(monkeypatch):
    import app.tools.nutrition_db as nutrition
    monkeypatch.setattr(nutrition, '_load_raw_df', lambda: pd.DataFrame([{'식품명': '쌀밥'}]))
    root = Model([call('delegate_meal', {'query': 'record foods'})])
    child = Model([call('search_foods', {'query': name}) for name in
                   ['라이스페이퍼', '돼지바', '브랜드 아이스크림']] + [AIMessage(content='done')])
    models = iter([root, child])
    repo = AsyncMock()
    team = DietTeam({'user_id': 'u1', 'message': '밥 450g 라이스페이퍼 10g 돼지바',
                     'requested_action': 'record_only'}, model_factory=lambda: next(models),
                    repository=repo, db=object())
    result = await team.execute()
    assert result['execution_status'] == 'blocked'
    assert '영양정보' in result['response']
    assert result['execution_usage']['tool_calls'] == 4
    repo.create.assert_not_called()
    assert any(event.get('reason') == 'food_not_found' for event in result['agent_events'])


async def test_validator_distinguishes_csv_nutrition_from_guideline_evidence():
    from app.agents.team import Verdict
    captured = []
    class Validator:
        def with_structured_output(self, schema):
            return self
        async def ainvoke(self, messages, config=None):
            captured.extend(messages)
            return Verdict(passed=True, feedback='ok')
    team = DietTeam({'user_id': 'u1', 'message': '밥 100g 계획'},
                    model_factory=Validator, repository=AsyncMock(), db=object())
    await team.validate({'kind': 'plan', 'meals': [{'source': 'csv', 'calories': 130}]})
    policy = captured[0]['content']
    assert 'csv' in policy and 'RAG' in policy
    assert '전략 변경' in policy


def call(name, args):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": name, "type": "tool_call"}])


class Model:
    def __init__(self, responses):
        self.ainvoke = AsyncMock(side_effect=responses)
    def bind_tools(self, schemas):
        self.schemas = schemas
        return self


async def test_supervisor_delegates_and_meal_agent_selects_tools_before_proposal(monkeypatch):
    import app.tools.nutrition_db as nutrition
    monkeypatch.setattr(nutrition, "_load_raw_df", lambda: pd.DataFrame([{
        "식품명": "쌀밥", "에너지": 150, "단백질": 3, "탄수화물": 33, "지방": 1, "나트륨": 2}]))
    supervisor = Model([call("delegate_meal", {"query": "record rice"}), AIMessage(content="확인해주세요")])
    specialist = Model([call("search_foods", {"query": "쌀밥"}),
        call("nutrition_lookup", {"food_id": 0, "quantity_g": 200}),
        call("propose_meal", {"kind": "intake", "log_date": "2026-10-09", "meals": [{"quote_id": "0:200.0", "meal_type": "lunch"}]}),
        AIMessage(content="섭취 기록 제안")])
    models = iter([supervisor, specialist])
    repo = AsyncMock()
    async def create(user, thread, payload, key):
        return {"id": "p1", "version": 1, "kind": payload["kind"], "payload": payload, "status": "pending"}
    repo.create.side_effect = create
    team = DietTeam({"user_id": "u1", "thread_id": "t1", "run_id": "r1", "message": "점심 쌀밥 200g 기록만",
                     "requested_action": "record_only"}, model_factory=lambda: next(models), repository=repo, db=object())
    result = await team.execute()
    assert result["pending_proposal"]["payload"]["meals"][0]["calories"] == 300
    assert result["awaiting_confirmation"] is True
    assert result["execution_usage"]["model_calls"] == 5
    repo.resolve.assert_not_called()
    names = [s["function"]["name"] for s in specialist.schemas]
    assert "search_evidence" not in names
    assert "propose_meal_change" not in names


async def test_no_search_policy_reaches_specialist():
    root = Model([call("delegate_evidence", {"query": "help"}), AIMessage(content="검색 금지로 근거 검색을 하지 않았습니다.")])
    child = Model([AIMessage(content="검색할 수 없습니다")])
    models = iter([root, child])
    team = DietTeam({"user_id": "u1", "message": "검색하지 말고 설명", "tool_policy": []},
                   model_factory=lambda: next(models), repository=AsyncMock(), db=object())
    result = await team.execute()
    assert result["execution_status"] == "completed"
    assert not hasattr(child, "schemas")


async def test_unoffered_food_id_cannot_be_used():
    import pytest
    from app.agents.team import FoodLookup
    team = DietTeam({"user_id": "u1", "message": "food"}, repository=AsyncMock(), db=object())
    with pytest.raises(ValueError, match="offered"):
        await team.nutrition_lookup(FoodLookup(food_id=555, quantity_g=100))


async def test_today_intake_uses_server_date_instead_of_model_supplied_date():
    from app.agents.team import MealDraft, QuotedMeal
    from app.core.service_clock import service_today

    team = DietTeam(
        {"user_id": "u1", "message": "오늘 간식으로 사과 100g 먹었어. 기록만 해줘."},
        repository=AsyncMock(), db=object(),
    )
    team.quotes["apple:100"] = {
        "food_name": "사과, 생것", "quantity_g": 100, "source": "csv",
        "calories": 52, "protein_g": 0.3, "carbs_g": 14,
        "fat_g": 0.1, "sodium_mg": 0,
    }

    await team.propose_meal(MealDraft(
        kind="intake",
        log_date="2025-01-01",
        meals=[QuotedMeal(quote_id="apple:100", meal_type="snack")],
    ))

    assert team.proposal["log_date"] == service_today().isoformat()


async def test_unrelated_question_preserves_pending_proposal():
    proposal = {"id": "p1", "version": 1, "payload": {"meals": []}}
    model = Model([AIMessage(content="질문에 대한 설명")])
    repo = AsyncMock()
    team = DietTeam({"user_id": "u1", "message": "이건 무슨 뜻이야?", "pending_proposal": proposal},
                    model_factory=lambda: model, repository=repo, db=object())
    result = await team.execute()
    assert result["pending_proposal"] == proposal
    assert result["awaiting_confirmation"]
    repo.create.assert_not_called()


async def test_profile_keeps_goal_priority_and_constraints():
    team = DietTeam({"user_id": "u1", "message": "목표"}, repository=AsyncMock(), db=object())
    team.rows = AsyncMock(side_effect=[[{"goal_priority": "muscle", "activity_level": "high",
                                        "allergies": ["peanut"], "age": 30}], []])
    result = await team.read_profile(None)
    assert result["goal_priority"] == "muscle"
    assert result["allergies"] == ["peanut"]
    assert result["activity_level"] == "high"


async def test_goal_specialist_gets_deterministic_progress_policy_tool():
    from app.agents.team import Empty
    team = DietTeam({"user_id": "u1", "message": "진행 점검"}, repository=AsyncMock(), db=object())
    team.profile={"goal":"diet"}
    team.rows=AsyncMock(return_value=[
        {"measured_date":"2026-01-30","weight_kg":79},
        {"measured_date":"2026-01-01","weight_kg":80},
    ])
    result=await team.assess_goal_progress(Empty())
    assert result["status"]=="lifestyle_review_recommended"
    assert result["automatic_calorie_adjustment_kcal"]==0
    assert "assess_goal_progress" in [tool.name for tool in team.tools("goal")]


async def test_evidence_uses_one_based_canonical_pdf_page(monkeypatch):
    from langchain_core.documents import Document
    from app.agents.team import Query
    async def retrieve(*args,**kwargs):
        return {"grounded":True,"docs":[Document(page_content="evidence",metadata={
            "source_file":"guide.pdf","page":5,"pdf_page":6,"document_sha256":"a"*64})]}
    monkeypatch.setattr('app.rag.retriever.retrieve',retrieve)
    team=DietTeam({"user_id":"u","message":"근거"},repository=AsyncMock(),db=object())
    result=await team.search_evidence(Query(query="test"))
    assert result['evidence'][0]['page']=='6'


async def test_ungrounded_evidence_search_blocks_unsupported_numeric_guidance(monkeypatch):
    async def retrieve(*args, **kwargs):
        return {"grounded": False, "docs": [], "context": "", "max_score": 0.01}
    monkeypatch.setattr('app.rag.retriever.retrieve', retrieve)
    supervisor = Model([
        call("delegate_meal", {"query": "dinner energy distribution"}),
        AIMessage(content="저녁은 하루 열량의 30~35%가 공식 권장량입니다."),
    ])
    specialist = Model([
        call("search_evidence", {"query": "dinner energy distribution"}),
        AIMessage(content="저녁은 하루 열량의 30~35%가 공식 권장량입니다."),
    ])
    models = iter([supervisor, specialist])
    team = DietTeam(
        {"user_id": "u1", "message": "공식 근거로 저녁 칼로리를 추천해줘"},
        model_factory=lambda: next(models), repository=AsyncMock(), db=object(),
    )

    result = await team.execute()

    assert "30~35" not in result["response"]
    assert "근거" in result["response"] and "보류" in result["response"]


async def test_grounded_macro_evidence_does_not_authorize_meal_percentage(monkeypatch):
    from langchain_core.documents import Document

    async def retrieve(*args, **kwargs):
        return {"grounded": True, "docs": [Document(
            page_content="성인의 탄수화물 에너지적정비율은 총 에너지의 50~65%이다.",
            metadata={"source_file": "KDRI.pdf", "pdf_page": 42},
        )]}

    monkeypatch.setattr("app.rag.retriever.retrieve", retrieve)
    supervisor = Model([
        call("delegate_meal", {"query": "저녁 식사 에너지 배분"}),
        AIMessage(content="저녁은 하루 열량의 30%인 800 kcal를 권장합니다."),
    ])
    specialist = Model([
        call("search_evidence", {"query": "저녁 식사 에너지 배분"}),
        AIMessage(content="저녁은 하루 열량의 30%인 800 kcal를 권장합니다."),
    ])
    models = iter([supervisor, specialist])
    team = DietTeam(
        {"user_id": "u1", "message": "공식 근거로 저녁 칼로리를 추천해줘"},
        model_factory=lambda: next(models), repository=AsyncMock(), db=object(),
    )

    result = await team.execute()

    assert "30%" not in result["response"]
    assert "끼니별" in result["response"] and "보류" in result["response"]


async def test_explicit_meal_recommendation_avoids_redundant_evidence_delegation():
    supervisor = Model([
        call("delegate_meal", {"query": "근거를 반영한 저녁 추천"}),
        AIMessage(content="저녁 추천 결과입니다."),
    ])
    specialist = Model([AIMessage(content="필요한 정보를 먼저 확인하겠습니다.")])
    models = iter([supervisor, specialist])
    team = DietTeam(
        {"user_id": "u1", "message": "공식 근거를 반영해서 오늘 저녁 식단을 추천해줘"},
        model_factory=lambda: next(models), repository=AsyncMock(), db=object(),
    )

    result = await team.execute()

    assert result["execution_status"] == "completed"
    names = [schema["function"]["name"] for schema in supervisor.schemas]
    assert names == ["delegate_meal"]


async def test_meal_specialist_must_read_intake_before_claiming_records_are_missing():
    supervisor = Model([call("delegate_meal", {"query": "오늘 섭취 기록 요약"})])
    specialist = Model([
        call("read_intake", {}),
        AIMessage(content="오늘 섭취 기록을 요약했습니다."),
    ])
    models = iter([supervisor, specialist])
    db = AsyncMock()
    team = DietTeam(
        {"user_id": "u1", "message": "오늘 먹은 기록만 간단히 요약해줘."},
        model_factory=lambda: next(models), repository=AsyncMock(), db=db,
    )
    team.rows = AsyncMock(return_value=[{"calories": 222}])

    result = await team.execute()

    specialist_instruction = specialist.ainvoke.call_args_list[0].args[0][0].content
    assert "반드시 read_intake" in specialist_instruction
    assert result["response"] == "오늘 섭취 기록을 요약했습니다."
    team.rows.assert_awaited_once()


async def test_evidence_search_reuses_same_query_without_second_retrieval(monkeypatch):
    from langchain_core.documents import Document
    from app.agents.team import Query

    retrieve = AsyncMock(return_value={"grounded": True, "docs": [Document(
        page_content="근거", metadata={"source_file": "guide.pdf", "pdf_page": 3})]})
    monkeypatch.setattr("app.rag.retriever.retrieve", retrieve)
    team = DietTeam({"user_id": "u1", "message": "근거"}, repository=AsyncMock(), db=object())

    first = await team.search_evidence(Query(query="저녁 식사 근거"))
    second = await team.search_evidence(Query(query="  저녁   식사 근거 "))

    assert first == second
    assert retrieve.await_count == 1
    assert team.budget.model_calls == 1


async def test_food_search_and_quote_reuse_cached_results(monkeypatch):
    from app.agents.team import Query, FoodLookup
    import app.tools.nutrition_db as nutrition

    loads = 0

    def load_df():
        nonlocal loads
        loads += 1
        return pd.DataFrame([{"식품명": "쌀밥", "에너지": 150, "단백질": 3,
                              "탄수화물": 33, "지방": 1, "나트륨": 2}])

    monkeypatch.setattr(nutrition, "_load_raw_df", load_df)
    team = DietTeam({"user_id": "u1", "message": "쌀밥"}, repository=AsyncMock(), db=object())

    assert await team.search_foods(Query(query="쌀밥")) == await team.search_foods(Query(query=" 쌀밥 "))
    quote = FoodLookup(food_id=0, quantity_g=100)
    assert await team.nutrition_lookup(quote) == await team.nutrition_lookup(quote)
    assert loads == 2
