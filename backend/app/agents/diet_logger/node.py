"""
diet_logger/node.py

역할: 파싱 + 영양계산 + RAG피드백 생성 → pending_meals 저장 후 종료
      HITL은 이 노드에서 처리하지 않음. confirm_node가 전담.

흐름:
  diet_logger_node → state에 pending_meals, response(확인화면) 저장 → save_chat → END
  다음 요청에서 supervisor가 pending_meals 감지 → confirm 라우팅
  interrupt_before=["confirm"] → 사용자 확인 대기 → resume → confirm_node 실행
"""
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from app.schemas.models import AgentState, extract_messages_context
from app.core.config import get_settings
from app.tools.agent_tools import get_today_meals_tool, check_missing_meals_tool, rag_nutrition_tool
from app.tools.nutrition_db import nutrition_db_tool
from app.rag.region_guidance import get_region_guidance
import json, re

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0,
                 openai_api_key=get_settings().openai_api_key)

PARSE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """사용자가 먹은 음식을 파싱해서 JSON 배열로만 응답하세요.
각 항목: {{"food_name": "음식명", "quantity_g": 숫자, "meal_type": "breakfast|lunch|dinner|snack"}}

[오늘 이미 기록된 끼니 (참고용)]: {logged_meals}
[최근 대화 맥락]: {recent_context}

규칙:
- 현재 사용자 메시지에 새로 말한 음식만 파싱하세요.
- 최근 대화 맥락의 음식은 사용자가 "그거", "아까 말한 것", "위 음식"처럼 명시적으로 참조할 때만 사용하세요.
- 현재 메시지가 "점심 쌀밥 100g, 닭가슴살 200g"이면 이전 아침/간식 기록을 절대 포함하지 마세요.
- 사용자가 명시한 음식은 이미 기록된 끼니여도 반드시 파싱 (중복 여부는 사용자가 결정)
- 오타 교정 (예: "달각슴살" → "닭가슴살")
- meal_type: 명시 없으면 미기록 끼니로 추정
- 양 없으면 일반 1인분으로 추정
- 반드시 1개 이상 반환 (빈 배열 금지)
JSON 외 텍스트 금지."""),
    ("human", "{message}")
])

NUTRITION_LLM_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """다음 음식의 영양성분을 JSON으로만 응답하세요.
{{"calories": 숫자, "protein_g": 숫자, "carbs_g": 숫자, "fat_g": 숫자, "sodium_mg": 숫자}}
한국 식품영양성분 기준. JSON 외 텍스트 금지."""),
    ("human", "{food_name} {quantity_g}g")
])

FEEDBACK_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """영양학 전문 식단 코치입니다. RAG 근거 기반 간결한 피드백을 주세요.
[오늘 누적]: {today_cal}kcal / 목표 {target_cal}kcal | 단백질 {today_protein}g / 목표 {target_protein}g
[기록 음식]: {food_names}
[RAG 근거]: {rag_context}

[지역 기준 우선순위]: {region_guidance}

규칙:
- RAG 근거 있으면 출처(파일명, 페이지) 반드시 명시
- RAG 근거 없으면 추측하지 말고 일반적 조언만
- RAG 근거 영역이 비어 있거나 근거 부족이면 출처 기반 피드백을 만들지 마세요
- 2~3문장, 다음 끼니 제안 포함"""),
    ("human", "피드백 주세요.")
])


