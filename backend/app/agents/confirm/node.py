"""
confirm/node.py

역할: HITL 전담 agent.
      diet_logger 또는 meal_plan이 생성한 pending_meals를
      사용자 응답(message)에 따라 확정/수정/취소 처리.

흐름:
  graph.compile(interrupt_before=["confirm"])
  → diet_logger/meal_plan 완료 후 confirm 진입 전 자동 대기
  → routes/main.py: aupdate_state({"message": user_input}) + ainvoke(None)
  → confirm_node 실행: state["message"]로 LLM 분류
  → confirm → save_meal_tool로 저장
  → modify  → pending_meals 업데이트 + awaiting_confirmation=True
               (supervisor가 다음 요청도 confirm으로 라우팅)
  → cancel  → pending 초기화

Tools: save_meal_tool, rag_nutrition_tool (수정 시 영양 재계산용)
"""
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from app.schemas.models import AgentState
from app.core.config import get_settings
from app.tools.agent_tools import save_meal_tool
from app.tools.nutrition_db import nutrition_db_tool
import json, re

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0,
                 openai_api_key=get_settings().openai_api_key)

CONFIRM_CLASSIFY_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """사용자가 아래 식단 확인 화면을 보고 응답했습니다.
의도를 파악해서 confirm / modify / cancel 중 하나만 출력하세요.

[확인 중인 식단]:
{pending_summary}

confirm(저장): "응","ㅇ","네","ok","저장","저장해줘","확정","맞아","좋아","그래","기록","할게" 등
modify(수정): 특정 음식 수정/변경/추가/삭제 요청이 명확한 경우 (예: "삼겹살 150g으로", "현미밥 빼줘")
cancel(취소): "취소","됐어","아니야","그만" 등

판단 불명확 시 confirm. 단어 하나만 출력."""),
    ("human", "사용자 응답: {message}")
])

MODIFY_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """현재 식단을 사용자 요청에 맞게 수정하세요.
[현재 식단]: {current_plan}

수정 후 JSON으로만 응답:
{{"meals": [{{"meal_type":"...","food_name":"...","quantity_g":숫자,
             "calories":숫자,"protein_g":숫자,"carbs_g":숫자,"fat_g":숫자,"sodium_mg":숫자}}],
  "message":"수정 내용 설명"}}
JSON 외 텍스트 금지."""),
    ("human", "수정 요청: {message}")
])

NUTRITION_LLM_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """다음 음식의 영양성분을 JSON으로만 응답하세요.
{{"calories":숫자,"protein_g":숫자,"carbs_g":숫자,"fat_g":숫자,"sodium_mg":숫자}}
한국 식품영양성분 기준. JSON 외 텍스트 금지."""),
    ("human", "{food_name} {quantity_g}g")
])


def _format_pending_summary(pending_meals: list) -> str:
    labels = {"breakfast":"아침","lunch":"점심","dinner":"저녁","snack":"간식"}
    return "\n".join(
        f"  [{labels.get(m.get('meal_type',''),'')}] {m['food_name']} {m['quantity_g']}g ({round(m['calories'])}kcal)"
        for m in pending_meals
    ) if pending_meals else "없음"


def _format_modified_display(meals: list, plan_date: str, message: str) -> str:
    meal_labels = {"breakfast":"🌅 아침","lunch":"☀️ 점심","dinner":"🌙 저녁","snack":"🍎 간식"}
    lines = [f"📋 **수정된 식단**\n"]
    by_meal = {}
    for m in meals:
        by_meal.setdefault(m["meal_type"], []).append(m)
    for mt in ["breakfast","lunch","dinner","snack"]:
        if mt not in by_meal: continue
        lines.append(f"\n{meal_labels[mt]}")
        for m in by_meal[mt]:
            lines.append(
                f"  • {m['food_name']} {m['quantity_g']}g "
                f"({round(m['calories'])}kcal | 탄 {round(m.get('carbs_g',0))}g | "
                f"단 {round(m['protein_g'])}g | 지 {round(m.get('fat_g',0))}g | "
                f"나트륨 {round(m.get('sodium_mg',0))}mg)"
            )
    total_cal  = round(sum(m["calories"]  for m in meals))
    total_prot = round(sum(m["protein_g"] for m in meals))
    lines.append(f"\n\n📊 **합계**: {total_cal}kcal | 단백질 {total_prot}g")
    lines.append(f"\n💬 {message}")
    lines.append("\n\n✅ **확정**하시겠습니까? 추가 수정이 있으면 말씀해주세요.")
    return "\n".join(lines)


