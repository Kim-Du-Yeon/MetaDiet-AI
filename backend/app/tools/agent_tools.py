"""
Agent Tool 모음
각 Tool은 단일 책임 원칙으로 분리.
diet_logger, confirm, edit 등 각 Agent가 필요한 Tool만 호출.
하드코딩 없이 LLM이 상황에 맞게 판단.
"""
from datetime import date, timedelta
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from app.db.supabase_client import get_supabase
from app.rag.retriever import search_nutrition_knowledge
from app.core.config import get_settings
import json, re

sb = get_supabase()


# ── Tool 1: 오늘 식단 조회 ──────────────────────────────────────────
@tool
async def get_today_meals_tool(user_id: str) -> dict:
    """오늘 확정 저장된 식단 전체 조회"""
    try:
        rows = sb.table("meal_logs").select("*").eq(
            "user_id", user_id
        ).eq("log_date", date.today().isoformat()).execute().data

        logged_meal_types = list(set(r["meal_type"] for r in rows))
        today_meals = [{
            "meal_type": r["meal_type"],
            "food_name": r["food_name"],
            "quantity_g": r["quantity_g"],
            "calories": r["calories"],
            "protein_g": r["protein_g"],
            "carbs_g": r.get("carbs_g", 0),
            "fat_g": r.get("fat_g", 0),
            "sodium_mg": r.get("sodium_mg", 0),
        } for r in rows]

        return {
            "logged_meal_types": logged_meal_types,
            "today_meals": today_meals,
            "total_calories": round(sum(r["calories"] for r in rows), 1),
            "total_protein": round(sum(r["protein_g"] for r in rows), 1),
        }
    except Exception as e:
        print(f"=== get_today_meals_tool 오류: {e} ===")
        return {"logged_meal_types": [], "today_meals": [], "total_calories": 0, "total_protein": 0}


# ── Tool 2: 식단 저장 ────────────────────────────────────────────────
@tool
async def save_meal_tool(
    user_id: str,
    log_date: str,
    meal_type: str,
    food_name: str,
    quantity_g: float,
    calories: float,
    protein_g: float,
    carbs_g: float,
    fat_g: float,
    sodium_mg: float,
) -> dict:
    """확정된 식단을 DB에 저장"""
    try:
        sb.table("meal_logs").insert({
            "user_id": user_id,
            "log_date": log_date,
            "meal_type": meal_type,
            "food_name": food_name,
            "quantity_g": float(quantity_g),
            "calories": float(calories),
            "protein_g": float(protein_g),
            "carbs_g": float(carbs_g),
            "fat_g": float(fat_g),
            "sodium_mg": float(sodium_mg),
        }).execute()
        return {"success": True, "food_name": food_name}
    except Exception as e:
        print(f"=== save_meal_tool 오류: {e} ===")
        return {"success": False, "error": str(e)}


# ── Tool 3: 식단 수정 ────────────────────────────────────────────────
@tool
async def update_meal_tool(
    meal_id: str,
    user_id: str,
    quantity_g: float,
    calories: float,
    protein_g: float,
    carbs_g: float,
    fat_g: float,
    sodium_mg: float,
) -> dict:
    """기존 식단 기록 수정"""
    try:
        sb.table("meal_logs").update({
            "quantity_g": float(quantity_g),
            "calories": float(calories),
            "protein_g": float(protein_g),
            "carbs_g": float(carbs_g),
            "fat_g": float(fat_g),
            "sodium_mg": float(sodium_mg),
        }).eq("id", meal_id).eq("user_id", user_id).execute()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Tool 4: 식단 삭제 ────────────────────────────────────────────────
@tool
async def delete_meal_tool(meal_id: str, user_id: str) -> dict:
    """식단 기록 삭제"""
    try:
        sb.table("meal_logs").delete().eq(
            "id", meal_id
        ).eq("user_id", user_id).execute()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Tool 5: 누락 끼니 감지 ──────────────────────────────────────────