def _format_display(pending_meals: list, today_meals: list) -> str:
    """확인 화면 텍스트 생성"""
    meal_labels = {"breakfast": "🌅 아침", "lunch": "☀️ 점심",
                   "dinner": "🌙 저녁", "snack": "🍎 간식"}
    lines = ["📋 **아래 식단으로 기록할까요?**\n"]
    by_meal = {}
    for m in pending_meals:
        by_meal.setdefault(m["meal_type"], []).append(m)
    for mt in ["breakfast", "lunch", "dinner", "snack"]:
        if mt not in by_meal:
            continue
        lines.append(f"\n{meal_labels[mt]}")
        for m in by_meal[mt]:
            mark = "📊" if m.get("source") == "csv" else "🤖"
            lines.append(
                f"  • {m['food_name']} {m['quantity_g']}g "
                f"({round(m['calories'])}kcal | 탄 {round(m.get('carbs_g',0))}g | "
                f"단 {round(m['protein_g'])}g | 지 {round(m.get('fat_g',0))}g | "
                f"나트륨 {round(m.get('sodium_mg',0))}mg) {mark}"
            )
    p_cal    = round(sum(m["calories"]         for m in pending_meals))
    p_carbs  = round(sum(m.get("carbs_g",  0)  for m in pending_meals))
    p_prot   = round(sum(m["protein_g"]         for m in pending_meals))
    p_fat    = round(sum(m.get("fat_g",    0)   for m in pending_meals))
    p_sodium = round(sum(m.get("sodium_mg", 0)  for m in pending_meals))
    lines.append(f"\n\n📊 **이번 식사 합계**: {p_cal}kcal | 탄 {p_carbs}g | 단 {p_prot}g | 지 {p_fat}g | 나트륨 {p_sodium}mg")
    all_meals = today_meals + pending_meals
    if all_meals:
        t_cal    = round(sum(m["calories"]         for m in all_meals))
        t_carbs  = round(sum(m.get("carbs_g",  0)  for m in all_meals))
        t_prot   = round(sum(m["protein_g"]         for m in all_meals))
        t_fat    = round(sum(m.get("fat_g",    0)   for m in all_meals))
        t_sodium = round(sum(m.get("sodium_mg", 0)  for m in all_meals))
        lines.append(f"\n📈 **오늘 누적 합계**: {t_cal}kcal | 탄 {t_carbs}g | 단 {t_prot}g | 지 {t_fat}g | 나트륨 {t_sodium}mg")
    lines.append("\n\n✅ **확정**하시겠습니까? 수정하고 싶으신 끼니가 있으면 말씀해주세요.")
    lines.append("(다른 대화를 하시면 기록 없이 넘어갑니다)")
    return "\n".join(lines)


def _references_previous_context(message: str) -> bool:
    msg = message or ""
    return any(k in msg for k in ["그거", "그걸", "그 음식", "아까", "위에서", "방금", "말한대로", "말한 대로"])


def _filter_current_message_items(items: list, message: str) -> list:
    if _references_previous_context(message):
        return items

    normalized_msg = re.sub(r"\s+", "", message or "").lower()
    filtered = []
    for item in items:
        food_name = str(item.get("food_name", ""))
        normalized_food = re.sub(r"\s+", "", food_name).lower()
        if normalized_food and normalized_food in normalized_msg:
            filtered.append(item)

    return filtered or items