async def confirm_node(state: AgentState) -> dict:
    user_id   = state["user_id"]
    pending   = state.get("pending_meals") or []
    plan_date = state.get("plan_date") or state.get("today_date", "")
    message   = state.get("message", "")

    print(f"=== [confirm] 진입 | pending={len(pending)}개 | message='{message}' ===")

    if not pending:
        return {
            "response":              "확정할 식단 제안이 없습니다. 먼저 식단을 말씀해주세요.",
            "agent_used":            "confirm",
            "awaiting_confirmation": False,
            "pending_meals":         None,
        }

    # LLM이 의도 분류
    classify   = await llm.ainvoke(CONFIRM_CLASSIFY_PROMPT.format_messages(
        pending_summary=_format_pending_summary(pending), message=message,
    ))
    raw_action = classify.content.strip().lower()
    action     = raw_action if raw_action in ("confirm","modify","cancel") else "confirm"
    print(f"=== [confirm] LLM 분류: '{raw_action}' → '{action}' ===")

    # ── confirm: 저장 ─────────────────────────────────────────────────
    if action == "confirm":
        # 저장 전 같은 날짜+끼니의 기존 기록 삭제 (롤백 후 중복 저장 방지)
        # 예: 삼겹살 150g 저장 후 롤백 → 닭가슴살로 저장 시 삼겹살 자동 삭제
        try:
            from app.db.supabase_client import get_supabase
            sb = get_supabase()
            meal_types_to_overwrite = list(set(m["meal_type"] for m in pending))
            for mt in meal_types_to_overwrite:
                sb.table("meal_logs").delete()                  .eq("user_id", user_id)                  .eq("log_date", plan_date)                  .eq("meal_type", mt)                  .execute()
                print(f"=== [confirm] 기존 {mt} 기록 삭제 ({plan_date}) ===")
        except Exception as e:
            print(f"=== [confirm] 기존 기록 삭제 실패: {e} ===")

        saved = 0
        for meal in pending:
            r = await save_meal_tool.ainvoke({
                "user_id": user_id, "log_date": plan_date,
                "meal_type": meal["meal_type"], "food_name": meal["food_name"],
                "quantity_g": float(meal["quantity_g"]), "calories": float(meal["calories"]),
                "protein_g": float(meal["protein_g"]), "carbs_g": float(meal.get("carbs_g",0)),
                "fat_g": float(meal.get("fat_g",0)), "sodium_mg": float(meal.get("sodium_mg",0)),
            })
            if r.get("success"): saved += 1
        total_cal    = round(sum(m["calories"]        for m in pending))
        total_carbs  = round(sum(m.get("carbs_g",0)   for m in pending))
        total_prot   = round(sum(m["protein_g"]        for m in pending))
        total_fat    = round(sum(m.get("fat_g",0)     for m in pending))
        total_sodium = round(sum(m.get("sodium_mg",0)  for m in pending))
        print(f"=== [confirm] 저장 완료: {saved}/{len(pending)}개 ===")
        return {
            "response":              f"✅ **{plan_date} 식단이 캘린더에 저장됐습니다!**\n\n📊 {total_cal}kcal | 탄 {total_carbs}g | 단 {total_prot}g | 지 {total_fat}g | 나트륨 {total_sodium}mg\n\n더 드신 음식이 있으면 언제든지 말씀해주세요.",
            "agent_used":            "confirm",
            "pending_meals":         None,
            "awaiting_confirmation": False,
        }

    # ── modify: LLM이 수정 후 재제안, CSV로 영양 재계산 ─────────────
    elif action == "modify":
        modify_resp = await llm.ainvoke(MODIFY_PROMPT.format_messages(
            current_plan=json.dumps(pending, ensure_ascii=False), message=message,
        ))
        new_plan  = json.loads(re.sub(r"```json|```", "", modify_resp.content).strip())
        new_meals = new_plan["meals"]

        # 수정된 음식에 대해 CSV로 영양 재계산 (하드코딩 없이 DB 우선)
        recalculated = []
        for meal in new_meals:
            db_result = await nutrition_db_tool.ainvoke({
                "food_name": meal["food_name"], "quantity_g": float(meal["quantity_g"])
            })
            if db_result.get("found_in_db"):
                meal.update({
                    "calories": db_result["calories"], "protein_g": db_result["protein_g"],
                    "carbs_g": db_result["carbs_g"], "fat_g": db_result["fat_g"],
                    "sodium_mg": db_result["sodium_mg"], "source": "국가표준식품성분표",
                })
            else:
                nutr_resp = await llm.ainvoke(NUTRITION_LLM_PROMPT.format_messages(
                    food_name=meal["food_name"], quantity_g=meal["quantity_g"]
                ))
                nutrition = json.loads(re.sub(r"```json|```", "", nutr_resp.content).strip())
                meal.update({**nutrition, "source": "LLM 추정"})
            recalculated.append(meal)

        display = _format_modified_display(recalculated, plan_date, new_plan["message"])
        print(f"=== [confirm] 수정 재제안: {len(recalculated)}개 ===")
        return {
            "response":              display,
            "agent_used":            "confirm",
            "pending_meals":         recalculated,
            "awaiting_confirmation": True,  # supervisor가 다음 요청도 confirm으로 라우팅
        }

    # ── cancel ───────────────────────────────────────────────────────
    else:
        return {
            "response":              "식단 제안을 취소했습니다. 언제든지 다시 요청해주세요.",
            "agent_used":            "confirm",
            "pending_meals":         None,
            "awaiting_confirmation": False,
        }
