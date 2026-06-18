# Routing / RAG Evaluation Summary

이 문서는 보고서에 바로 옮길 수 있도록 routing evaluation과 RAG evaluation 결과를 정리한 것이다. 평가 결과 파일 목록:

- `routing_report.json`, `eval_report.json` — 초기 결과
- `routing_report_baseline.json`, `routing_report_edge_before.json`, `routing_report_edge_after.json` — edge eval 전후 비교
- `ragas_report_full.json`, `ragas_report_limit3.json` — Ragas 평가 결과

평가 입력 데이터셋(`*_dataset.json`)과 실행 결과 report(`*_report*.json`) 파일 분류는 Section 8 참고.

---

## 목적별 평가 데이터셋 구성 (Evaluation Datasets by Purpose)

평가 대상(routing / RAG 검색 품질 / Ragas 응답 품질)을 분리하여 각각 전용 데이터셋과 스크립트로 독립적으로 검증했다.
성능 수치는 서비스 전체 성능 보장이 아닌 핵심 시나리오 회귀 테스트 및 진단 목적이다.

| 데이터셋 | 분류 | 평가 목적 | gold/정답 기준 | 스크립트 | 주요 지표 | 결과 |
|---------|------|---------|-------------|---------|---------|------|
| `routing_dataset.json` | standard routing gold-labeled dataset | 정상 입력 → 올바른 Agent 라우팅 회귀 테스트 (7 Agent label 커버) | `expected` (Agent 이름) | `run_routing_eval.py` | intent_accuracy, route_accuracy | 18/18 **(1.000)** |
| `edge_dataset.json` | edge routing gold-labeled dataset | 오타·구어체·mixed intent 등 6종 취약 패턴 진단 | `expected` + `edge_type` | `run_routing_eval.py` | intent_accuracy | 15/18 → 18/18 **(1.000)** |
| `qa_dataset.json` | RAG ablation dataset | dense / hybrid / full 모드별 RAG 검색 품질 비교 (`gold_answer` 없음) | `gold_source`, `gold_page`, `gold_excerpt` | `run_eval.py` | source_hit, page_hit, excerpt_hit†, avg_score | full: 1.00 / 1.00 / 0.90 / **0.978** |
| `gold_dataset.json` | Ragas/cross-lingual RAG ground-truth dataset | Ragas 기반 응답 품질 측정 + EN/KO 성능 분리 분석 | `gold_answer` + `language` | `run_ragas_eval.py` | faithfulness, context_recall | EN: 0.900/0.950, KO: 0.200/0.300 |

> †`excerpt_hit`은 `run_eval.py`의 커스텀 문자열 매칭 지표로, Ragas의 `context_recall`과 개념은 유사하지만 측정 방식이 다르다.

**데이터셋 분리의 의미:**
- routing 평가의 gold 기준은 `expected` label(어떤 Agent로 가야 하는가). `gold_dataset.json`은 routing 평가와 무관하다.
- `qa_dataset.json`은 `gold_answer` 없이 RAG 검색 모드 비교만 하는 ablation 전용이다.
- `gold_dataset.json`은 `gold_answer` + `language` 필드가 있어야 Ragas context_recall 측정과 EN/KO 분리가 가능하다.
- edge-case 성능 개선(15/18 → 18/18)은 평가 기준(rubric) 변경이 아니라 `_heuristic_intent()` heuristic 우선순위 로직 수정이다.
- LangSmith는 eval 실행 trace 관측 도구이며, 성능 지표 계산은 Python eval 스크립트가 담당한다.

---

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

다만 이 평가는 정형화된 표현 기반이므로, 실제 사용자의 오타, 구어체, 사진 업로드 후 후속 발화 같은 edge case는 별도의 edge-case 평가셋(`edge_dataset.json`)으로 보완했다. (→ Section 5)

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

> 이 평가는 `qa_dataset.json`(EN QA 10개, `run_eval.py` 기본 데이터셋)을 기준으로 dense / hybrid / full 3모드를 비교한다.
> `source_hit`·`page_hit`·`excerpt_hit`은 `run_eval.py`의 커스텀 검색 지표이며, Ragas 지표가 아니다.
> `gold_dataset.json`(EN/KO bilingual QA 10쌍, 총 20개)은 `run_ragas_eval.py`(Ragas 기반 cross-lingual 분석) 전용이며 Section 7 참고.

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
| 전체(갱신 전, 2026-06 초) | 20 | 0.550 | 0.575 | ragas summary (공식) |
| 영어 QA(갱신 전) | 10 | 0.900 | 0.950 | per-sample 로그 기반 |
| 한국어 QA(갱신 전) | 10 | 0.200 | 0.300 | per-sample 로그 기반 |
| `--limit 3` (EN 상위 3개) | 3 | 0.833 | 1.000 | 초기 테스트 |

