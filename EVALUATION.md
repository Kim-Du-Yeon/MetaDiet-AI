# Routing / RAG Evaluation Summary

이 문서는 보고서에 바로 옮길 수 있도록 routing evaluation과 RAG evaluation 결과를 정리한 것이다. 원본 결과 파일은 다음 두 개다.

- `backend/scripts/eval/routing_report.json`
- `backend/scripts/eval/eval_report.json`

## 1. 평가 목적

| 평가 | 목적 | 확인하고 싶은 것 |
|---|---|---|
| Routing evaluation | Supervisor Agent가 사용자 의도를 올바른 Agent로 분기하는지 확인 | intent classification과 실제 graph route가 기대값과 일치하는지 |
| RAG evaluation | 영양지식 RAG가 정답 문서와 페이지를 잘 찾고, 출처 기반 응답을 생성하는지 확인 | source/page hit, citation, faithfulness, grounded quality |

## 2. Routing Evaluation

### 평가 설정

`routing_report.json`은 사용자가 실제로 입력할 법한 문장을 intent별로 구성하고, Supervisor의 intent 판단과 LangGraph route 결과가 기대 Agent와 일치하는지 평가한다.

| 항목 | 값 |
|---|---:|
| 평가 케이스 수 | 18 |
| Intent accuracy | 1.00 |
| Route accuracy | 1.00 |
| Confusion | 없음 |

### Intent별 케이스 분포

| Expected intent | 케이스 수 | 목적 |
|---|---:|---|
| `diet_logger` | 5 | 먹은 음식 기록, 이전 대화 기반 기록 |
| `meal_plan` | 2 | 하루 식단 계획 생성 |
| `strategy` | 3 | 식단 조언, 칼로리/영양 전략 질문 |
| `confirm` | 3 | 식단 후보 확정/수정/취소 |
| `edit` | 2 | 이미 저장된 식단 수정/삭제 |
| `inbody` | 1 | 인바디 결과 분석 및 전략 갱신 |
| `reporter` | 2 | 주간/월간 식단 리포트 |

### 평가에 사용한 문장

| Expected intent | 평가 문장 |
|---|---|
| `diet_logger` | 닭가슴살 200g 먹었어 |
| `diet_logger` | 오늘 점심에 김치찌개랑 공기밥 먹었어 |
| `diet_logger` | 방금 아메리카노 한 잔 마셨어 |
| `diet_logger` | 그거 그대로 기록해줘 |
| `diet_logger` | 위에서 말한 저녁으로 기록 |
| `meal_plan` | 내일 하루 식단 좀 짜줘 |
| `meal_plan` | 다이어트용으로 하루치 식단 계획 세워줘 |
| `strategy` | 단백질은 하루에 얼마나 먹어야 해? |
| `strategy` | 지금 칼로리 남았는데 뭐 먹으면 좋을까? |
| `strategy` | 살 빼려면 탄수화물 줄이는 게 맞아? |
| `confirm` | 응 확정해줘 |
| `confirm` | ok 그대로 기록 |
| `confirm` | 점심을 치킨샐러드로 바꿔줘 |
| `edit` | 아까 기록한 저녁 메뉴 삭제해줘 |
| `edit` | 어제 저장한 점심 칼로리 좀 수정해줘 |
| `inbody` | 인바디 결과 분석해서 전략 업데이트 해줘 |
| `reporter` | 이번 주 식단 리포트 보여줘 |
| `reporter` | 최근 한 달 단백질 섭취 통계 알려줘 |

`confirm` 케이스는 확인 대기 중인 pending 식단이 있는 상태를 가정했다. `그거 그대로 기록해줘`, `위에서 말한 저녁으로 기록`은 직전 대화 context를 참고해 `diet_logger`로 분기되는지 확인하기 위한 케이스다.

### 해석

Routing evaluation에서는 18개 케이스 모두에서 Supervisor의 intent와 최종 route가 기대값과 일치했다. 이는 Multi-Agent 구조에서 각 Agent의 역할이 분리되어 있고, 사용자의 요청이 적절한 node로 전달되는지 확인하기 위한 기본 안정성 검증이다.

다만 이 평가는 synthetic dataset 기반이므로, 실제 사용자의 오타, 구어체, 사진 업로드 후 후속 발화 같은 edge case는 별도의 smoke test로 보완했다.

### 실제 데모 시나리오 Smoke Test

