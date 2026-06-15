from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from app.schemas.models import AgentState, extract_messages_context
from app.core.config import get_settings

llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0,
    openai_api_key=get_settings().openai_api_key
)

SUPERVISOR_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """당신은 식단 AI Agent의 Supervisor입니다.
사용자의 현재 메시지와 직전 대화 맥락을 함께 분석해서 의도를 파악하세요.

[직전 대화 맥락]:
{recent_context}

[현재 확인 대기 중인 식단 제안]:
{pending_info}

아래 7가지 중 하나로만 응답하세요:

- diet_logger: 먹은 음식을 기록하려는 의도
  판단 기준: 음식명이 포함되거나, 이전 대화에서 언급된 음식을 기록하려는 경우
  맥락 예시: 직전에 "저녁 연어 쌀밥"을 말했고 "그거로 기록해줘" → diet_logger
  맥락 예시: "위에서 말한대로", "아까 말한 저녁", "그거 기록" → diet_logger

- strategy: 식단 조언/추천을 원하는 의도
  판단 기준: 앞으로 먹을 것에 대한 조언, 칼로리 문의, 식단 전략 요청

- meal_plan: 하루 전체 식단 계획을 원하는 의도
  판단 기준: 하루치 식단을 짜달라는 요청

- confirm: 현재 제안된 식단을 확정/수정/취소하는 의도
  판단 기준: 현재 확인 대기 중인 식단이 있고, 그에 대한 승인/수정/거절 의사
  주의: 확인 대기 중인 식단이 없으면 confirm이 아님
  맥락 예시: 식단 제안을 받은 직후 "응", "확정", "ok", "기록" → confirm
  맥락 예시: 식단 제안을 받은 직후 "점심을 치킨으로 바꿔줘" → confirm (수정)

- edit: 이미 캘린더에 저장된 식단을 수정/삭제하는 의도
  판단 기준: "아까 기록한", "저장된", "기록된" 같은 표현과 함께 수정/삭제 요청

- inbody: 인바디 관련 의도

- reporter: 주간/월간 식단 리포트를 원하는 의도

반드시 위 7개 단어 중 하나만 출력. 다른 텍스트 금지."""),
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


def _heuristic_intent(message: str, has_pending: bool) -> str | None:
    """명확한 사용자 요청은 LLM 분류 전에 안전하게 라우팅한다."""
    msg = (message or "").lower()

    # 1. pending 식단 확정/수정/취소 → confirm 최우선
    if has_pending and any(k in msg for k in ["응", "네", "확정", "저장", "취소", "아니", "수정", "바꿔", "변경"]):
        return "confirm"

    # 2. 인바디/리포트/피드백 — 명시적 전용 신호
    if any(k in msg for k in ["인바디", "체성분", "골격근", "체지방"]):
        return "inbody"

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

    # 5. 하루 전체 식단 계획 → meal_plan
    if any(k in msg for k in ["식단 짜", "식단짜", "식단 계획", "식단 추천", "하루 식단", "meal plan", "플랜"]):
        return "meal_plan"

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
        print(f"=== [supervisor] 휴리스틱 라우팅: {heuristic} | message='{state.get('message','')}' ===")
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
                       "meal_plan", "confirm", "edit"]:
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

