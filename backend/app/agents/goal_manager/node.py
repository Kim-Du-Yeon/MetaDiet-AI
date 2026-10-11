"""
goal_manager/node.py

역할: target_weight_kg/target_date/goal_priority 대비 진행 상황(달성률·속도·근손실 위험)을
      점검하고 칼로리/단백질 조정을 "권고"한다. confirm 패턴이 아니라 단순 텍스트 응답이며,
      DB에 자동 적용하지 않는다.

트리거:
  1) 채팅 intent "goal_manager" (supervisor 라우팅)
  2) inbody 노드 완료 후 자동 체이닝(graph.py: inbody → goal_manager → save_chat).
     이 경우 inbody의 response를 덮어쓰지 않고 이어붙인다.
"""
from datetime import date
from app.core.llm import get_chat_model
from langchain_core.prompts import ChatPromptTemplate
from app.schemas.models import AgentState
from app.core.config import get_settings
from app.tools.agent_tools import get_inbody_history_tool
from app.db.supabase_client import get_supabase
from app.rag.region_guidance import get_region_guidance
from app.core.service_clock import service_today
import json, re

llm = get_chat_model(temperature=0.2)
sb = get_supabase()

GOAL_MANAGER_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """당신은 장기 목표 기반 식단 코칭 전문가입니다.
목표 대비 진행 상황과 영양학 근거를 종합해서 전략 조정을 권고하세요.

[사용자 목표 방향]: {user_goal}
[목표]: 목표 체중 {target_weight_kg}kg / 목표 날짜 {target_date} / 우선순위 {goal_priority}
[시작 체중]: {start_weight}kg → [현재 체중]: {current_weight}kg
[진행률]: {progress_pct}% (남은 {remaining_weight}kg, 음수면 목표 초과 달성)
[최근 골격근 변화]: {muscle_change}kg ({muscle_change_note})
[현재 속도]: 주당 {weekly_rate}kg ({weekly_rate_note})
[목표 달성 필요 속도]: 주당 {needed_weekly_rate}kg ({needed_rate_note})
[현재 전략]: 칼로리 {target_calories}kcal / 단백질 {target_protein}g

[RAG 영양학 근거]:
{rag_context}

[지역 기준 우선순위]:
{region_guidance}

당신의 역할:
- goal_priority가 "speed"면 속도를, "muscle"이면 근손실 방지를, "balance"면 둘의 균형을 우선하세요
- 현재 속도와 필요 속도를 비교해서 목표 기한 내 달성 가능한지(on_track) 판단하세요
- 골격근 변화가 우려되면 근손실 위험을 반드시 언급하세요
- RAG 근거 영역에 "현재 문서 기반 근거는 부족합니다"가 있으면 출처 기반 설명을 만들지 말고 수치 기반 권고만 하세요
- 칼로리/단백질 조정은 "권고"이며 자동 적용되지 않는다는 점을 message에 명시하세요

아래 JSON으로만 응답하세요:
{{
  "on_track": true/false,
  "muscle_risk": "low|medium|high",
  "recommended_calories": 숫자,
  "recommended_protein": 숫자,
  "message": "사용자에게 보여줄 설명(근거 포함, 3~5문장)"
}}
JSON 외 텍스트 금지."""),
    ("human", "목표 진행 상황을 점검해주세요.")
])


def _append(state: AgentState, text: str) -> str:
    """inbody 체이닝 시 직전 response를 덮어쓰지 않고 이어붙인다."""
    prev = (state.get("response") or "").strip()
    return f"{prev}\n\n{text}".strip() if prev else text


def _calc_goal_progress(current_weight: float, target_weight: float, start_weight: float) -> dict:
    """시작→현재→목표 체중으로 달성률(%)과 남은 체중(kg)을 계산. target==start면 100%로 간주."""
    total_needed = start_weight - target_weight
    progressed   = start_weight - current_weight
    progress_pct = round(progressed / total_needed * 100, 1) if total_needed else 100.0
    remaining_weight = round(current_weight - target_weight, 2)
    return {"progress_pct": progress_pct, "remaining_weight": remaining_weight}


def _calc_weekly_rate(current_weight: float, current_date: str, prev_weight: float, prev_date: str):
    """최근 2개 인바디 기록 간 주당 체중 변화율(kg/주). 기간이 0일 이하면 None."""
    days_between = (date.fromisoformat(current_date) - date.fromisoformat(prev_date)).days
    if days_between <= 0:
        return None
    return round((current_weight - prev_weight) / days_between * 7, 2)


def _calc_needed_weekly_rate(remaining_weight: float, target_date_str: str, today: date = None):
    """목표일까지 남은 기간 기준, 목표 달성에 필요한 주당 변화율(kg/주). 기한이 지났으면 None."""
    today = today or service_today()
    days_remaining = (date.fromisoformat(target_date_str) - today).days
    if not days_remaining or days_remaining <= 0:
        return None
    return round(remaining_weight / (days_remaining / 7), 2)


