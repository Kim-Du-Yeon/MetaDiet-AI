from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from app.schemas.models import AgentState, extract_messages_context
from app.core.config import get_settings
from app.tools.analytics import get_yesterday_summary, get_pattern_analysis

llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0.3,
    openai_api_key=get_settings().openai_api_key
)

STRATEGY_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """당신은 영양학 전문 식단 코치입니다.
사용자의 현재 식단 상황과 RAG 영양학 근거를 바탕으로 실질적인 조언을 제공하세요.

[사용자 목표]: {goal}
[하루 목표]: {target_cal}kcal / 단백질 {target_protein}g
[오늘 현재까지 섭취]: {today_cal}kcal / 단백질 {today_protein}g
[남은 칼로리]: {remaining_cal}kcal
[전날 데이터]: {yesterday_context}
[최근 7일 패턴]: {pattern_context}
[직전 대화 맥락]: {recent_context}

[RAG 영양학 근거]:
{rag_context}

중요 지침:
- 칼로리를 초과했더라도 "굶어라"고 하지 마세요
- RAG 근거를 바탕으로 초과 시에도 최소한 먹어야 할 것을 제안하세요
- 칼로리가 남았으면 RAG 근거로 어떤 음식이 좋은지 구체적으로 제안하세요
- RAG 근거가 있으면 반드시 출처와 함께 인용하세요
- RAG 근거 영역에 "현재 문서 기반 근거는 부족합니다"가 있으면 출처 기반 조언을 하지 마세요
- 3~5문장으로 간결하고 실용적으로 답변하세요"""),
    ("human", "{message}")
])


async def strategy_node(state: AgentState) -> dict:
    from app.db.supabase_client import get_supabase
    sb = get_supabase()
    user_id = state["user_id"]

    target_cal = state.get("target_calories", 2000)
    target_protein = state.get("target_protein", 130)
    today_cal = state.get("today_calories", 0)
    today_protein = state.get("today_protein", 0)
    remaining_cal = round(target_cal - today_cal)

    # 어제 데이터
    yesterday = await get_yesterday_summary(user_id)
    if yesterday["has_data"]:
        excess = yesterday["excess_calories"]
        sign = "+" if excess > 0 else ""
        yesterday_context = (
            f"어제 {yesterday['total_calories']}kcal 섭취 "
            f"(목표 대비 {sign}{excess}kcal)"
        )
    else:
        yesterday_context = "어제 기록 없음"

    # 최근 7일 패턴
    pattern = await get_pattern_analysis(user_id, days=7)
    if pattern["has_data"]:
        pattern_context = (
            f"7일 평균 {pattern['avg_daily_calories']}kcal "
            f"(달성률 {pattern['cal_achievement_pct']}%), "
            f"단백질 달성률 {pattern['protein_achievement_pct']}%"
        )
    else:
        pattern_context = "패턴 데이터 부족"

    # 직전 대화 맥락
    recent_context = extract_messages_context(state.get("messages", []))

    # RAG 검색 - grounded=True일 때만 문서 기반 조언에 사용
    try:
        from app.rag.retriever import retrieve

        # 상황에 맞는 RAG 쿼리 생성
        situation = "calorie deficit meal recommendation" if remaining_cal > 0 else "calorie exceeded healthy evening meal minimum intake"
        query_resp = await llm.ainvoke(
            f"""아래 상황에서 영양학 논문/가이드라인 검색에 가장 적합한 영어 검색 쿼리를 1줄로만 생성하세요.
사용자 메시지: {state['message']}
상황: 오늘 {round(today_cal)}kcal 섭취, 목표 {target_cal}kcal, 남은 칼로리 {remaining_cal}kcal
목표: {state.get('user_goal', 'diet')}
보조 키워드: {situation}
영어 쿼리만 출력, 다른 텍스트 금지."""
        )
        rag_query = query_resp.content.strip()
        rag_result = await retrieve(rag_query, k=4, max_docs=2)
        rag_grounded = bool(rag_result.get("grounded") and rag_result.get("context"))
        if rag_grounded:
            rag_context = rag_result["context"]
        else:
            rag_context = (
                "현재 문서 기반 근거는 부족합니다. "
                "출처 기반 조언은 생성하지 말고, 사용자 기록과 목표 기반의 일반 안내만 하세요."
            )
        print(f"=== strategy RAG 쿼리: {rag_query} | grounded={rag_grounded} score={rag_result.get('max_score')} ===")
    except Exception as e:
        print(f"=== strategy RAG 실패: {e} ===")
        rag_context = (
            "현재 문서 기반 근거는 부족합니다. "
            "출처 기반 조언은 생성하지 말고, 사용자 기록과 목표 기반의 일반 안내만 하세요."
        )
        rag_grounded = False

    resp = await llm.ainvoke(STRATEGY_PROMPT.format_messages(
        goal=state.get("user_goal", "다이어트"),
        target_cal=target_cal,
        target_protein=target_protein,
        today_cal=round(today_cal),
        today_protein=round(today_protein),
        remaining_cal=remaining_cal,
        yesterday_context=yesterday_context,
        pattern_context=pattern_context,
        recent_context=recent_context,
        rag_context=rag_context,
        message=state["message"]
    ))

    return {
        "response": resp.content,
        "agent_used": "strategy",
        "rag_grounded": rag_grounded,
    }

