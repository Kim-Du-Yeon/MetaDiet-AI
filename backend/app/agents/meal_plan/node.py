from app.core.llm import get_chat_model
from langchain_core.prompts import ChatPromptTemplate
from app.schemas.models import AgentState, extract_messages_context
from app.core.config import get_settings
from app.tools.analytics import get_yesterday_summary, get_pattern_analysis
from app.rag.region_guidance import get_region_guidance
from app.core.service_clock import service_today
import json, re
from datetime import date, timedelta

llm = get_chat_model(temperature=0.3)

MEAL_PLAN_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """당신은 영양학 전문 식단 플래너입니다.
아래 데이터를 종합적으로 분석해서 최적의 식단을 제안하세요.

[오늘 날짜]: {today}
[내일 날짜]: {tomorrow}
[사용자 목표]: {goal}
[현재 설정된 하루 목표]: {target_cal}kcal / 단백질 {target_protein}g

[오늘 식단 현황]:
{today_summary}

[전날 섭취 데이터]:
{yesterday_context}

[최근 7일 패턴]:
{pattern_context}

[영양학 근거 (RAG)]:
{rag_context}

[지역 기준 우선순위]:
{region_guidance}

[이전 검증 실패 피드백 - 있으면 반드시 반영]:
{validation_feedback}

당신의 역할:
- 제안하는 meals의 총 칼로리(total_calories)는 반드시 목표 칼로리({target_cal}kcal)의 90% 이상이어야 합니다
- [오늘 식단 현황]에 이미 섭취한 칼로리가 있으면, meals는 (목표 칼로리 {target_cal}kcal - 오늘 이미 섭취한 칼로리)를 채우도록 설계하세요
- 위 모든 데이터를 종합해서 위 90% 기준 안에서 세부 칼로리를 판단하세요
- 이전 검증 실패 피드백이 있으면 반드시 반영해서 수정하세요
- RAG 영양 근거가 있으면 반드시 식단 구성과 칼로리 설정에 반영하세요
- RAG 근거 영역에 "현재 문서 기반 근거는 부족합니다"가 있으면 출처 기반 설명을 만들지 마세요
- 단순히 칼로리만 줄이는 게 아니라 영양 균형을 함께 고려하세요
- message에 "목표 대비 +/-XXXkcal"를 쓸 때는 [전날 섭취 데이터]에 이미 계산된 값을 그대로 사용하세요(재계산 금지). 실제섭취가 목표보다 많으면 "+Nkcal 초과", 적으면 "-Nkcal 부족"으로 표기하세요

날짜 규칙:
- "오늘" 요청이면 plan_date를 {today}로
- "내일" 요청이면 plan_date를 {tomorrow}로
- 절대 임의 날짜 사용 금지

아래 JSON 형식으로만 응답하세요:
{{
  "plan_date": "YYYY-MM-DD",
  "meals": [
    {{
      "meal_type": "breakfast|lunch|dinner|snack",
      "food_name": "음식명",
      "quantity_g": 숫자,
      "calories": 숫자,
      "protein_g": 숫자,
      "carbs_g": 숫자,
      "fat_g": 숫자
    }}
  ],
  "total_calories": 숫자,
  "total_protein": 숫자,
  "message": "전날 XXXkcal 섭취(목표 대비 +/-XXXkcal). 오늘/내일 XXXkcal로 설정한 이유: [RAG 근거 포함 설명]"
}}
JSON 외 텍스트 금지."""),
    ("human", "{message}")
])


async def _generate_plan_json(messages) -> dict:
    """LLM이 가끔 JSON 외 텍스트를 섞어 보내 파싱이 깨지는 경우를 위해 1회만 재호출(최소 방어)."""
    for attempt in range(2):
        resp = await llm.ainvoke(messages)
        raw = re.sub(r"```json|```", "", resp.content).strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            if attempt == 1:
                raise
            print("=== meal_plan JSON 파싱 실패 → 1회 재시도 ===")


def format_plan_for_display(plan: dict) -> str:
    meal_labels = {
        "breakfast": "🌅 아침",
        "lunch": "☀️ 점심",
        "dinner": "🌙 저녁",
        "snack": "🍎 간식"
    }
    lines = [f"📋 **{plan['plan_date']} 식단 제안**\n"]
    by_meal = {}
    for m in plan["meals"]:
        mt = m["meal_type"]
        if mt not in by_meal:
            by_meal[mt] = []
        by_meal[mt].append(m)

    for mt in ["breakfast", "lunch", "dinner", "snack"]:
        if mt in by_meal:
            lines.append(f"\n{meal_labels[mt]}")
            for m in by_meal[mt]:
                lines.append(
                    f"  • {m['food_name']} {m['quantity_g']}g "
                    f"({m['calories']}kcal / 단백질 {m['protein_g']}g)"
                )

    lines.append(f"\n\n📊 **합계**: {plan['total_calories']}kcal / 단백질 {plan['total_protein']}g")
    lines.append(f"\n💬 {plan['message']}")
    lines.append("\n\n✅ **확정**하시겠습니까? 수정하고 싶은 끼니가 있으면 말씀해주세요.")
    lines.append("\n(다른 대화를 하시면 이 제안은 저장되지 않습니다)")
    return "\n".join(lines)


