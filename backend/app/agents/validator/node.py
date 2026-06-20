"""
validator/node.py

역할: meal_plan Agent가 생성한 식단 제안을 독립적으로 검증.
      단순 규칙 검사가 아닌, LLM + RAG가 영양학적 관점에서 판단.

순환 루프 흐름:
  meal_plan → validator
    ├── 통과(passed=True)  → confirm → (사용자 확인) → save_chat → END
    └── 실패(passed=False) → meal_plan (피드백 반영 재생성, 최대 MAX_ATTEMPTS회)

검증 기준 (하드코딩 없이 LLM이 RAG 근거로 판단):
  - 칼로리가 사용자 목표 대비 지나치게 낮거나 높은지
  - 단백질이 체중/목표 기준으로 충분한지
  - 탄수화물·지방 비율이 균형 잡혔는지
  - 특정 영양소가 극단적으로 편중됐는지
  - 식사 구성이 실현 가능한지(끼니 수, 음식 다양성)
"""
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from app.schemas.models import AgentState
from app.core.config import get_settings
from app.rag.region_guidance import get_region_guidance
import json, re

# 최대 재생성 시도 횟수 - 무한 루프 방지
MAX_ATTEMPTS = 3

llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0,
    openai_api_key=get_settings().openai_api_key
)

VALIDATOR_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """당신은 독립적인 영양학 전문 검증 AI입니다.
다른 AI가 생성한 식단 제안을 영양학적 관점에서 엄격하게 검증하세요.

[사용자 정보]
- 목표: {goal}
- 하루 칼로리 목표: {target_cal}kcal
- 하루 단백질 목표: {target_protein}g
- 오늘까지 섭취: {today_cal}kcal / 단백질 {today_protein}g

[검증 대상 식단]
- 날짜: {plan_date}
- 총 칼로리: {total_cal}kcal
- 총 단백질: {total_protein}g
- 총 탄수화물: {total_carbs}g
- 총 지방: {total_fat}g
- 구성:
{meal_details}

[RAG 영양학 근거]
{rag_context}

[지역 기준 우선순위]
{region_guidance}

[현재 시도 횟수]: {attempts}회 / 최대 {max_attempts}회

검증 기준 (RAG 근거로 판단, 수치 하드코딩 금지):
1. 칼로리: 목표 대비 ±20% 이내인지, 다이어트 목표라면 적절한 적자인지
2. 단백질: RAG 근거에 따른 권장량(체중×계수)과 비교해 충분한지
3. 영양 균형: 탄수화물·단백질·지방 비율이 RAG 권장 범위인지
4. 실현 가능성: 끼니 구성이 실제로 먹을 수 있는 수준인지
5. 목표 적합성: 사용자 목표(다이어트/근육증량/유지)에 부합하는지

아래 JSON으로만 응답하세요:
{{
  "passed": true/false,
  "score": 0~100,
  "issues": ["문제점1", "문제점2"] 또는 [],
  "feedback": "재생성 시 반영해야 할 구체적 수정 지시사항 (passed=false일 때만 작성, 수치 포함)",
  "reasoning": "판단 근거 요약 (RAG 출처 포함, 2~3문장)"
}}
JSON 외 텍스트 금지."""),
    ("human", "위 식단을 검증해주세요.")
])


def _format_meal_details(meals: list) -> str:
    """pending_meals 리스트를 검증용 텍스트로 변환"""
    if not meals:
        return "  (식단 없음)"
    lines = []
    meal_labels = {
        "breakfast": "아침",
        "lunch": "점심",
        "dinner": "저녁",
        "snack": "간식"
    }
    for m in meals:
        label = meal_labels.get(m.get("meal_type", ""), m.get("meal_type", ""))
        lines.append(
            f"  [{label}] {m['food_name']} {m['quantity_g']}g — "
            f"{round(m['calories'])}kcal / "
            f"단백질 {round(m['protein_g'])}g / "
            f"탄수화물 {round(m.get('carbs_g', 0))}g / "
            f"지방 {round(m.get('fat_g', 0))}g"
        )
    return "\n".join(lines)


