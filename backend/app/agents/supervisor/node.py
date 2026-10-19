from app.core.llm import get_chat_model
from app.core.prompts import get_prompt
from langchain_core.prompts import ChatPromptTemplate
from app.schemas.models import AgentState, extract_messages_context
from app.core.config import get_settings

llm = get_chat_model(temperature=0, task='classification')

SUPERVISOR_PROMPT = ChatPromptTemplate.from_messages([
    ("system", get_prompt('legacy.intent_classification')),
    ("human", "{message}")
])


# 음식/음료 명칭 신호 — 섭취 신호와 함께 있으면 diet_logger 우선
_FOOD_KW = (
    "닭가슴살", "고등어", "삼겹살", "치킨", "샐러드", "김치찌개", "밥",
    "프로틴", "쉐이크", "shake", "아메리카노", "아아", "아메", "커피",
    "chicken", "salad", "라뚜기",
)
# 섭취/기록 행위 신호
_INTAKE_KW = (
    "먹었", "먹음", "먹었다", "마셨", "마셨어", "마심",
    "한잔", "한 잔", "기록", "기록해줘", "저장해줘",
)
# 과거 시점 신호 — mixed intent("어제 ~ 먹었어 + 오늘 식단 짜줘") 판별용
_PAST_KW = ("어제", "아까", "그제", "전에")
# 하루 전체 식단 계획 요청 신호 — diet_logger(mixed intent)와 meal_plan 라우팅이 공유
_PLAN_KW = ("식단 짜", "식단짜", "식단 계획", "식단 추천", "하루 식단", "meal plan", "플랜")


def _heuristic_intent(message: str, has_pending: bool) -> str | None:
    """명확한 사용자 요청은 LLM 분류 전에 안전하게 라우팅한다."""
    msg = (message or "").lower()

    # 1. pending 식단 확정/수정/취소 → confirm 최우선
    if has_pending and any(k in msg for k in ["응", "네", "확정", "저장", "취소", "아니", "수정", "바꿔", "변경"]):
        return "confirm"

    # 2. 인바디/리포트/피드백 — 명시적 전용 신호
    if any(k in msg for k in ["인바디", "체성분", "골격근", "체지방"]):
        return "inbody"

    if any(k in msg for k in ["목표 체중", "목표 달성", "목표까지", "목표 진행", "목표 기간", "목표 설정"]):
        return "goal_manager"

    if "오늘" in msg and any(k in msg for k in ["총평", "피드백", "평가", "잘한 점", "부족한 점", "개선 방향"]):
        return "strategy"

    if any(k in msg for k in ["리포트", "보고서", "통계", "패턴", "전달", "지난달", "이번 달", "이번달", "한달", "월간", "주간", "어땠"]):
        return "reporter"

    # 3. 저장된 기록의 수정/삭제 → edit
    if any(k in msg for k in ["수정", "삭제", "지워", "바꿔", "변경"]) and any(k in msg for k in ["기록", "식단", "아까", "먹은", "저장"]):
        return "edit"

    # 4. 음식 신호 + 섭취 신호 동시 존재 → diet_logger 우선
    #    mixed intent("먹었고 단백질 더 먹어야 하나?", "식단 짜줘, 아 삼겹살 기록해줘" 등)에서
    #    strategy/meal_plan으로 밀리지 않도록 meal_plan 체크보다 먼저 처리
    if any(k in msg for k in _FOOD_KW) and any(k in msg for k in _INTAKE_KW):
        return "diet_logger"

    # 4.5. mixed intent: 과거 식사 언급 + 오늘 식단 계획 요청이 함께 있으면
    #      diet_logger를 우선 처리(기록 누락 방지). 안내 문구는 diet_logger_node가 덧붙인다.
    if any(k in msg for k in _PAST_KW) and any(k in msg for k in _INTAKE_KW) \
            and any(k in msg for k in _PLAN_KW):
        return "diet_logger"

    # 5. 하루 전체 식단 계획 → meal_plan
    if any(k in msg for k in _PLAN_KW):
        return "meal_plan"

    # 6. 운동/헬스 언급만 있고 목표 진행 신호가 없으면 strategy로 안전 라우팅.
    #    goal_manager 도입 후 LLM이 "오늘 gym 다녀왔어" 같은 단순 운동 보고를 목표 점검으로
    #    과민 분류하는 회귀가 발견됨(edge_dataset.json) → 명확한 케이스는 LLM 이전에 차단.
    #    위 1~5에서 이미 안 걸렸으므로 다른 의도(식사 기록 등)와 섞인 문장은 영향 없음.
    if any(k in msg for k in ["운동", "헬스", "gym", "짐", "헬짐", "workout", "워크아웃"]) \
            and not any(k in msg for k in ["목표", "달성", "얼마나", "남았", "진행"]):
        return "strategy"

    return None


async def supervisor_node(state: AgentState) -> AgentState:
    # 헬퍼 함수로 Message 객체/dict 모두 처리
    recent_context = extract_messages_context(state.get("messages", []))

    pending = state.get("pending_meals") or []
    if pending:
        pending_info = f"있음 - {[m['meal_type'] + ' ' + m['food_name'] for m in pending]}"
    else:
        pending_info = "없음"

    heuristic = _heuristic_intent(state.get("message", ""), bool(pending))
    if heuristic:
        print(f"=== [supervisor] 휴리스틱 라우팅: {heuristic} | message_redacted ===")
        return {"intent": heuristic}

    response = await llm.ainvoke(
        SUPERVISOR_PROMPT.format_messages(
            message=state["message"],
            recent_context=recent_context,
            pending_info=pending_info,
        )
    )
    intent = response.content.strip().lower()

    if intent not in ["diet_logger", "strategy", "inbody", "reporter",
                       "meal_plan", "confirm", "edit", "goal_manager", "off_topic"]:
        intent = "strategy"

    return {"intent": intent}  # 리듀서 방식: 변경된 필드만 반환


def route_to_agent(state: AgentState) -> str:
    intent = state["intent"]
    pending = state.get("pending_meals")
    awaiting = state.get("awaiting_confirmation", False)
    heuristic = _heuristic_intent(state.get("message", ""), bool(pending))

    if heuristic:
        if heuristic == "confirm" and not pending:
            return "strategy"
        return heuristic

    # confirm은 '확인 대기 중인 식단(pending)'이 있을 때만 유효.
    # pending 없이 confirm으로 가면 interrupt_before에서 응답 없이 멈춤(데드 인터럽트).
    # 예: 사진 인식 후 "이거 아니야" → supervisor가 confirm으로 분류 → 멈춤.
    # → pending 없으면 strategy로 안전 전환(항상 응답 생성).
    if intent == "confirm" and not pending:
        return "strategy"

    if awaiting and pending and intent not in ["confirm", "edit", "diet_logger", "strategy"]:
        return "confirm"

    return intent