> context_recall의 전체 ragas summary 값(0.575)과 per-sample 기반 단순 평균(0.625) 사이에
> 소수점 수준의 차이가 있다. ragas 내부 집계 방식·NaN 처리·정규화 차이에 의한 것으로 간주하며,
> 공식 전체 값은 ragas summary(0.575)를 기준으로 사용한다.

> **2026-06-19 갱신** — query translation(한→영 쿼리 변환) + dual query expansion + 임베딩
> `text-embedding-3-large` 교체 적용 후 재측정:
>
> | 구간 | 샘플 수 | faithfulness | context_recall |
> |------|---------|-------------|---------------|
> | 전체 | 20 | **0.925** | **0.825** |
> | 영어 QA | 10 | **1.000** | **0.700**(↓0.250) |
> | 한국어 QA | 10 | **0.850**(↑0.650) | **0.950**(↑0.650) |
>
> 한국어는 cross-lingual gap이 거의 해소됨(오히려 이번 회차는 영어보다 recall이 높음). 영어
> context_recall은 소폭 하락(20개 중 3개 영향) — 임베딩 교체로 `chunks.pkl`이 재생성되며
> `SemanticChunker` 청크 경계 자체가 바뀐 영향으로 추정되나 미검증. 아래 "해석"·"포트폴리오용
> 요약" 단락은 갱신 전(한국어 성능 저하가 핵심 한계였던 시점) 분석이라 현재 상태와 다르다.
> 원본 리포트: `backend/scripts/eval/ragas_report.json`.

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

---

## 8. 평가 파일 분류

| 파일명 | 분류 | 목적 | 개수 | 근거 파일 |
|--------|------|------|------|----------|
| `routing_dataset.json` | routing gold-labeled dataset | 정상 입력 baseline 라우팅 정확도 검증 — `expected` label이 정답 기준 (회귀 테스트) | 18개 | [routing_dataset.json](backend/scripts/eval/routing_dataset.json) |
| `edge_dataset.json` | edge routing gold-labeled dataset | 실사용 취약 입력 패턴 라우팅 안정성 검증 — `expected` label + `edge_type`이 정답 기준 | 18개 | [edge_dataset.json](backend/scripts/eval/edge_dataset.json) |
| `qa_dataset.json` | RAG ablation dataset | `run_eval.py` 기본 데이터셋 — dense/hybrid/full 3모드 ablation용 EN QA 10개 (`excerpt_hit` 등 커스텀 지표 측정 — Ragas 지표 아님, gold_answer 없음) | 10개 | [qa_dataset.json](backend/scripts/eval/qa_dataset.json) |
| `gold_dataset.json` | Ragas/cross-lingual RAG ground-truth dataset | `run_ragas_eval.py` 기본 데이터셋 — EN/KO bilingual QA 10쌍, `gold_answer` + `language` 필드 포함, Ragas faithfulness/context_recall + cross-lingual retrieval 분석 전용 (routing 평가와 무관) | 20개 (EN 10 + KO 10, 10쌍) | [gold_dataset.json](backend/scripts/eval/gold_dataset.json) |
| `ragas_report_limit3.json` | Smoke/Limit test 결과 report | --limit 1 (동작 확인) + --limit 3 (샘플링 성능 확인) 사전 점검 | 실행 2회분 누적 | [ragas_report_limit3.json](backend/scripts/eval/ragas_report_limit3.json) |
| `ragas_report_full.json` | 평가 실행 결과 report | n=1, n=3, n=20 전체 Ragas 실행 결과 누적 | 실행 3회분 누적 | [ragas_report_full.json](backend/scripts/eval/ragas_report_full.json) |
| `routing_report_baseline.json` | 평가 실행 결과 report | standard 18케이스 baseline 결과 (18/18) | 1회 | [routing_report_baseline.json](backend/scripts/eval/routing_report_baseline.json) |
| `routing_report_edge_before.json` | 평가 실행 결과 report | 개선 전 edge 18케이스 결과 (15/18) | 1회 | [routing_report_edge_before.json](backend/scripts/eval/routing_report_edge_before.json) |
| `routing_report_edge_after.json` | 평가 실행 결과 report | 개선 후 edge 18케이스 결과 (18/18) | 1회 | [routing_report_edge_after.json](backend/scripts/eval/routing_report_edge_after.json) |
| `run_routing_eval.py` | 코드 파일 | supervisor_node 실호출 방식 routing 평가 러너 | — | [run_routing_eval.py](backend/scripts/eval/run_routing_eval.py) |
| `run_eval.py` | 코드 파일 | RAG QA 평가 러너 (커스텀 LLM judge, 6개 지표) | — | [run_eval.py](backend/scripts/eval/run_eval.py) |
| `run_ragas_eval.py` | 코드 파일 | Ragas 표준 지표 평가 러너 (faithfulness·context_recall) | — | [run_ragas_eval.py](backend/scripts/eval/run_ragas_eval.py) |
| `EDGE_EVAL_REPORT.md` | 문서화 파일 | edge-case 평가 분석·개선 내용 기록 | — | [EDGE_EVAL_REPORT.md](backend/scripts/eval/EDGE_EVAL_REPORT.md) |
| `RAGAS_EVAL_REPORT.md` | 문서화 파일 | Ragas 평가 설정·결과·해석·개선 방향 기록 | — | [RAGAS_EVAL_REPORT.md](backend/scripts/eval/RAGAS_EVAL_REPORT.md) |
| `EVALUATION.md` | 문서화 파일 | 전체 평가 체계 종합 문서 | — | [EVALUATION.md](EVALUATION.md) |
| `README.md` | 문서화 파일 | 프로젝트 개요 + 평가 수치 요약 | — | [README.md](README.md) |

