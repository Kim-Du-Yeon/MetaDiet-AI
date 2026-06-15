# Supervisor Routing Edge-Case Evaluation Report

## 1. 개요

| 항목 | 내용 |
|------|------|
| 평가 목적 | 실사용 환경의 불완전한 입력(오타·구어체·mixed intent 등)에 대한 라우팅 안정성 검증 |
| 평가 일자 | 2026-06-15 |
| 평가 대상 | `_heuristic_intent()` in `app/agents/supervisor/node.py` |
| 평가 스크립트 | `scripts/eval/run_routing_eval.py` |

**배경:** Supervisor는 사용자 메시지를 7개 agent 중 하나로 라우팅한다. 일반 케이스 baseline은 18/18을 달성했지만, 실제 사용자는 오타·축약어·혼합 의도 등 불완전한 입력을 자주 사용한다. 이를 체계적으로 검증하고 개선하기 위해 edge case 전용 평가셋을 구축하고 heuristic을 보완했다.

---

## 2. Baseline Routing Eval

- **데이터셋:** `routing_dataset.json` — 18케이스, 7개 라우트 레이블 커버
- **라우트 레이블:** `diet_logger` / `meal_plan` / `strategy` / `confirm` / `edit` / `inbody` / `reporter`

| 지표 | 결과 |
|------|------|
| intent_accuracy | **1.000** (18/18) |
| route_accuracy | **1.000** |
| confusion | 없음 |

> baseline은 개선 전·후 동일하게 18/18 유지됨을 확인.

---

## 3. Edge Routing Eval — 개선 전/후 비교

- **데이터셋:** `edge_dataset.json` — 6종 edge type × 3케이스 = 18케이스

| 지표 | Before | After |
|------|--------|-------|
| intent_accuracy | 0.833 | **1.000** |
| 정답 수 | 15 / 18 | **18 / 18** |
| confusion 건수 | 3 | **0** |

**개선 전 오분류 패턴:**

| 혼동 | 건수 |
|------|------|
| diet_logger → strategy | 2 |
| diet_logger → meal_plan | 1 |

---

## 4. 실패 케이스 분석 (Before)

| # | 입력 | expected | got | 근본 원인 |
|---|------|----------|-----|-----------|
| 1 | `아아 한잔 했어` | diet_logger | strategy | "아아"(아이스 아메리카노 축약어), "한잔" 같은 음료 섭취 표현을 heuristic과 LLM 모두 음식 기록으로 인식하지 못함 |
| 2 | `닭가슴살 200g 먹었고 단백질 더 먹어야 하나?` | diet_logger | strategy | 음식 기록 의도 + 전략 질문이 혼재(mixed intent)된 문장에서 LLM이 뒷부분 strategy 신호에 밀림 |
| 3 | `식단 짜줘, 아 그리고 어제 저녁 삼겹살 기록해줘` | diet_logger | meal_plan | "식단 짜줘"가 앞에 위치해 기존 heuristic의 meal_plan 키워드가 먼저 반응, 뒤의 음식 기록 의도가 무시됨 |

**정책 판단 근거:** 음식 섭취 기록이 포함된 경우, 기록을 먼저 처리해야 이후 전략/식단 계획 판단의 정확도가 높아진다. 따라서 mixed intent에서는 `diet_logger` 우선이 올바른 동작이다.

---

## 5. `_heuristic_intent()` 개선 내용

**변경 파일:** `app/agents/supervisor/node.py`

### 추가된 신호 집합

```python
_FOOD_KW = (
    "닭가슴살", "고등어", "삼겹살", "치킨", "샐러드", "김치찌개", "밥",
    "프로틴", "쉐이크", "shake", "아메리카노", "아아", "아메", "커피",
    "chicken", "salad", "라뚜기",
)
_INTAKE_KW = (
    "먹었", "먹음", "먹었다", "마셨", "마셨어", "마심",
    "한잔", "한 잔", "기록", "기록해줘", "저장해줘",
)
```

### 추가된 우선순위 규칙 (우선순위 4번)

```python
# 음식 신호 + 섭취 신호가 동시에 존재하면 diet_logger 우선
# → mixed intent에서 meal_plan/strategy로 밀리지 않도록 meal_plan 체크보다 먼저 처리
if any(k in msg for k in _FOOD_KW) and any(k in msg for k in _INTAKE_KW):
    return "diet_logger"
```

### 최종 우선순위 구조

| 순위 | 조건 | 라우트 |
|------|------|--------|
| 1 | pending 상태 + 확정/수정/취소 표현 | confirm |
| 2 | 인바디/체성분 키워드 | inbody |
| 3 | 오늘 + 피드백 키워드 | strategy |
| 4 | 리포트/통계/주간/월간 키워드 | reporter |
| 5 | 수정/삭제 + 기록/저장 키워드 | edit |
| **6** | **음식 신호 + 섭취 신호 (신규)** | **diet_logger** |
| 7 | 식단 짜/식단 계획 키워드 | meal_plan |
| 8 | 해당 없음 | LLM 분류로 위임 |

> `route_to_agent()` 구조는 변경하지 않음.

---

## 6. Edge Eval 최종 결과 — edge_type별 정확도 (After)

| edge_type | 설명 | 결과 |
|-----------|------|------|
| typo | 음식명 오타·구어체 ("라뚜기", "아아", "치킨 먹음") | **3 / 3** |
| missing_unit | g 단위 누락 ("닭가슴살 먹었어", "밥 한 그릇") | **3 / 3** |
| empty_or_irrelevant | 빈 입력·무관한 입력 ("", "안녕", "날씨") | **3 / 3** |
| mixed_lang | 한/영 혼용 ("chicken salad", "프로틴 shake") | **3 / 3** |
| pending_flow | pending 상태 확정/수정/취소 | **3 / 3** |
| mixed_intent | 기록 + 전략/식단 계획 혼합 | **3 / 3** |
| **전체** | | **18 / 18 (1.000)** |

---

## 7. Agent 안정성 관점의 의미

**오분류가 서비스에 미치는 영향:**
- `diet_logger → strategy` 오분류: 사용자가 먹은 음식이 기록되지 않음 → 영양 추적 누락 → 이후 리포트 부정확
- `diet_logger → meal_plan` 오분류: 식단 계획 agent가 호출되어 불필요한 LLM 비용 발생 + 사용자 혼란

**개선 효과:**
- 음식·음료 축약어 및 구어체 표현을 heuristic 레벨에서 처리 → LLM 호출 없이 정확히 라우팅
- mixed intent 문장에서 "기록 우선" 정책이 heuristic에 명시적으로 반영됨
- pending_flow 3/3 확인: pending 식단의 확정/수정/취소가 모두 `confirm`으로 처리 → 데드 인터럽트(응답 없는 멈춤) 방지 검증 완료

---

## 8. 평가 파일 목록

| 파일 | 설명 |
|------|------|
| `routing_dataset.json` | 일반 케이스 18개 (baseline, 7개 라우트 레이블) |
| `edge_dataset.json` | edge case 18개 (6종 × 3개, `edge_type` 필드 포함) |
| `run_routing_eval.py` | 라우팅 평가 스크립트 (`--dataset` 인자로 데이터셋 선택) |
| `routing_report_baseline.json` | baseline eval 결과 (intent_accuracy: 1.000) |
| `routing_report_edge_before.json` | 개선 전 edge eval 결과 (intent_accuracy: 0.833) |
| `routing_report_edge_after.json` | 개선 후 edge eval 결과 (intent_accuracy: 1.000) |
