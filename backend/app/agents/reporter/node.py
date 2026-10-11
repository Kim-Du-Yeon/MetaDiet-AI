from app.core.llm import get_chat_model
from langchain_core.prompts import ChatPromptTemplate
from app.schemas.models import AgentState
from app.core.config import get_settings
from app.tools.analytics import get_pattern_analysis, get_inbody_diet_correlation, get_missing_meal_alert
from app.rag.region_guidance import get_region_guidance

llm = get_chat_model(temperature=0.3)

REPORT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """당신은 데이터 분석 기반 식단 코치입니다.
숫자와 패턴을 근거로 구체적인 인사이트를 제공합니다.
반드시 인바디 변화와 식단의 상관관계를 분석에 포함하세요.

[30일 패턴 분석]:
{pattern_analysis}

[인바디-식단 상관관계]:
{inbody_correlation}

[이번달 기록 누락]:
{missing_stats}

[현재 전략]:
하루 {target_cal}kcal / 단백질 {target_protein}g

[RAG 영양 근거]:
{rag_context}

[지역 기준 우선순위]:
{region_guidance}

RAG 근거 영역에 "현재 문서 기반 근거는 부족합니다"가 있으면 출처 기반 설명을 만들지 마세요.

아래 형식으로 반드시 답하세요:

**✅ 잘하고 있는 것**
(데이터 근거와 함께 1~2문장)

**⚠️ 개선이 필요한 것**
(구체적 수치와 함께 1~2문장)

**📊 패턴 분석**
(주말 초과, 단백질 부족 등 발견된 패턴. 요일별 수치 포함)

**💪 인바디-식단 상관관계**
(인바디 변화와 그 기간 식단 패턴을 반드시 연결해서 분석)

**📅 기록 성실도**
이번달 누락 일수와 다음달 개선 방향
(예: "이번달 8일 누락(27%). 다음달은 점심 기록부터 집중해보세요")

**🎯 다음 달 전략**
(이번달 패턴 + 누락 현황 기반으로 다음달 구체적 실행 방법 2~3가지)
(예: "지난달 칼로리 평균 XXXkcal, 단백질 달성률 XX%, 누락 X일이었습니다.
이번달은 좀 더 신경써서 목표를 이루어봐요")

**⏱️ 목표 달성 예상**
(현재 패턴 지속 시 목표까지 예상 기간)"""),
    ("human", "{message}")
])


async def reporter_node(state: AgentState) -> AgentState:
    user_id = state["user_id"]

    # 1. 30일 패턴 분석
    pattern = await get_pattern_analysis(user_id, days=30)
    if pattern["has_data"]:
        pattern_text = f"""
- 기록 일수: {pattern['period_days']}일
- 평균 칼로리: {pattern['avg_daily_calories']}kcal (목표 {pattern['target_calories']}kcal, 달성률 {pattern['cal_achievement_pct']}%)
- 평균 단백질: {pattern['avg_daily_protein']}g (목표 {pattern['target_protein']}g, 달성률 {pattern['protein_achievement_pct']}%)
- 요일별 패턴: {pattern['weekday_pattern']}
- 주말 초과 패턴: {'있음 (평균 ' + str(pattern['weekend_avg_excess']) + 'kcal 초과)' if pattern['has_weekend_excess_pattern'] else '없음'}
- 주말 패턴으로 인한 목표 지연: {pattern['weeks_delayed_by_weekend']}주"""
    else:
        pattern_text = "30일 데이터 부족"

    # 2. 인바디-식단 상관관계
    correlation = await get_inbody_diet_correlation(user_id)
    if correlation["has_data"]:
        correlation_text = f"""
- 분석 기간: {correlation['period']}
- 체중 변화: {correlation['weight_change']}kg
- 골격근 변화: {correlation['muscle_change']}kg
- 체지방 변화: {correlation['fat_change']}kg
- 해당 기간 단백질 달성률: {correlation['protein_achievement_pct']}%
- 인사이트: {correlation['insight']}"""
    else:
        correlation_text = "인바디 기록 2회 이상 필요"

    # 3. 누락 통계
    alert = await get_missing_meal_alert(user_id)
    missing_text = (
        f"이번달 누락 일수: {alert['missing_days_this_month']}일 / "
        f"전체 {alert['total_days_this_month']}일 "
        f"(누락률 {alert['missing_rate']}%)"
    )

    target_cal = state.get("target_calories", 2000)
    target_protein = state.get("target_protein", 130)

    # 4. RAG 검색 - grounded=True일 때만 출처 기반 근거로 사용
    try:
        from app.rag.retriever import retrieve
        rag_result = await retrieve(state["message"], k=4, max_docs=2)
        rag_grounded = bool(rag_result.get("grounded") and rag_result.get("context"))
        rag_context = rag_result["context"] if rag_grounded else (
            "현재 문서 기반 근거는 부족합니다. "
            "출처 기반 설명은 만들지 말고, 패턴·수치 기반의 일반적 인사이트만 제공하세요."
        )
    except Exception:
        rag_context = (
            "현재 문서 기반 근거는 부족합니다. "
            "출처 기반 설명은 만들지 말고, 패턴·수치 기반의 일반적 인사이트만 제공하세요."
        )
        rag_grounded = False

    resp = await llm.ainvoke(REPORT_PROMPT.format_messages(
        pattern_analysis=pattern_text,
        inbody_correlation=correlation_text,
        missing_stats=missing_text,
        target_cal=target_cal,
        target_protein=target_protein,
        rag_context=rag_context,
        region_guidance=get_region_guidance(state.get("user_region")),
        message=state["message"]
    ))

    return {**state, "response": resp.content, "agent_used": "reporter", "rag_grounded": rag_grounded}