> **데이터셋 vs 결과 report 구분**: `*_dataset.json`은 평가 입력 QA 케이스를 담은 파일이다.
> `*_report*.json`은 eval 스크립트 실행 후 저장된 결과 기록으로, 재현 가능한 실행 이력을 위해 커밋에 포함한다.
> 데이터셋 규모(routing 18개, edge 18개, qa 10개, gold 20개)는 대규모 일반화 성능 보장이 아니라
> 핵심 시나리오 회귀 테스트 및 취약 패턴 진단을 목적으로 구성되었다.
>
> **데이터셋-스크립트 대응**: `qa_dataset.json`은 `run_eval.py`(커스텀 지표: source_hit·page_hit·excerpt_hit·faithfulness 0/1) 전용,
> `gold_dataset.json`은 `run_ragas_eval.py`(Ragas 지표: faithfulness·context_recall) 전용으로 서로 다른 스크립트와 1:1로 대응한다.
> `excerpt_hit`은 `run_eval.py`의 커스텀 문자열 매칭 지표이며 Ragas 지표가 아니다.
>
> **평가 영역별 gold 역할 구분**: 이 프로젝트에서 "gold"는 평가 영역에 따라 형태가 다르다.
> routing 평가(`routing_dataset.json`, `edge_dataset.json`)는 `expected` label을 정답 기준으로 하는 routing gold-labeled dataset이고,
> RAG 평가(`qa_dataset.json`, `gold_dataset.json`)는 `gold_source`·`gold_page`·`gold_excerpt`를 정답 기준으로 하는 RAG ground-truth dataset이다.
> `gold_dataset.json`은 Ragas 표준 지표 및 EN/KO cross-lingual 분석 전용이며, routing 평가와는 무관하다.

---

## 기술적 판단 근거 (Technical Rationale)

### 1. Mixed Intent 라우팅 정책

음식 기록 의도와 전략 상담 의도가 혼재한 경우, 서비스 흐름상 먼저 기록을 해야 이후 단백질 부족 여부나
남은 칼로리 판단이 정확해진다. 그래서 음식명 신호와 섭취·기록 표현이 동시에 존재하면 `diet_logger`를
우선하는 log-first policy를 `_heuristic_intent()`에 반영했다.

명확한 패턴은 라우팅 휴리스틱으로 먼저 처리하고, 그 외 애매한 케이스는 LLM 판단으로 위임한다.
평가 기준(rubric)은 변경하지 않았으며, 동일한 `edge_dataset.json`과 `expected` label로
개선 전후를 비교했다.

| 입력 예시 | 포함된 의도 | 개선 전 | 개선 후 |
|-----------|------------|---------|---------|
| 아아 한잔 했어 | 음료 기록 | strategy | diet_logger |
| 닭가슴살 200g 먹었고 단백질 더 먹어야 하나? | 기록 + 전략 상담 | strategy | diet_logger |
| 식단 짜줘, 아 그리고 어제 저녁 삼겹살 기록해줘 | 식단 계획 + 기록 | meal_plan | diet_logger |

edge-case routing accuracy: 15/18(0.833) → 18/18(1.000). 상세: [EDGE_EVAL_REPORT.md](backend/scripts/eval/EDGE_EVAL_REPORT.md)