async def meal_plan_node(state: AgentState) -> dict:
    from app.db.supabase_client import get_supabase
    sb = get_supabase()
    user_id = state["user_id"]

    today_value = service_today()
    today = today_value.isoformat()
    tomorrow = (today_value + timedelta(days=1)).isoformat()

    # 오늘 식단 현황
    rows = sb.table("meal_logs").select("*").eq(
        "user_id", user_id).eq("log_date", today).execute().data
    today_cal = sum(r["calories"] for r in rows)
    today_protein = sum(r["protein_g"] for r in rows)
    by_meal = {}
    for row in rows:
        mt = row["meal_type"]
        if mt not in by_meal:
            by_meal[mt] = []
        by_meal[mt].append(row["food_name"])
    meal_lines = [f"{mt}: {', '.join(items)}" for mt, items in by_meal.items()]
    today_summary = "\n".join(meal_lines) if meal_lines else "아직 기록 없음"
    today_summary += f"\n누적: {round(today_cal)}kcal / 단백질 {round(today_protein)}g"

    target_cal = state.get("target_calories", 2000)
    target_protein = state.get("target_protein", 130)

    # 어제 데이터
    yesterday = await get_yesterday_summary(user_id)
    if yesterday["has_data"]:
        excess = yesterday["excess_calories"]
        sign = "+" if excess > 0 else ""
        yesterday_context = (
            f"어제 실제 섭취: {yesterday['total_calories']}kcal "
            f"(목표 {yesterday['target_calories']}kcal 대비 {sign}{excess}kcal), "
            f"단백질: {yesterday['total_protein']}g"
        )
    else:
        yesterday_context = "어제 기록 없음"

    # 최근 7일 패턴
    pattern = await get_pattern_analysis(user_id, days=7)
    if pattern["has_data"]:
        pattern_context = (
            f"7일 평균 칼로리: {pattern['avg_daily_calories']}kcal "
            f"(목표 달성률 {pattern['cal_achievement_pct']}%), "
            f"7일 평균 단백질: {pattern['avg_daily_protein']}g "
            f"(달성률 {pattern['protein_achievement_pct']}%)"
        )
    else:
        pattern_context = "패턴 데이터 부족"

    # 이전 검증 실패 피드백 (재생성 시 반영)
    validation_feedback = state.get("validation_feedback", "") or ""
    if validation_feedback:
        print(f"=== meal_plan 재생성: 검증 피드백 반영 → {validation_feedback[:80]}... ===")

    # RAG 검색 - 그래프 run당 1회만. 검증 루프 재진입(재생성) 시에는
    # state에 캐시된 근거를 재사용 → 동일 페이지 중복 검색 + 쿼리생성 LLM 호출 절감.
    # (영양학 근거는 객관적 사실이라 재생성마다 다시 뽑을 필요 없음. 변하는 건 식단뿐)
    rag_context  = state.get("rag_context")
    rag_grounded = state.get("rag_grounded")
    if rag_context is None:
        try:
            from app.rag.retriever import retrieve
            query_resp = await llm.ainvoke(
                f"""아래 상황에서 영양학 논문/가이드라인 검색에 가장 적합한 영어 검색 쿼리를 1줄로만 생성하세요.
상황: {state['message']}
사용자 목표: {state.get('user_goal', 'diet')}
목표 칼로리: {target_cal}kcal
검증 피드백: {validation_feedback[:100] if validation_feedback else '없음'}
영어 쿼리만 출력, 다른 텍스트 금지."""
            )
            rag_query = query_resp.content.strip()
            result = await retrieve(rag_query)
            rag_grounded = result["grounded"]
            rag_context  = result["context"] if rag_grounded and result["context"] else (
                "현재 문서 기반 근거는 부족합니다. "
                "출처 기반 설명은 생성하지 말고, 사용자 목표와 기록 기반으로만 식단을 제안하세요."
            )
            print(f"=== meal_plan RAG: query_redacted grounded={rag_grounded} score={result['max_score']} ===")
        except Exception as e:
            print(f"=== meal_plan RAG 실패 유형: {type(e).__name__} ===")
            rag_context, rag_grounded = (
                "현재 문서 기반 근거는 부족합니다. "
                "출처 기반 설명은 생성하지 말고, 사용자 목표와 기록 기반으로만 식단을 제안하세요."
            ), False
    else:
        print("=== meal_plan RAG: 캐시 재사용 (검증 루프, 재검색 생략) ===")

    plan = await _generate_plan_json(MEAL_PLAN_PROMPT.format_messages(
        today=today,
        tomorrow=tomorrow,
        goal=state.get("user_goal", "다이어트"),
        target_cal=target_cal,
        target_protein=target_protein,
        today_summary=today_summary,
        yesterday_context=yesterday_context,
        pattern_context=pattern_context,
        rag_context=rag_context,
        region_guidance=get_region_guidance(state.get("user_region")),
        validation_feedback=validation_feedback if validation_feedback else "없음",
        message=state["message"]
    ))
    if not rag_grounded:
        plan["message"] = (
            f"{plan.get('message', '')} "
            "현재 문서 기반 근거는 부족해 RAG 출처 기반 설명은 생략했습니다."
        ).strip()
    display_text = format_plan_for_display(plan)

    return {
        "response": display_text,
        "agent_used": "meal_plan",
        "pending_meals": plan["meals"],
        "awaiting_confirmation": True,
        "plan_date": plan["plan_date"],
        # 검증 루프(validator·재생성)에서 재사용하도록 RAG 근거 캐싱
        "rag_context": rag_context,
        "rag_grounded": rag_grounded,
    }

