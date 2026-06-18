from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from app.schemas.models import AgentState
from app.core.config import get_settings
import json, re

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0,
                 openai_api_key=get_settings().openai_api_key)

EDIT_PARSE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """사용자가 기록된 식단을 수정하려고 합니다.
수정 내용을 파악해서 JSON으로 반환하세요.

[오늘 기록된 식단]:
{today_meals}

아래 JSON으로만 응답하세요:
{{
  "action": "update|delete",
  "meal_type": "breakfast|lunch|dinner|snack",
  "food_name": "수정할 음식명 (기존 기록에서 찾아서)",
  "new_quantity_g": 숫자 또는 null (삭제시 null),
  "new_food_name": "새 음식명 또는 null (음식명 변경시)",
  "reason": "수정 내용 한 문장 설명"
}}
JSON 외 텍스트 금지."""),
    ("human", "{message}")
])

NUTRITION_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """다음 음식의 영양성분을 JSON으로만 응답하세요.
{{"calories": 숫자, "protein_g": 숫자, "carbs_g": 숫자, "fat_g": 숫자}}
한국 식품영양성분 기준으로 추정하세요. JSON 외 텍스트 금지."""),
    ("human", "{food_name} {quantity_g}g")
])


def _resolve_target_date(message: str, today) -> str:
    """메시지의 상대 날짜 표현을 해석. 명시 없으면 오늘."""
    from datetime import timedelta
    msg = message or ""
    if any(k in msg for k in ["그저께", "그그제", "그제"]):
        return (today - timedelta(days=2)).isoformat()
    if "어제" in msg:
        return (today - timedelta(days=1)).isoformat()
    return today.isoformat()


async def edit_node(state: AgentState) -> AgentState:
    from app.db.supabase_client import get_supabase
    from datetime import date
    sb = get_supabase()
    user_id = state["user_id"]
    message = state["message"]

    # 메시지의 상대 날짜("어제"/"그제") 해석 후 해당 날짜 식단 조회
    target_date = _resolve_target_date(message, date.today())
    rows = sb.table("meal_logs").select("*").eq(
        "user_id", user_id).eq("log_date", target_date).execute().data

    if not rows:
        return {
            **state,
            "response": f"{target_date}에 기록된 식단이 없습니다.",
            "agent_used": "edit",
        }

    today_meals_text = "\n".join([
        f"- [{r['meal_type']}] {r['food_name']} {r['quantity_g']}g "
        f"(id: {r['id']})"
        for r in rows
    ])

    # 수정 내용 파악
    edit_resp = await llm.ainvoke(EDIT_PARSE_PROMPT.format_messages(
        today_meals=today_meals_text,
        message=message
    ))
    raw = re.sub(r"```json|```", "", edit_resp.content).strip()
    edit_info = json.loads(raw)

    # 수정할 항목 찾기
    target_row = None
    for row in rows:
        if (row["meal_type"] == edit_info.get("meal_type") and
                edit_info.get("food_name", "").lower() in row["food_name"].lower()):
            target_row = row
            break

    if not target_row:
        return {
            **state,
            "response": f"'{edit_info.get('food_name')}' 기록을 찾지 못했습니다. 오늘 기록된 식단을 확인해주세요.",
            "agent_used": "edit",
        }

    if edit_info["action"] == "delete":
        sb.table("meal_logs").delete().eq("id", target_row["id"]).execute()
        response = f"✅ {target_row['meal_type']} {target_row['food_name']} 기록을 삭제했습니다."

    else:  # update
        new_quantity = edit_info.get("new_quantity_g", target_row["quantity_g"])
        new_food_name = edit_info.get("new_food_name") or target_row["food_name"]

        # 새 영양성분 계산
        nutr_resp = await llm.ainvoke(NUTRITION_PROMPT.format_messages(
            food_name=new_food_name,
            quantity_g=new_quantity
        ))
        nutr_raw = re.sub(r"```json|```", "", nutr_resp.content).strip()
        nutrition = json.loads(nutr_raw)

        sb.table("meal_logs").update({
            "food_name": new_food_name,
            "quantity_g": float(new_quantity),
            "calories": float(nutrition["calories"]),
            "protein_g": float(nutrition["protein_g"]),
            "carbs_g": float(nutrition["carbs_g"]),
            "fat_g": float(nutrition["fat_g"]),
        }).eq("id", target_row["id"]).execute()

        response = (
            f"✅ 수정 완료!\n"
            f"{target_row['meal_type']} {new_food_name} "
            f"{new_quantity}g → {nutrition['calories']}kcal / 단백질 {nutrition['protein_g']}g"
        )

    return {
        **state,
        "response": response,
        "agent_used": "edit",
    }