---

### 2. Dense + BM25 + RRF 융합 방식

| 방식 | 기준 | 장점 | 한계 |
|------|------|------|------|
| Dense retrieval | 임베딩 기반 의미 유사도 | 표현이 달라도 의미가 유사하면 검색 가능 | 정확한 키워드 매칭에 약함 |
| BM25 | 키워드 빈도·희귀도·문서 길이 | 정확한 단어·전문 용어 매칭에 강함 | 의미적으로 유사한 표현을 놓칠 수 있음 |

Dense는 cosine similarity 스케일, BM25는 문서 특성에 따라 점수 범위가 고정되지 않는다.
두 점수를 단순 합산하면 BM25 점수가 클 때 의미적으로 중요한 Dense 결과가 묻힐 수 있다.

| 방식 | 결합 기준 |
|------|---------|
| 단순 점수 합산 | Dense 점수 + BM25 점수 (스케일 불일치) |
| RRF | Dense 순위 + BM25 순위 (스케일 무관) |

RRF는 각 검색기에서 몇 위로 검색됐는지를 기준으로 결합하므로, 점수 스케일 차이 없이 두 방식의 장점을 안정적으로 융합한다.
dense 단독 → hybrid(dense+BM25+RRF) 전환으로 page_hit 0.80 → 1.00 개선.

---

### 3. Rerank Threshold 0.15

FlashRank reranker가 후보 문서에 관련성 점수를 부여한 뒤, 0.15 미만 문서는 답변 근거에서 제외한다.
관련성이 낮은 문서를 답변 생성에 포함하면 hallucination 위험이 커지기 때문이다.

0.15는 grid search로 찾은 절대 최적값이 아니라, FlashRank 점수 분포와 grounded generation 목적을 고려해
설정한 운영 기준값이다. full mode 평가에서 아래 결과가 안정적으로 확인되어 현재 값으로 유지했다.

| 지표 | 결과 |
|------|------|
| source_hit | 1.00 |
| page_hit | 1.00 |
| excerpt_hit (`run_eval.py` 커스텀 지표, Ragas 지표 아님) | 0.90 |
| avg_score | 0.978 |

config로 분리되어 있어 향후 데이터셋 확장 시 threshold ablation 실험이 가능하다.

---

### 4. Chunk Size 1,200자 / Overlap 150자

청킹은 문서를 검색 가능한 단위로 분할하는 과정으로, chunk size와 overlap은 검색 품질에 직접 영향을 준다.

| 극단 | 문제 |
|------|------|
| 너무 작음 | 근거 문맥이 끊겨 필요한 정보가 완전하게 들어오지 않음 |
| 너무 큼 | 단일 chunk에 여러 주제가 섞여 precision 저하 |

| 설정 | 설계 기준값 의미 |
|------|----------------|
| chunk size 1,200자 | 문맥을 충분히 보존하면서도 불필요한 주제가 섞이지 않도록 설정한 상한 |
| overlap 150자 | chunk 경계에서 중요한 근거 문장이 잘리는 것을 줄이기 위한 완충 구간 |

grid search로 찾은 최적값이 아니며, 문서 구조와 검색 품질 간 trade-off를 고려해 설정한 설계 기준값이다.
config로 관리되어 향후 재실험 가능하다.

---

### 5. Validator Loop 3회 제한 및 이관 구조

`meal_plan` Agent가 생성한 식단을 `validator` Agent가 영양 기준으로 검토하고,
부족한 조건을 feedback으로 AgentState에 저장해 다음 생성에 반영하는 루프 구조다.

흐름:

1. `meal_plan` → 식단 생성
2. `validator` → 영양 기준 충족 여부 검토
3. 부족 조건을 feedback으로 state에 저장
4. 다음 생성에서 feedback 반영 후 재생성
5. 최대 3회까지 반복
6. 3회 초과 시 자동 재생성 중단 → 사용자 확인 단계로 이관

3회는 LLM 기반 루프의 무한 반복 위험을 방지하기 위한 운영 기준값이다.
3회 초과 후 바로 거절하지 않으며, 사용자가 아래 중 하나를 선택하도록 한다.

| 선택 | 의미 |
|------|------|
| 확정 | 현재 식단을 그대로 사용 |
| 수정 | 사용자가 원하는 방향으로 수정 |
| 취소 | 식단 저장 취소 |

이 구조는 RAG에서 근거 부족 시 답변 생성을 제한하는 것과는 다른 레이어다.
LLM 기반 루프의 무한 반복 위험을 상한으로 방지하되, 최종 판단은 사용자에게 위임한다.