async def goal_manager_node(state: AgentState) -> dict:
    user_id = state["user_id"]
    target_weight_kg = state.get("target_weight_kg")
    target_date_str  = state.get("target_date")
    goal_priority     = state.get("goal_priority") or "balance"

    if target_weight_kg is None or not target_date_str:
        return {
            "response": _append(state, "🎯 아직 목표 체중·기간이 설정되지 않았어요. 목표를 먼저 설정해주세요."),
            "agent_used": "goal_manager",
        }

    history = await get_inbody_history_tool.ainvoke({"user_id": user_id, "limit": 10})
    if not history:
        return {
            "response": _append(state, "🎯 인바디 기록이 없어서 진행 상황을 계산할 수 없어요. 인바디를 먼저 업로드해주세요."),
            "agent_used": "goal_manager",
        }

    latest = history[0]
    current_weight = latest["weight_kg"]
    current_muscle = latest["skeletal_muscle_kg"]

    user_rows = sb.table("users").select("weight_kg").eq("id", user_id).limit(1).execute().data
    start_weight = (user_rows[0].get("weight_kg") if user_rows else None) or history[-1]["weight_kg"]

    progress = _calc_goal_progress(current_weight, target_weight_kg, start_weight)
    progress_pct = progress["progress_pct"]
    remaining_weight = progress["remaining_weight"]

    if len(history) >= 2:
        prev_log = history[1]
        weekly_rate = _calc_weekly_rate(
            current_weight, latest["measured_date"], prev_log["weight_kg"], prev_log["measured_date"]
        )
        muscle_change = round(current_muscle - prev_log["skeletal_muscle_kg"], 2)
    else:
        weekly_rate = None
        muscle_change = None

    needed_weekly_rate = _calc_needed_weekly_rate(remaining_weight, target_date_str)

    rag_query = (
        f"weight loss rate goal {goal_priority} muscle preservation calorie protein adjustment "
        f"target weight {target_weight_kg}kg remaining {remaining_weight}kg {state.get('user_goal','diet')}"
    )
    try:
        from app.rag.retriever import retrieve
        rag_result = await retrieve(rag_query, k=4, max_docs=3)
        rag_grounded = bool(rag_result.get("grounded") and rag_result.get("context"))
        rag_context = rag_result["context"] if rag_grounded else (
            "현재 문서 기반 근거는 부족합니다. "
            "출처 기반 설명은 만들지 말고, 수치 기반의 일반적 권고만 하세요."
        )
        print(f"=== goal_manager RAG: grounded={rag_grounded} score={rag_result.get('max_score')} ===")
    except Exception as e:
        print(f"=== goal_manager RAG 실패: {e} ===")
        rag_context = (
            "현재 문서 기반 근거는 부족합니다. "
            "출처 기반 설명은 만들지 말고, 수치 기반의 일반적 권고만 하세요."
        )
        rag_grounded = False

    resp = await llm.ainvoke(GOAL_MANAGER_PROMPT.format_messages(
        user_goal=state.get("user_goal", "diet"),
        target_weight_kg=target_weight_kg, target_date=target_date_str, goal_priority=goal_priority,
        start_weight=start_weight, current_weight=current_weight,
        progress_pct=progress_pct, remaining_weight=remaining_weight,
        muscle_change=muscle_change if muscle_change is not None else "측정 불가",
        muscle_change_note="최근 2회 인바디 비교" if muscle_change is not None else "인바디 기록 1회뿐",
        weekly_rate=weekly_rate if weekly_rate is not None else "측정 불가",
        weekly_rate_note="최근 기록 구간 기준" if weekly_rate is not None else "인바디 기록 1회뿐",
        needed_weekly_rate=needed_weekly_rate if needed_weekly_rate is not None else "계산 불가",
        needed_rate_note="목표일까지 남은 기간 기준" if needed_weekly_rate is not None else "목표 날짜가 지났거나 오늘",
        target_calories=state.get("target_calories", 2000), target_protein=state.get("target_protein", 130),
        rag_context=rag_context,
        region_guidance=get_region_guidance(state.get("user_region")),
    ))

    raw = re.sub(r"```json|```", "", resp.content).strip()
    result = json.loads(raw)

    text = (
        f"🎯 **목표 진행 점검**\n"
        f"목표 체중 {target_weight_kg}kg까지 {progress_pct}% 진행 "
        f"(현재 {current_weight}kg, 남은 {abs(remaining_weight)}kg)\n"
        f"{result['message']}\n\n"
        f"💡 권고: 하루 {result['recommended_calories']}kcal / 단백질 {result['recommended_protein']}g "
        f"(자동 적용되지 않았어요. 적용을 원하시면 말씀해주세요)"
    )

    return {
        "response": _append(state, text),
        "agent_used": "goal_manager",
        "rag_grounded": rag_grounded,
    }