@tool
async def check_missing_meals_tool(
    logged_meals: list,
    pending_meals: list,
    just_recorded: list,
) -> dict:
    """
    오늘 식단 흐름에서 누락된 끼니 감지.
    확정 저장된 끼니 + 현재 pending 끼니를 합산해서 판단.
    LLM이 흐름 기반으로 판단 (시간 하드코딩 없음).
    """
    llm = ChatOpenAI(
        model="gpt-4o",
        temperature=0,
        openai_api_key=get_settings().openai_api_key
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", """당신은 사용자의 하루 식단 흐름을 파악하는 AI입니다.

[오늘 확정 저장된 끼니]: {logged_meals}
[현재 대기 중인 끼니]: {pending_meals}
[방금 기록하려는 끼니]: {just_recorded}

판단 기준:
- 사람마다 식사 패턴이 다릅니다. 시간이 아닌 흐름으로 판단하세요.
- 방금 기록하려는 끼니 기준으로 그 이전에 빠진 끼니가 있으면 누락
- 방금 기록하려는 끼니 이후는 아직 안 먹었을 수 있으니 누락 아님
- 예시: 아침 기록 후 저녁 기록(방금) → 점심 누락
- 예시: 점심 기록 후 저녁 기록(방금) → 아침 누락
- 예시: 저녁 기록 후 아침 기록(방금) → 누락 아님 (다음날일 수 있음)
- 사용자가 의도적으로 건너뛴다고 언급했으면 누락 아님
- 방금 기록한 끼니가 비어있던 끼니를 채우는 경우 누락 아님
- 누락된 끼니가 여러 개일 수 있습니다.

아래 JSON으로만 응답하세요:
{{
  "has_missing": true/false,
  "missing_meals": ["아침", "점심"] 또는 [],
  "reason": "판단 이유 한 문장"
}}
JSON 외 텍스트 금지."""),
        ("human", "오늘 식단 흐름에서 누락된 끼니가 있는지 판단해주세요.")
    ])

    try:
        resp = await llm.ainvoke(prompt.format_messages(
            logged_meals=logged_meals if logged_meals else "없음",
            pending_meals=pending_meals if pending_meals else "없음",
            just_recorded=just_recorded if just_recorded else "없음",
        ))
        raw = re.sub(r"```json|```", "", resp.content).strip()
        return json.loads(raw)
    except Exception as e:
        print(f"=== check_missing_meals_tool 오류: {e} ===")
        return {"has_missing": False, "missing_meals": [], "reason": "판단 실패"}


# ── Tool 6: RAG 영양 지식 검색 ──────────────────────────────────────
@tool
async def rag_nutrition_tool(query: str) -> str:
    """
    Pinecone에서 영양학 논문/가이드라인 검색.
    출처(문서명, 페이지) 포함해서 반환.
    """
    try:
        docs = await search_nutrition_knowledge(query)
        if not docs:
            return "관련 영양학 근거를 찾지 못했습니다."

        results = []
        for d in docs[:3]:
            source = d.metadata.get('source_file', d.metadata.get('source', 'Unknown'))
            page = d.metadata.get('page', 'N/A')
            results.append(
                f"[출처: {source}, 페이지: {page}]\n{d.page_content}"
            )
        return "\n\n".join(results)
    except Exception as e:
        return f"RAG 검색 실패: {e}"


# ── Tool 7: 현재 전략 조회 ──────────────────────────────────────────
@tool
async def get_active_strategy_tool(user_id: str) -> dict:
    """현재 활성 식단 전략 조회"""
    try:
        rows = sb.table("diet_strategies").select("*").eq(
            "user_id", user_id
        ).eq("is_active", True).order("created_at", desc=True).limit(1).execute().data
        return rows[0] if rows else {}
    except Exception as e:
        print(f"=== get_active_strategy_tool 오류: {e} ===")
        return {}


# ── Tool 8: 전략 업데이트 ───────────────────────────────────────────
@tool
async def update_strategy_tool(
    user_id: str,
    daily_calories: float,
    protein_g: float,
    carbs_g: float,
    fat_g: float,
    strategy_note: str,
    triggered_by: str,
    inbody_log_id: str = None,
) -> dict:
    """식단 전략 업데이트 (기존 비활성화 후 새 전략 저장)"""
    try:
        sb.table("diet_strategies").update(
            {"is_active": False}
        ).eq("user_id", user_id).eq("is_active", True).execute()

        sb.table("diet_strategies").insert({
            "user_id": user_id,
            "daily_calories": daily_calories,
            "protein_g": protein_g,
            "carbs_g": carbs_g,
            "fat_g": fat_g,
            "strategy_note": strategy_note,
            "triggered_by": triggered_by,
            "inbody_log_id": inbody_log_id,
            "is_active": True,
        }).execute()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Tool 9: 어제 요약 ───────────────────────────────────────────────
@tool
async def get_yesterday_summary_tool(user_id: str) -> dict:
    """어제 식단 요약 조회 (오늘 전략 조정 근거)"""
    from app.tools.analytics import get_yesterday_summary
    return await get_yesterday_summary(user_id)


# ── Tool 10: 인바디 이력 조회 ───────────────────────────────────────
@tool
async def get_inbody_history_tool(user_id: str, limit: int = 3) -> list:
    """최근 인바디 기록 조회"""
    try:
        rows = sb.table("inbody_logs").select("*").eq(
            "user_id", user_id
        ).order("measured_date", desc=True).limit(limit).execute().data
        return rows
    except Exception as e:
        return []