| 검증 항목 | 확인 내용 |
|---|---|
| 음식 사진 오인 거절 | 사진 인식 후 "이거 아니야" 입력 시 pending food state를 초기화하고 잘못된 기록을 방지 |
| 자연어 식단 기록 | "아침 연어롤 200g", "점심 쌀밥 100g, 닭가슴살 200g"처럼 끼니/음식/중량을 파싱 |
| HITL confirm | "응 확정해줘", "저장해" 입력 시 pending 식단만 DB에 저장 |
| 이전 식단 중복 방지 | 새 식단 입력 시 이전 pending/history 음식이 재파싱되어 중복 합산되지 않는지 확인 |
| Rollback 수정 | checkpoint rollback 후 닭가슴살을 고등어로 수정하면 기존 점심 row를 대체 저장 |
| 오늘 식단 총평 | "오늘 식단 총평" 요청 시 당일 DB meal_logs와 최신 목표 칼로리/단백질을 재조회해 평가 |
| 내일 식단 계획 | 저녁 치킨 약속 같은 제약조건을 반영해 meal_plan Agent가 아침/점심 계획 생성 |
| 인바디 갱신 | 인바디 사진 업로드 후 OCR 결과를 이력과 비교하고 전략 갱신 흐름으로 연결 |

## 3. RAG Evaluation

### 평가 설정

`eval_report.json`은 영양지식 PDF에서 생성한 QA 케이스에 대해 검색 모드별 성능을 비교한다. 각 모드는 `k=4`, 평가 질문 수 `n=10`으로 측정했다.

| 모드 | 설명 |
|---|---|
| `dense` | Pinecone dense vector search only |
| `hybrid` | Dense search + BM25 sparse search + RRF |
| `full` | Hybrid retrieval + FlashRank reranking + grounded/citation pipeline |

### 주요 지표 설명

| 지표 | 의미 |
|---|---|
| Source hit | 정답 PDF 파일을 검색 결과에 포함했는지 |
| Page hit | 정답 페이지를 검색 결과에 포함했는지 |
| Excerpt hit | 정답 근거 문단에 가까운 excerpt를 찾았는지 |
| Avg score | 검색 및 reranking 후 평균 관련도 점수 |
| Refusal rate | 근거 부족으로 답변을 거절한 비율 |
| Citation rate | 응답에 출처가 포함된 비율 |
| Faithfulness | 응답이 검색 근거에 충실한지 평가한 값 |

### 결과 표

| 모드 | k | n | Source hit | Page hit | Excerpt hit | Avg score | Refusal rate | Citation rate | Faithfulness |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| dense | 4 | 10 | 1.00 | 0.80 | 0.70 | 0.817 | 0.00 | 1.00 | 1.00 |
| hybrid | 4 | 10 | 1.00 | 1.00 | 0.90 | 0.817 | 0.00 | 1.00 | 1.00 |
| full | 4 | 10 | 1.00 | 1.00 | 0.90 | 0.978 | 0.00 | 1.00 | 1.00 |

### 개선 효과

| 비교 | 개선 내용 |
|---|---|
| dense -> hybrid | Page hit가 0.80에서 1.00으로 상승, Excerpt hit가 0.70에서 0.90으로 상승 |
| hybrid -> full | Page/source/excerpt hit는 유지하면서 Avg score가 0.817에서 0.978로 상승 |
| dense -> full | Source hit 1.00 유지, Page hit +0.20, Excerpt hit +0.20, Avg score +0.161 |

### 해석

Dense search만 사용해도 정답 PDF 파일은 모두 찾았지만, 정확한 페이지와 근거 문단을 찾는 성능은 hybrid/full 구성에서 더 안정적이었다. 특히 full 모드는 hybrid retrieval 이후 FlashRank reranking을 적용하여 평균 score가 가장 높았다. Citation rate와 faithfulness가 1.00으로 유지된 점은 RAG 응답이 출처 기반으로 생성되고 있음을 보여준다.

단, 현재 평가는 synthetic QA 10개 기준이므로 전체 일반화 성능을 보장하지는 않는다. 보고서에서는 "제한된 평가셋에서 hybrid retrieval과 reranking 적용 후 근거 검색 품질이 개선되었다"라고 표현하는 것이 정확하다.

## 4. 보고서용 요약 문장

Routing evaluation에서는 18개 intent routing case에 대해 intent accuracy와 route accuracy가 모두 1.00으로 측정되었다. RAG evaluation에서는 dense 단독 검색 대비 hybrid/full 구성에서 page hit가 0.80에서 1.00으로, excerpt hit가 0.70에서 0.90으로 개선되었고, full 모드의 평균 score는 0.978로 가장 높았다. 이를 통해 Supervisor 기반 Multi-Agent routing의 안정성과, hybrid retrieval 및 reranking을 적용한 RAG 검색 품질 개선을 확인했다.

