"""
Agent Tool 모음
각 Tool은 단일 책임 원칙으로 분리.
diet_logger, confirm, edit 등 각 Agent가 필요한 Tool만 호출.
하드코딩 없이 LLM이 상황에 맞게 판단.
"""
from datetime import date, timedelta
from langchain_core.tools import tool
from app.core.llm import get_chat_model
from langchain_core.prompts import ChatPromptTemplate
from app.db.supabase_client import get_supabase
from app.core.config import get_settings
from app.core.service_clock import service_today
import json, re

sb = get_supabase()


# ── Tool 1: 오늘 식단 조회 ──────────────────────────────────────────
@tool
async def get_today_meals_tool(user_id: str) -> dict:
    """오늘 확정 저장된 식단 전체 조회"""
    try:
        rows = sb.table("meal_logs").select("*").eq(
            "user_id", user_id
        ).eq("log_date", service_today().isoformat()).execute().data

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
    source: str = "llm_estimated",
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
            "source": source,
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
    방금 기록한 끼니보다 앞선 끼니만 누락으로 본다.
    """
    order = ["breakfast", "lunch", "dinner"]
    labels = {"breakfast": "아침", "lunch": "점심", "dinner": "저녁"}

    recorded = set(logged_meals or []) | set(pending_meals or []) | set(just_recorded or [])
    current = [m for m in (just_recorded or []) if m in order]
    if not current:
        return {"has_missing": False, "missing_meals": [], "reason": "간식 또는 끼니 정보 없음"}

    latest_idx = max(order.index(m) for m in current)
    missing = [m for m in order[:latest_idx] if m not in recorded]

    return {
        "has_missing": bool(missing),
        "missing_meals": [labels[m] for m in missing],
        "reason": "방금 기록한 끼니보다 앞선 끼니만 누락으로 판단",
    }


# ── Tool 6: RAG 영양 지식 검색 ──────────────────────────────────────
@tool
async def rag_nutrition_tool(query: str, user_region: str = "KR") -> str:
    """
    Pinecone에서 영양학 논문/가이드라인 검색.
    출처(문서명, 페이지) 포함해서 반환. 반환 텍스트 끝에 지역 기준 우선순위 가드레일을 덧붙인다.
    """
    try:
        from app.rag.retriever import retrieve
        from app.rag.region_guidance import get_region_guidance
        rag_result = await retrieve(query, k=4, max_docs=3)
        if not (rag_result.get("grounded") and rag_result.get("context")):
            return "관련 영양학 근거를 찾지 못했습니다."
        return f"{rag_result['context']}\n\n[지역 기준 우선순위] {get_region_guidance(user_region)}"
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
    """구형 직접 저장은 차단. 전략 제안·근거 검증·사용자 확정 경로를 사용하세요."""
    return {"success": False, "error": "proposal_approval_required"}


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