async def diet_logger_node(state: AgentState) -> dict:
    """파싱 + 영양계산 + RAG피드백 → pending_meals 저장"""
    from datetime import date
    user_id = state["user_id"]
    today   = date.today().isoformat()

    today_data     = await get_today_meals_tool.ainvoke({"user_id": user_id})
    logged_meals   = today_data["logged_meal_types"]
    today_meals    = today_data["today_meals"]
    recent_context = extract_messages_context(state.get("messages", []))

    parse_resp = await llm.ainvoke(PARSE_PROMPT.format_messages(
        message=state["message"],
        logged_meals=logged_meals if logged_meals else "없음",
        recent_context=recent_context,
    ))
    items = json.loads(re.sub(r"```json|```", "", parse_resp.content).strip())
    items = _filter_current_message_items(items, state["message"])

    # 사용자가 버튼으로 끼니를 지정했으면(forced_meal_type) LLM 추측 대신 강제 적용.
    # 끼니는 추론할 사실이 아니라 사용자가 정하는 값 → 오분류(점심/간식 임의지정) 방지.
    forced_meal_type = state.get("forced_meal_type")

    pending_meals = []
    for item in items:
        food_name  = item["food_name"]
        quantity_g = float(item["quantity_g"])
        meal_type  = forced_meal_type or item.get("meal_type", "snack")
        db_result  = await nutrition_db_tool.ainvoke({"food_name": food_name, "quantity_g": quantity_g})
        if db_result.get("found_in_db"):
            nutrition = {k: db_result[k] for k in ["calories","protein_g","carbs_g","fat_g","sodium_mg"]}
            source    = "csv"
        else:
            nutr_resp = await llm.ainvoke(NUTRITION_LLM_PROMPT.format_messages(
                food_name=food_name, quantity_g=quantity_g))
            nutrition = json.loads(re.sub(r"```json|```", "", nutr_resp.content).strip())
            source    = "llm_estimated"
            print(f"=== LLM 추정: {food_name} ===")
        pending_meals.append({
            "meal_type": meal_type, "food_name": food_name, "quantity_g": quantity_g,
            "calories":  float(nutrition["calories"]),  "protein_g": float(nutrition["protein_g"]),
            "carbs_g":   float(nutrition.get("carbs_g", 0)), "fat_g": float(nutrition.get("fat_g", 0)),
            "sodium_mg": float(nutrition.get("sodium_mg", 0)), "source": source,
        })

    # RAG 피드백: grounded=True일 때만 출처 기반 피드백 생성
    food_names_str = " ".join(item["food_name"] for item in items)
    rag_context = ""
    rag_grounded = False
    try:
        from app.rag.retriever import retrieve
        rag_result = await retrieve(f"nutrition benefits {food_names_str} dietary guidelines health", k=4, max_docs=2)
        rag_grounded = bool(rag_result.get("grounded") and rag_result.get("context"))
        rag_context = rag_result["context"] if rag_grounded else ""
        print(f"=== [diet_logger] RAG grounded={rag_grounded} score={rag_result.get('max_score')} ===")
    except Exception as e:
        print(f"=== [diet_logger] RAG 검색 오류: {e} ===")

    missing_alert = ""
    try:
        just_recorded  = list(set(m["meal_type"] for m in pending_meals))
        missing_result = await check_missing_meals_tool.ainvoke({
            "logged_meals": logged_meals or [], "pending_meals": just_recorded, "just_recorded": just_recorded,
        })
        if missing_result.get("has_missing") and missing_result.get("missing_meals"):
            missing_alert = f"\n\n⚠️ **알림**: {', '.join(missing_result['missing_meals'])} 식사 기록이 없습니다."
    except Exception as e:
        print(f"=== 누락 감지 오류: {e} ===")

    rag_feedback = ""
    if rag_grounded:
        try:
            all_combined = today_meals + pending_meals
            feedback_resp = await llm.ainvoke(FEEDBACK_PROMPT.format_messages(
                today_cal=round(sum(m["calories"] for m in all_combined)),
                target_cal=state.get("target_calories", 2000),
                today_protein=round(sum(m["protein_g"] for m in all_combined)),
                target_protein=state.get("target_protein", 130),
                food_names=food_names_str, rag_context=rag_context,
                region_guidance=get_region_guidance(state.get("user_region")),
            ))
            rag_feedback = f"\n\n💡 {feedback_resp.content.strip()}"
        except Exception as e:
            print(f"=== 피드백 생성 오류: {e} ===")
    else:
        rag_feedback = "\n\n💡 현재 문서 기반 근거는 부족해 출처 기반 피드백은 생략합니다."

    # mixed intent("어제 ~ 먹었어 + 오늘 식단 짜줘"): supervisor가 diet_logger를 우선
    # 라우팅했을 때, 식단 계획 요청이 묻히지 않도록 기록 응답 뒤에 안내를 덧붙인다.
    from app.agents.supervisor.node import _PLAN_KW
    plan_hint = ""
    if any(k in state["message"] for k in _PLAN_KW):
        plan_hint = "\n\n📋 식단 기록 완료 후 \"식단 짜줘\"라고 말씀해주세요."

    display_text = _format_display(pending_meals, today_meals) + missing_alert + rag_feedback + plan_hint
    print(f"=== [diet_logger] 완료 | pending={len(pending_meals)}개 ===")

    return {
        "response":              display_text,
        "agent_used":            "diet_logger",
        "pending_meals":         pending_meals,
        "awaiting_confirmation": True,
        "plan_date":             today,
        "rag_grounded":          rag_grounded,
    }