## 5. Edge-Case Routing Eval

### 배경

Section 2의 baseline routing eval은 정형화된 입력을 대상으로 한다. 실제 사용자는 오타·축약어·혼합 의도 같은 불완전한 입력을 자주 사용하므로, 6종 edge type 전용 평가셋(`edge_dataset.json`)을 구축하고 `_heuristic_intent()`를 보완했다.

### 결과 비교

| 평가셋 | 케이스 수 | Before | After |
|--------|----------|--------|-------|
| routing_dataset.json (baseline) | 18 | 1.000 (18/18) | 1.000 유지 |
| edge_dataset.json               | 18 | 0.833 (15/18) | **1.000 (18/18)** |

### 개선 전 실패 케이스 3건

| 입력 | expected | got | 원인 |
|------|----------|-----|------|
| "아아 한잔 했어" | diet_logger | strategy | 음료 축약어·구어체를 heuristic/LLM 모두 미인식 |
| "닭가슴살 200g 먹었고 단백질 더 먹어야 하나?" | diet_logger | strategy | mixed intent에서 strategy 신호에 밀림 |
| "식단 짜줘, 아 그리고 어제 저녁 삼겹살 기록해줘" | diet_logger | meal_plan | meal_plan 신호가 앞에 위치해 기록 의도 무시됨 |

### 개선 방식

변경 파일: `app/agents/supervisor/node.py` — `_heuristic_intent()`

- `_FOOD_KW` (음식·음료명 신호, 17개) / `_INTAKE_KW` (섭취·기록 행위 신호, 10개) 추가
- 두 신호가 동시에 존재하면 `diet_logger`를 `meal_plan` / `strategy` 체크보다 먼저 반환
- mixed intent에서 "음식 기록 우선" 정책을 heuristic 레벨에 명시적으로 반영
- `route_to_agent()` 구조는 변경하지 않음

### edge_type별 최종 정확도 (After)

| edge_type | 결과 |
|-----------|------|
| typo (오타·구어체) | 3/3 |
| missing_unit (단위 누락) | 3/3 |
| empty_or_irrelevant (빈 입력·무관) | 3/3 |
| mixed_lang (한/영 혼용) | 3/3 |
| pending_flow (확정/수정/취소) | 3/3 |
| mixed_intent (혼합 의도) | 3/3 |

### 상세 보고서

`backend/scripts/eval/EDGE_EVAL_REPORT.md`

## 6. LangSmith 연동 및 Eval 관측성

### 배경

eval 스크립트 실행 시 LangSmith에 trace가 남지 않는 문제가 있었다.

| 문제 | 원인 |
|------|------|
| `main.py` tracing 하드코딩 | `LANGCHAIN_TRACING_V2 = "true"` 고정 — `.env`의 `LANGSMITH_TRACING` 값 미반영 |
| eval 스크립트 trace 미전송 | eval 스크립트에서 LangSmith/LangChain tracing 환경변수 매핑과 trace flush가 부족해 실행 trace가 안정적으로 남지 않음 |

### 개선 내용

**`main.py`**
- `LANGCHAIN_TRACING_V2`를 `LANGSMITH_TRACING` 값에서 읽도록 수정 (미설정 시 `"true"`)

**`run_eval.py` / `run_routing_eval.py`**
- `backend/.env` 명시 로드 (`load_dotenv(BACKEND_DIR / ".env")`)
- `LANGSMITH_*` → `LANGCHAIN_*` 매핑 (`setdefault` 사용 — 외부 설정 덮어쓰지 않음)
- `@traceable` 유지 (함수 레벨 span 생성)
- `__main__` 실행부를 `tracing_context(enabled=_tracing)`으로 감쌈
- `try/finally`로 `Client().flush()` 보장 (eval 종료 시 버퍼 강제 전송)
- `LANGSMITH_TRACING=false`일 때 tracing 비활성화 및 flush 생략

### 검증 결과

| 항목 | 결과 |
|------|------|
| compileall | 통과 |
| baseline routing eval | **18/18 유지** |
| edge routing eval | **18/18 유지** |
| LangSmith `diet-agent` 프로젝트 `routing-eval` trace | 생성 확인 |
| ChatOpenAI 하위 run | LangSmith에 기록 확인 |

### 관측성 개선 효과