async def validator_node(state: AgentState) -> dict:
    """
    meal_plan이 생성한 pending_meals를 LLM + RAG로 검증.

    반환:
      - validation_passed: True → 통과, False → 재생성 필요
      - validation_attempts: 누적 시도 횟수
      - validation_feedback: 실패 시 재생성에 반영할 구체적 피드백
      - can_improve: False이면 MAX_ATTEMPTS 도달로 강제 통과 처리
    """
    pending_meals = state.get("pending_meals") or []
    attempts = (state.get("validation_attempts") or 0) + 1

    print(f"=== [validator] 검증 시작 (시도 {attempts}/{MAX_ATTEMPTS}) ===")

    # pending_meals가 없으면 즉시 통과 (diet_logger confirm 등 다른 경로)
    if not pending_meals:
        print("=== [validator] pending_meals 없음 → 즉시 통과 ===")
        return {
            "validation_passed": True,
            "validation_attempts": attempts,
            "validation_feedback": "",
            "can_improve": False,
        }

    # 최대 시도 횟수 초과 → 강제 통과 (무한 루프 방지)
    if attempts > MAX_ATTEMPTS:
        print(f"=== [validator] 최대 시도 횟수({MAX_ATTEMPTS}) 초과 → 강제 통과 ===")
        return {
            "validation_passed": True,
            "validation_attempts": attempts,
            "validation_feedback": "",
            "can_improve": False,
        }

    # 영양 합계 계산
    total_cal = round(sum(m["calories"] for m in pending_meals))
    total_protein = round(sum(m["protein_g"] for m in pending_meals))
    total_carbs = round(sum(m.get("carbs_g", 0) for m in pending_meals))
    total_fat = round(sum(m.get("fat_g", 0) for m in pending_meals))

    # RAG: meal_plan이 이미 검색해 state에 캐싱한 근거를 재사용.
    # → 동일 페이지 중복 검색 + 쿼리생성 LLM 호출 제거(토큰 절감).
    #   같은 영양학 근거로 검증해야 plan과 평가 기준이 일치(일관성)한다.
    #   캐시가 없을 때(다른 경로 진입)만 직접 검색하는 폴백 유지.
    rag_context = state.get("rag_context")
    if rag_context:
        print("=== [validator] RAG 캐시 재사용 → 재검색 생략 ===")
    else:
        try:
            from app.rag.retriever import retrieve
            query_resp = await llm.ainvoke(
                f"""아래 식단 검증 상황에서 영양학 기준 확인에 가장 적합한 영어 검색 쿼리를 1줄로만 생성하세요.
사용자 목표: {state.get('user_goal', 'diet')}
목표 칼로리: {state.get('target_calories', 2000)}kcal
제안 칼로리: {total_cal}kcal
제안 단백질: {total_protein}g
검증 초점: calorie adequacy protein requirements nutritional balance {state.get('user_goal', 'weight loss')}
영어 쿼리만 출력, 다른 텍스트 금지."""
            )
            rag_query = query_resp.content.strip()
            result = await retrieve(rag_query)
            rag_context = result["context"] or "관련 영양학 근거 없음 — 추측하지 말 것"
            print(f"=== [validator] RAG: query='{rag_query}' grounded={result['grounded']} score={result['max_score']} ===")
        except Exception as e:
            print(f"=== [validator] RAG 실패: {e} ===")
            rag_context = "영양 지식베이스 준비 중"

    # LLM 검증 실행
    resp = await llm.ainvoke(VALIDATOR_PROMPT.format_messages(
        goal=state.get("user_goal", "다이어트"),
        target_cal=state.get("target_calories", 2000),
        target_protein=state.get("target_protein", 130),
        today_cal=round(state.get("today_calories", 0)),
        today_protein=round(state.get("today_protein", 0)),
        plan_date=state.get("plan_date", ""),
        total_cal=total_cal,
        total_protein=total_protein,
        total_carbs=total_carbs,
        total_fat=total_fat,
        meal_details=_format_meal_details(pending_meals),
        rag_context=rag_context,
        region_guidance=get_region_guidance(state.get("user_region")),
        attempts=attempts,
        max_attempts=MAX_ATTEMPTS,
    ))

    raw = re.sub(r"```json|```", "", resp.content).strip()
    result = json.loads(raw)

    passed = result.get("passed", True)
    score = result.get("score", 100)
    issues = result.get("issues", [])
    feedback = result.get("feedback", "")
    reasoning = result.get("reasoning", "")

    print(f"=== [validator] 결과: {'✅ 통과' if passed else '❌ 실패'} (점수: {score}) ===")
    if issues:
        print(f"=== [validator] 문제점: {issues} ===")
    if feedback:
        print(f"=== [validator] 피드백: {feedback[:100]}... ===")
    print(f"=== [validator] 근거: {reasoning} ===")

    # can_improve: 아직 재시도 여유가 있는지
    can_improve = (not passed) and (attempts < MAX_ATTEMPTS)

    return {
        "validation_passed": passed,
        "validation_attempts": attempts,
        "validation_feedback": feedback if not passed else "",
        "can_improve": can_improve,
    }


def route_after_validator(state: AgentState) -> str:
    """
    validator 결과에 따른 라우팅 함수.
    graph.py의 add_conditional_edges에서 사용.

    반환값:
      "meal_plan" → 실패 + 재시도 가능 → meal_plan으로 루프백
      "confirm"  → 통과 또는 최대 시도 초과 → 사용자 확인 후 저장
    """
    passed = state.get("validation_passed", True)
    can_improve = state.get("can_improve", False)

    if not passed and can_improve:
        attempts = state.get("validation_attempts", 0)
        print(f"=== [validator→route] 재생성 → meal_plan (시도 {attempts}/{MAX_ATTEMPTS}) ===")
        return "meal_plan"

    print(f"=== [validator→route] 통과 → confirm ===")
    return "confirm"