---

### 6. 전체 평가 흐름 요약

| 단계 | 내용 |
|------|------|
| 1 | 기능별 Agent 구현 + Supervisor routing 설계 |
| 2 | `routing_dataset.json`으로 baseline 18/18 확인 |
| 3 | `edge_dataset.json`으로 취약 입력 평가 → 15/18 발견 |
| 4 | 복합 의도 라우팅 정책 개선(rubric 변경 아님) → 18/18 달성 |
| 5 | Hybrid RAG 구축 (dense + BM25 + RRF + FlashRank) |
| 6 | `qa_dataset.json`으로 dense / hybrid / full 검색 품질 비교 |
| 7 | `gold_dataset.json`으로 Ragas EN/KO cross-lingual 분석 |
| 8 | LangSmith로 eval 실행 trace 관측성 확보 (지표 계산은 Python 스크립트 담당) |

## 9. 프로젝트 업그레이드 흐름

| 단계 | 문제/동기 | 조치 | 결과 수치 | 의미 |
|------|-----------|------|-----------|------|
| ① 기능 구현 | 식단 기록·상담·플랜·리포트 기능 필요 | FastAPI + 8 에이전트 구현, TypedDict AgentState 설계 | — | 기능 베이스 완성 |
| ② Multi-Agent 구조화 | 단일 LLM 흐름의 확장성 한계 | LangGraph StateGraph, HITL(interrupt_before), Postgres checkpointer 도입 | — | 멀티턴·상태 영속화 확보 |
| ③ 기본 routing 평가셋 구축 | 라우팅 정확도 측정 체계 부재 | `routing_dataset.json` 18개(standard routing gold-labeled dataset — `expected` label 기반, 7개 Agent label 커버) 구성 + `run_routing_eval.py` 작성 | **18/18 (1.0)** | 7개 에이전트 baseline 확인 |
| ④ Edge case 문제 발견 | 실사용 패턴(오타·혼합 의도)에서 오분류 | `edge_dataset.json` 18개(edge routing gold-labeled dataset — `expected` label + `edge_type` 기반, 6종 edge type) 구성 + 평가 실행 | **15/18 (0.833)** — 오분류 3건 확인 | 취약점 정량화 |
| ⑤ Heuristic 개선 | diet_logger→strategy 2건, diet_logger→meal_plan 1건 오분류 | `_FOOD_KW`·`_INTAKE_KW` 추가 + log-first policy | **18/18 (1.0)** | 취약점 해소 검증 — 평가 기준(rubric) 변경 아님, `_heuristic_intent()` heuristic 우선순위 로직 자체 수정 |
| ⑥ RAG 파이프라인 구축 | 단순 dense retrieval의 recall 한계 | SemanticChunker + BM25 + RRF + FlashRank 4단계 hybrid RAG | — | 다단계 검색 구조 확보 |
| ⑦ RAG 평가셋 구축 + 3모드 ablation | RAG 검색 품질 측정 체계 부재 | `qa_dataset.json` 10개(EN, RAG ablation dataset — gold_answer 없음) 구축 + `run_eval.py` dense/hybrid/full 3모드 비교 (커스텀 지표: source_hit·page_hit·**excerpt_hit** — Ragas 지표 아님) | **source_hit 1.0 / page_hit 1.0 / excerpt_hit 0.90** | dense < hybrid < full 개선 확인 |
| ⑧ LangSmith tracing 연동 | eval 실행 시 trace 미전송 | `tracing_context` + `Client().flush()` + 환경변수 매핑 적용 | trace 전송 확인 | eval 실행 trace 관측성 확보 (성능 지표 계산은 Python 스크립트 담당, LangSmith는 trace 관측 전용) |
| ⑨ Ragas 평가 + cross-lingual 분석 | 커스텀 judge 한계 (0/1 이진 판정) + KO 성능 의문 | `gold_dataset.json` 20개(Ragas/cross-lingual RAG ground-truth dataset — EN/KO bilingual, `gold_answer`+`language` 필드 포함) 구축 + `run_ragas_eval.py` → smoke(n=1) → limit(n=3) → full(n=20) | **EN 0.900/0.950 · KO 0.200/0.300** | cross-lingual retrieval 한계 정량 분리 |
| ⑩ 문서화 | 평가 체계 가시화 필요 | `EVALUATION.md`·`README`·`EDGE_EVAL_REPORT.md`·`RAGAS_EVAL_REPORT.md` 작성 | — | 재현 가능한 평가 기록 확보 |
