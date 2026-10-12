from pydantic import BaseModel
from typing import Optional, List
from typing_extensions import TypedDict, Annotated
from langgraph.graph.message import add_messages
from app.schemas.proposals import ProposalDecision


def merge_pending_meals(existing, new):
    if new is None:
        return None
    return new


def keep_latest(existing, new):
    return new


def keep_max(existing, new):
    if existing is None:
        return new
    if new is None:
        return existing
    return max(existing, new)


class ChatRequest(BaseModel):
    message: str
    user_id: str
    thread_id: str = "default"
    pending_meals: Optional[list] = None
    awaiting_confirmation: bool = False
    plan_date: Optional[str] = None
    messages: list = []


class ResumeRequest(BaseModel):
    thread_id: str
    message: str
    decision: Optional[ProposalDecision] = None
    stream_run_id: Optional[str] = None
    after_seq: int = 0


class InbodyUploadResponse(BaseModel):
    measured_date: str
    weight_kg: float
    skeletal_muscle_kg: float
    body_fat_kg: float
    body_fat_pct: float
    bmi: Optional[float]
    bmr_kcal: Optional[float]
    strategy_updated: bool
    strategy_note: Optional[str]
    proposal: Optional[dict] = None


class MealLogResponse(BaseModel):
    id: str
    log_date: str
    meal_type: str
    food_name: str
    quantity_g: float
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float


class DailyNutritionSummary(BaseModel):
    date: str
    total_calories: float
    total_protein: float
    total_carbs: float
    total_fat: float
    target_calories: float
    target_protein: float
    remaining_calories: float
    remaining_protein: float
    meals: List[MealLogResponse]


class AgentState(TypedDict):
    user_id:   str
    user_goal: str
    thread_id: Annotated[str, keep_latest]
    run_id: Annotated[str, keep_latest]
    trace_id: Annotated[Optional[str], keep_latest]
    requested_action: Annotated[Optional[str], keep_latest]
    tool_policy: Annotated[Optional[list], keep_latest]
    pending_proposal: Annotated[Optional[dict], keep_latest]
    proposal_decision: Annotated[Optional[dict], keep_latest]
    proposal_result: Annotated[Optional[dict], keep_latest]
    execution_usage: Annotated[dict, keep_latest]
    execution_status: Annotated[str, keep_latest]
    execution_error: Annotated[Optional[str], keep_latest]
    agent_events: Annotated[list, keep_latest]
    food_selection: Annotated[Optional[dict], keep_latest]

    # ── message에 keep_latest 리듀서 추가 ────────────────────────────
    # 이유: /chat/resume에서 aupdate_state({"message": resume_msg})로
    #       사용자 응답을 state에 주입할 때, 리듀서가 없으면
    #       "Can receive only one value per step" 오류 발생.
    #       keep_latest를 붙이면 같은 스텝 내 덮어쓰기 허용.
    message: Annotated[str, keep_latest]
    intent:  str

    messages: Annotated[list, add_messages]

    today_date:      Annotated[str, keep_latest]
    today_calories:  Annotated[float, keep_latest]
    today_protein:   Annotated[float, keep_latest]
    today_carbs:     Annotated[float, keep_latest]
    today_fat:       Annotated[float, keep_latest]

    target_calories: Annotated[float, keep_latest]
    target_protein:  Annotated[float, keep_latest]
    target_carbs:    Annotated[float, keep_latest]
    target_fat:      Annotated[float, keep_latest]
    strategy_note:   Annotated[str, keep_latest]

    latest_inbody:     Annotated[Optional[dict], keep_latest]
    days_since_inbody: Annotated[int, keep_latest]

    response:   Annotated[str, keep_latest]
    agent_used: Annotated[str, keep_latest]

    pending_meals:         Annotated[Optional[list], merge_pending_meals]
    awaiting_confirmation: Annotated[bool, keep_latest]
    plan_date:             Annotated[Optional[str], keep_latest]
    overwrite_on_confirm:  Annotated[Optional[bool], keep_latest]

    # 사용자가 버튼으로 고른 끼니(아침/점심/저녁/간식). 있으면 diet_logger가
    # LLM 추측 대신 이 값을 강제 적용 → 끼니 오분류 방지(끼니는 사용자 사실).
    forced_meal_type:      Annotated[Optional[str], keep_latest]

    # 장기 목표(Goal Manager Agent). load_state가 users 테이블에서 채움.
    target_weight_kg:      Annotated[Optional[float], keep_latest]
    target_date:           Annotated[Optional[str], keep_latest]
    goal_priority:          Annotated[Optional[str], keep_latest]

    # 지역 기반 영양 기준 우선순위("KR"|"INTL"). load_state가 users.region에서 채움.
    user_region:            Annotated[str, keep_latest]

    # RAG 캐시: 그래프 1회 실행당 검색 1번만 하고 재사용.
    #   meal_plan이 채우면 validator·재생성 루프가 재사용 → 동일 페이지 중복
    #   검색 제거 + 쿼리생성 LLM 호출 절감(토큰). grounded는 RAG 근거 여부 추적.
    rag_context:  Annotated[Optional[str], keep_latest]
    rag_grounded: Annotated[Optional[bool], keep_latest]

    # 검증 루프
    validation_attempts:  Annotated[Optional[int], keep_latest]
    validation_passed:    Annotated[Optional[bool], keep_latest]
    validation_feedback:  Annotated[Optional[str], keep_latest]
    can_improve:          Annotated[Optional[bool], keep_latest]


def extract_messages_context(messages: list, n: int = 10) -> str:
    if not messages:
        return "없음"
    lines = []
    for m in messages[-n:]:
        if hasattr(m, 'type') and hasattr(m, 'content'):
            role    = "assistant" if m.type == "ai" else "user"
            content = str(m.content)[:200]
        elif isinstance(m, dict):
            role    = m.get("role", "")
            content = str(m.get("content", ""))[:200]
        else:
            continue
        lines.append(f"{role}: {content}")
    return "\n".join(lines) if lines else "없음"
