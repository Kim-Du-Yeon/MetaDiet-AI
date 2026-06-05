from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from app.schemas.models import AgentState
from app.tools.agent_tools import (
    get_inbody_history_tool,
    update_strategy_tool,
    get_active_strategy_tool
)
from app.db.supabase_client import get_supabase
from app.core.config import get_settings
import json, re

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.2, openai_api_key=get_settings().openai_api_key)
sb = get_supabase()

ANALYSIS_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """당신은 체성분 분석 전문 식단 코치입니다.
인바디 변화 데이터와 영양학 근거를 종합해서 최적의 새 전략을 수립하세요.

[사용자 목표]: {goal}

[인바디 변화 이력]:
{inbody_history}

[현재 식단 전략]:
{current_strategy}

[RAG 영양학 근거]:
{rag_context}

당신의 역할:
- 인바디 변화를 분석해서 근손실/체지방 변화를 파악하세요
- RAG 영양학 근거를 반드시 활용해서 새 칼로리/단백질 목표를 결정하세요
- 단백질 권장량, 칼로리 설정은 RAG의 논문/가이드라인 근거로 판단하세요
- 하드코딩된 공식이 아닌 RAG 근거 + 체성분 변화를 종합해서 판단하세요
- strategy_note에 RAG 근거를 반드시 인용하세요

아래 JSON 형식으로만 응답하세요:
{{
  "analysis": "인바디 변화 분석 요약 (2~3문장)",
  "muscle_change": "increased|maintained|decreased",
  "fat_change": "increased|maintained|decreased",
  "new_daily_calories": 숫자,
  "new_protein_g": 숫자,
  "new_carbs_g": 숫자,
  "new_fat_g": 숫자,
  "strategy_note": "왜 이 전략으로 바꾸는지 RAG 근거 포함 설명 (3~4문장)",
  "user_message": "사용자에게 전달할 친근한 메시지 (2~3문장)"
}}
JSON 외 텍스트 금지."""),
    ("human", "인바디 분석 후 새 전략을 수립해주세요.")
])


async def inbody_node(state: AgentState) -> AgentState:
    user_id = state["user_id"]

    # 1. 인바디 이력 조회
    history = await get_inbody_history_tool.ainvoke({"user_id": user_id, "limit": 3})
    current_strategy = await get_active_strategy_tool.ainvoke({"user_id": user_id})

    if len(history) < 1:
        return {**state, "response": "인바디 데이터가 저장되지 않았습니다.", "agent_used": "inbody"}

    # 2. 인바디 이력 텍스트 구성
    history_lines = []
    for h in history:
        history_lines.append(
            f"  {h['measured_date']}: 체중 {h['weight_kg']}kg, "
            f"골격근 {h['skeletal_muscle_kg']}kg, "
            f"체지방률 {h['body_fat_pct']}%, "
            f"BMR {h.get('bmr_kcal', '미측정')}kcal"
        )
    history_text = "\n".join(history_lines)

    strategy_text = (
        f"  칼로리 {current_strategy.get('daily_calories')}kcal, "
        f"단백질 {current_strategy.get('protein_g')}g"
        if "daily_calories" in current_strategy else "전략 없음"
    )

    # 3. RAG 검색 - 체성분 변화에 맞는 영양학 근거
    latest = history[0]
    rag_query = (
        f"protein requirements muscle loss body composition "
        f"weight {latest['weight_kg']}kg skeletal muscle {latest['skeletal_muscle_kg']}kg "
        f"body fat {latest['body_fat_pct']}% {state.get('user_goal', 'diet')} calorie deficit"
    )
    try:
        from app.rag.retriever import search_nutrition_knowledge
        docs = await search_nutrition_knowledge(rag_query)
        rag_context = "\n".join([d.page_content for d in docs[:3]])
        print(f"=== inbody RAG 검색됨: {len(docs)}개 문서 ===")
    except Exception as e:
        print(f"=== inbody RAG 실패: {e} ===")
        rag_context = "영양 지식베이스 준비 중"

    # 4. AI 분석 + 새 전략 계산 (RAG 근거 기반)
    resp = await llm.ainvoke(ANALYSIS_PROMPT.format_messages(
        goal=state.get("user_goal", "다이어트"),
        inbody_history=history_text,
        current_strategy=strategy_text,
        rag_context=rag_context
    ))

    raw = re.sub(r"```json|```", "", resp.content).strip()
    result = json.loads(raw)

    # 5. 새 전략 DB 저장
    latest_inbody_id = history[0]["id"] if history else None
    await update_strategy_tool.ainvoke({
        "user_id": user_id,
        "daily_calories": result["new_daily_calories"],
        "protein_g": result["new_protein_g"],
        "carbs_g": result["new_carbs_g"],
        "fat_g": result["new_fat_g"],
        "strategy_note": result["strategy_note"],
        "triggered_by": "inbody_update",
        "inbody_log_id": latest_inbody_id,
    })

    full_response = (
        f"{result['user_message']}\n\n"
        f"**분석**: {result['analysis']}\n"
        f"**새 전략**: 하루 {result['new_daily_calories']}kcal / 단백질 {result['new_protein_g']}g\n\n"
        f"**근거**: {result['strategy_note']}"
    )

    return {
        **state,
        "response": full_response,
        "agent_used": "inbody",
        "target_calories": result["new_daily_calories"],
        "target_protein": result["new_protein_g"],
    }