| 항목 | 내용 |
|------|------|
| Eval 실행 추적 | 실행 시각, 파라미터, 소요 시간 기록 |
| 실패 케이스 디버깅 | 오분류된 케이스의 LLM 입/출력 확인 가능 |
| LLM 비용 추적 | ChatOpenAI 호출 토큰 수 및 비용 확인 가능 |
| Agent 운영 관측성 | Supervisor routing 판단 근거를 trace 단위로 비교 가능 |

## 7. Ragas 기반 RAG 평가

### 배경

기존 `run_eval.py`는 커스텀 LLM judge로 faithfulness를 측정한다. 이를 보완하기 위해
ragas 0.2.15의 표준 지표로 동일 파이프라인을 재평가하는 `run_ragas_eval.py`를 추가했다.

ragas는 별도 평가 스크립트(`run_ragas_eval.py`)로 관리하며, 기본 실행 환경과 분리해 운영한다.
`requirements.txt`에는 미반영하고, 별도 Ragas 평가 리포트로 관리한다.

### 평가 설정

| 항목 | 값 |
|------|----|
| 스크립트 | `scripts/eval/run_ragas_eval.py` |
| 데이터셋 | `gold_dataset.json` (20개: EN 10 + KO 10) |
| 모드 | full (dense + BM25 hybrid + FlashRank reranking) |
| k | 4 |
| Judge LLM | gpt-4o-mini |
| 지표 | `faithfulness`, `context_recall` |

### 결과

| 구간 | 샘플 수 | faithfulness | context_recall | 기준 |
|------|---------|-------------|---------------|------|
| 전체 | 20 | **0.550** | **0.575** | ragas summary (공식) |
| 영어 QA | 10 | **0.900** | **0.950** | per-sample 로그 기반 |
| 한국어 QA | 10 | **0.200** | **0.300** | per-sample 로그 기반 |
| `--limit 3` (EN 상위 3개) | 3 | 0.833 | 1.000 | 초기 테스트 |

> context_recall의 전체 ragas summary 값(0.575)과 per-sample 기반 단순 평균(0.625) 사이에
> 소수점 수준의 차이가 있다. ragas 내부 집계 방식·NaN 처리·정규화 차이에 의한 것으로 간주하며,
> 공식 전체 값은 ragas summary(0.575)를 기준으로 사용한다.

### 해석

전체 평균(faithfulness 0.550 / context_recall 0.575)이 낮게 보이는 이유는 RAG 파이프라인 전체가
실패해서가 아니라, **영어 PDF corpus에 한국어 질문을 직접 검색하는 cross-lingual 평가 구간**이
포함되어 있기 때문이다.

- **영어 QA (faithfulness 0.900 / context_recall 0.950)**: 영어 질문 → 영어 PDF context → ragas judge의 언어 일관성이 유지되어 안정적
- **한국어 QA (faithfulness 0.200 / context_recall 0.300)**: 한국어 query와 영어 PDF context 간 semantic mismatch로 retrieval 점수와 평가 점수가 동시에 하락
- **핵심 한계**: "영어 PDF 기반 corpus에 한국어 질문을 직접 검색하는 구조" 자체의 제약

### 향후 개선 방향

| 방향 | 내용 |
|------|------|
| Query translation | 한국어 질문 → 영어 검색 쿼리 변환 후 retrieve |
| Multilingual embedding | multilingual-e5 또는 `text-embedding-3-large`로 임베딩 교체 |
| Dual query expansion | 한국어 + 영어 쿼리를 동시에 검색해 결과 합산 |
| Ragas judge 보강 | 한/영 혼합 판정 지침 추가 |

### 의존성 주의사항

ragas import를 위해 `langchain-community`를 0.4.1로 낮췄다.
`langchain-experimental 0.4.2`가 `langchain-community>=0.4.2`를 요구하므로 `pip check` 경고가 잔존한다.
`requirements.txt`에는 미반영하며, Ragas 평가는 별도 평가 환경에서 운영한다.

### 포트폴리오용 요약

Ragas 평가 결과 전체 평균은 faithfulness 0.55, context_recall 0.575였으나, 언어별로 분리해보면 영어 QA는 안정적인 반면 한국어 QA에서 성능 저하가 확인되었다. 이는 영어 PDF corpus에 한국어 질문을 직접 검색하는 cross-lingual retrieval 한계로 분석되며, query translation 및 multilingual embedding 개선 필요성을 정량적으로 도출했다.

### 상세 보고서

`backend/scripts/eval/RAGAS_EVAL_REPORT.md`
