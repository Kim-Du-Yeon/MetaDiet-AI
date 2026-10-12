# 2026-10-09 upgrade verification

Gemini-only migration regression: 135 passed, 1 optional parser test skipped.
Live Gemini Embedding 2 smoke test returned 3072 dimensions. Ragas now receives
both an explicit Gemini judge and Gemini embeddings; implicit provider defaults
are not used. Full corpus rebuild/activation and final Ragas scores remain
separate checks; historical OpenAI scores below are not Gemini results.

Current regression suite: 115 backend tests and 6 frontend tests passed. The
production model-led graph has additional delegation, policy, HITL and rollback
regressions. `scripts/check_agent_team.py` exercises live Gemini with synthetic
input and a memory repository. Local PostgreSQL checks are in
`scripts/check_proposal_transactions.py --local` and
`scripts/check_proposal_concurrency.py`; they require the disposable local test
database described in the scripts and do not establish remote deployment success.

Historical routing/Ragas numbers below belong to the baseline graph and corpus;
they are not evaluation scores for the new model-led team. Reviewed gold data,
agent trajectory evaluation and new LangSmith/Ragas experiments are still pending.
See [upgrade ledger](docs/UPGRADE_PROGRESS.md).

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

| 구간 | 샘플 수 | 시점 | faithfulness | context_recall |
|------|---------|------|-------------|---------------|
| 전체 | 20 | 개선 전 | 0.550 | 0.575 |
| 전체 | 20 | **개선 후** | **0.925** | **0.825** |
| 영어 QA | 10 | 개선 전 | 0.900 | 0.950 |
| 영어 QA | 10 | **개선 후** | **1.000** | 0.700 |
| 한국어 QA | 10 | 개선 전 | 0.200 | 0.300 |
| 한국어 QA | 10 | **개선 후** | **0.850** | **0.950** |
| `--limit 3` (EN 상위 3개) | 3 | 초기 테스트 | 0.833 | 1.000 |

> context_recall의 전체 ragas summary 값과 per-sample 기반 단순 평균 사이에 소수점 수준의 차이가
> 있다(개선 전 기준 0.575 vs 0.625). ragas 내부 집계 방식·NaN 처리·정규화 차이로 간주하며, 공식
> 값은 ragas summary 기준을 사용한다. 원본 리포트: `backend/scripts/eval/ragas_report.json`
> (개선 전/후 누적 2회 실행분).

### 개선 작업 (2026-06)

한국어 cross-lingual 성능 저하를 해결하기 위해 `backend/app/rag/retriever.py`의 `retrieve()`에
3가지를 적용했다.

1. **Query translation**: 쿼리에 한글이 포함되면(`_translate_to_english()`, 유니코드 범위 검출)
   LLM으로 영어 검색 쿼리 1줄로 변환 후 검색한다. 영어 쿼리는 그대로 통과해 추가 비용이 없다.
2. **Dual query expansion**: 번역이 실제로 일어난 경우에만 원본 한국어 쿼리로도 추가 검색해서
   두 결과를 기존 dense+sparse RRF 로직으로 재병합한다 — 번역 과정에서 누락될 수 있는 의미를 보완.
3. **임베딩 모델 교체**: `text-embedding-3-small` → `text-embedding-3-large`(1536→3072차원)로
   cross-lingual 검색 정밀도를 높였다. Pinecone 인덱스 재생성 + `chunks.pkl` 재인덱싱이 수반된다.

### 해석

개선 후 한국어 cross-lingual gap은 거의 해소됐다. faithfulness 0.200→0.850,
context_recall 0.300→0.950으로 올랐고, 이번 회차는 한국어 context_recall(0.950)이 영어(0.700)보다
오히려 높다. Query translation이 한국어 질문을 영어 코퍼스와 같은 언어 공간에서 검색하게 만들었고,
dual query expansion이 번역 손실을 보완했으며, 더 큰 임베딩 모델이 cross-lingual 매칭 정밀도를
끌어올린 결과로 분석된다.

다만 트레이드오프가 하나 관찰됐다: 영어 context_recall이 0.950→0.700으로 하락했다(20개 중 3개
샘플 영향). 임베딩 모델 교체로 `chunks.pkl`이 재생성되며 `SemanticChunker`의 청크 경계 자체가
바뀐 영향으로 추정되나, 별도 root-cause 분석은 하지 않았다. 한국어 개선분(+0.650)이 영어 하락분
(-0.250)보다 크고 전체 평균도 0.550/0.575 → 0.925/0.825로 개선됐으므로 순효과는 긍정적이다.

### 향후 개선 방향

| 방향 | 상태 | 내용 |
|------|------|------|
| Query translation | ✅ 완료 | 한국어 질문 → 영어 검색 쿼리 변환 후 retrieve |
| 임베딩 모델 교체 | ✅ 완료 | `text-embedding-3-large`로 교체 |
| Dual query expansion | ✅ 완료 | 한국어 + 영어 쿼리를 동시에 검색해 결과 합산(RRF 재병합) |
| 영어 context_recall 하락 원인 분석 | 미착수 | 청크 경계 변화 영향 추정, root-cause 미검증 |
| Ragas judge 보강 | 미착수 | 한/영 혼합 판정 지침 추가 |

### 의존성 주의사항

ragas import를 위해 `langchain-community`를 0.4.1로 낮췄다.
`langchain-experimental 0.4.2`가 `langchain-community>=0.4.2`를 요구하므로 `pip check` 경고가 잔존한다.
`requirements.txt`에는 미반영하며, Ragas 평가는 별도 평가 환경에서 운영한다.

### 포트폴리오용 요약

Ragas 평가에서 영어 PDF 코퍼스에 한국어로 질의하는 cross-lingual 구간의 성능 저하(faithfulness
0.200, context_recall 0.300)를 진단한 뒤, query translation·dual query expansion·임베딩 모델
교체(`text-embedding-3-large`)를 적용해 한국어 faithfulness 0.850, context_recall 0.950으로
개선했다(전체 평균 0.550/0.575 → 0.925/0.825). 이를 통해 단일 언어 코퍼스 기반 RAG에서도
번역·하이브리드 검색·임베딩 모델 선택을 조합해 cross-lingual 응답 품질을 정량적으로 끌어올릴 수
있음을 검증했다.

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

## 10. 검색 성능 원인 분석과 Jev 비교 — 2026-10-09

이번 단계는 개발용 40문항(20개 사실 그룹)의 원인 분석이다. 최종 평가나 운영 채택 검증이 아니다. `docs/rag_experiments/gold_core40_v2.json`은 WHO sugars의 PDF 12·24쪽을 원문 대조하여 대체 근거로 인정한다. 새 `gold_heldout20_v1.json`은 새로운 10개 사실 그룹의 한·영 20문항이며 검색 실험에 사용하지 않았다. 원문 사실 검토와 임상 정책 승인은 구분한다. Agent·안전 문항을 포함한 전체 120문항은 아직 미완료다.

### 실제 결함 수정

- Pinecone의 float 페이지와 BM25의 int 페이지가 같은 문서인데 다른 RRF 키로 처리되는 문제를 정규화했다. 첫 60자 대신 전체 내용 해시로 식별하여 서로 다른 근거가 합쳐지는 문제도 방지했다.
- 반환 4개 중 문맥에 3개만 전달되던 기본값을 맞췄다. 6,000자 예산에 인용 헤더·구분자를 포함하고 실제 전달된 문서만 출처에 표시한다.
- 동일한 원시 검색 순위를 재생하면 RRF 수정 전/후 페이지 적중률은 75%→80%, 핵심 구절 적중률은 80%→87.5%다. 평균 고유 후보 수는 17.75→20개지만 페이지 MRR은 0.617→0.560으로 감소했다. 모든 지표의 개선으로 해석하지 않는다.

### 동일 후보 리랭킹 비교

번역·검색 후보 20개·반환 4개·문맥 6,000자를 고정한 최초 후보 실험이다. 아래 시간은 리랭킹 단계 평균이며 전체 요청 시간이 아니다. 리랭킹 없음의 시간은 로컬 선택 비용뿐이다.

| 구성 | 허용 페이지 적중률 | 핵심 구절 적중률 | 페이지 MRR | 리랭킹 시간(초) |
|---|---:|---:|---:|---:|
| 없음 | 75.0% | 80.0% | 0.617 | <0.001 |
| MiniLM | 32.5% | 37.5% | 0.263 | 1.49 |
| MultiBERT | 17.5% | 17.5% | 0.142 | 3.33 |
| Jev 1.13.0 | 80.0% | 92.5% | 0.658 | 7.09 |

Jev는 800회 호출에서 API 오류·fallback 0건, 입력 651,064/출력 29,600토큰을 사용했다. 금액은 계산하지 않았다. 한국어 원질문도 고정된 영어 번역으로 리랭킹했으므로 이 결과는 Jev의 한국어 직접 입력 성능을 입증하지 않는다. 1회 실험이며 3회 반복 검증은 남아 있다.

후보 누락과 재정렬 손실을 분리했다. 최초 후보에서 허용 페이지가 없는 사례는 6/40이며 후보에 있던 페이지를 MiniLM 21건, MultiBERT 27건, Jev 2건이 반환 목록에서 잃었다. 두 FlashRank tokenizer의 한국어 문서 쌍 353개 중 209개가 512토큰을 넘었다. 문맥 잘림 위험의 증거지만 단독 원인으로 확정하지 않는다.

RRF 수정 후의 별도 동일 후보 실험에서는 리랭킹 없음이 페이지 80%/구절 87.5%, MiniLM이 42.5%/40%였다. 400자 child(50자 overlap)를 점수화하여 원래 부모 문서로 집계한 제한적 진단은 50%/45%, 평균 4.83초였다. 추가 파라미터 탐색은 중단했다. 이 진단은 전체 parent-child 색인 구성 비교가 아니다. 최초 Jev 결과와 수정 후 후보 결과를 동일 조건으로 비교하지 않는다.

### 답변 생성·Ragas·LangSmith

최초 동일 후보의 없음/Jev 문맥으로 Gemini 답변을 각각 40개 생성하고 별도 Gemini judge로 Ragas 0.2.15를 평가했다. 비교를 위해 비어 있지 않은 문맥을 모두 생성에 허용했으므로 운영 grounding 임계값 검증과 다르다.

| 구성 | Faithfulness | Context recall | 답변 보류 |
|---|---:|---:|---:|
| 없음 | 0.9625 | 0.7125 | 6/40 |
| Jev | 0.9688 | 0.8417 | 2/40 |

각 지표 40/40 유효 결과를 확보했다. 사실 그룹 bootstrap 95% 구간은 faithfulness 차이 [-0.0438, 0.0688], context recall 차이 [-0.0083, 0.2625]로 0을 포함한다. 답변 정확성·적절한 보류·임상 안전을 이 수치만으로 입증하지 않는다. 출처/페이지 형식 대조에서 두 구성 모두 잘못된 출처·페이지 0건이지만 의미상 인용 정확성 평가는 별도다.

초기 Ragas 실행의 Google API 오류·504·metric timeout을 보존했다. 평가 모델 전용 timeout(90초)을 분리하고 사례/지표별 즉시 저장·최대 2회 시도하는 실행기로 완료 결과를 복구했다. 서비스 timeout은 유지했다. 두 최종 결과는 동일 metric/model이지만 실행기 방식이 달라 완전히 동일한 반복 실행으로 주장하지 않는다.

LangSmith에 4개 오프라인 replay 실험을 등록하고 각 root run 40개를 재조회했다. 초기 색인 반영 지연은 제한된 재조회로 처리했다. replay 시간은 실제 Jev API trace나 전체 요청 지연이 아니다. 실험 ID는 `backend/artifacts/frozen-rerank-core40-v1/langsmith-replays.json`에 있다.

### 재현·채택 상태

`backend/`에서 프로젝트 venv로 실행한다. 아래 실행은 유료 API를 호출할 수 있다. 기존 역사 산출물은 보존하고 재실행은 새 출력 경로를 사용한다. 현재 스크립트는 데이터셋·후보·모델·코드 해시가 다른 캐시 재사용을 거절한다.

```powershell
.\venv\Scripts\python.exe scripts/eval/run_frozen_rerank.py --help
.\venv\Scripts\python.exe scripts/eval/run_rrf_identity_ablation.py --help
.\venv\Scripts\python.exe scripts/eval/run_window_rerank_diagnostic.py --help
.\venv\Scripts\python.exe scripts/eval/evaluate_frozen_answers.py --help
.\venv\Scripts\python.exe scripts/eval/score_saved_answers.py --help
```

원본 산출물: `backend/artifacts/frozen-rerank-core40-v1/`, `rrf-identity-core40-v1/`, `frozen-rerank-core40-rrf-fixed/`. 답변 비교는 `paired-quality.json`, 실패 유형은 `diagnostics.json`, 최종 없음 점수는 `metrics-answers-none-3e32bb0cff7ba3d8-c56711abca9ac908/report.json`에 있다.

Jev는 실험 전용이며 운영 활성화하지 않았다. 20개 pair 호출이 일반 모델 예산 12회를 넘으면 호출 없이 기준 순서를 반환한다. API 부분 실패도 전체 기준 순서를 유지한다. 기존 운영 리랭커 기본 설정을 이번 개발 실험만으로 변경하지 않았다. 전체 요청 p95/비용 개선, 독립 최종 평가와 3회 반복 기준이 충족되어야 채택한다.

검증: 백엔드 168 passed / 1 skipped / 기존 deprecation warnings 3개. 다음은 상위 두 파서·청킹 조합의 전체 코퍼스 비교와 Gemini 임베딩 차원 비교, Agent·안전 골드 보완이다. 기능·평가 완료 후 실제 스트리밍/Deep Agent/MCP/kind와 Cue 참고 UI 순서를 유지한다.

## 11. 전체 PDF 파서·청킹 비교 — 2026-10-10

### 문제와 동일 조건 비교

두 출처 파일럿에서 좋았던 구성이 전체 문서에서도 좋은지 확인했다. 선정 PDF 10개/1,953페이지, 개발 질문 40개(20개 사실 그룹의 한·영 질문), Gemini embedding 2/3072차원, 고정 질의 번역, 검색 후보 20개/반환 4개, 출처 헤더 포함 문맥 6,000자, 리랭킹 없음으로 비교했다. 독립 최종 평가 20문항은 조회하지 않았다. 신규 벡터는 로컬 exact cosine 인덱스로 분리했고 운영 Pinecone와 BM25 파일을 변경하지 않았다.

초기 Docling/page는 24→8페이지 배치와 모델 재사용으로도 120초 timeout·부분 변환·table worker 종료 실패가 반복됐다. v2의 완료 요청 페이지는 120/1,953이며 전체 성공 후보로 채점하지 않았다. 성공 상태와 실제 canonical 페이지 완전성 검사로 부분 산출물 재사용을 차단했다. 대체 후보 PDFPlumber/page와 PDFPlumber/section을 전체 처리하고, 기존 PyPDF/recursive 4,139개 벡터를 캐시에서 API 호출 없이 control로 가져왔다. 이는 성공한 두 파서의 전체 비교가 아니라 Docling 안정성 탈락 후 두 청킹과 기존 구성의 비교다.

### 결과

| 구성 | 검색 | 근거 페이지 적중 | 핵심 구절 적중 | 항목 순위 MRR | 평균 문맥 문자 | 잘린 요청 |
|---|---|---:|---:|---:|---:|---:|
| PDFPlumber/page | Dense | 65% | 62.5% | 0.527 | 5,783 | 32/40 |
| PDFPlumber/page | Hybrid | 60% | 57.5% | 0.519 | 5,921 | 33/40 |
| PDFPlumber/section | Dense | 65% | 62.5% | 0.527 | 4,476 | 0/40 |
| PDFPlumber/section | Hybrid | 65% | 60% | 0.513 | 4,563 | 0/40 |
| 기존 PyPDF/recursive | Dense | 75% | 67.5% | 0.638 | 4,157 | 0/40 |
| 기존 PyPDF/recursive | Hybrid | 80% | 75% | 0.573 | 4,296 | 0/40 |

페이지 적중은 허용 출처·페이지가 실제 전달 문맥에 있는지, 핵심 구절 적중은 해당 문맥에 정답 구절이 있는지 보는 결정적 자체 평가다. MRR은 표준 검색 지표의 반환 문맥 항목 순위 구현이다. Ragas 답변 점수는 이번에 새로 측정하지 않았다. 문맥 포장·정규화·로컬 검색 방식이 이전 실험과 달라 이전 87.5% 등의 수치를 이번 75%와 직접 증감 비교하지 않는다.

20개 사실 그룹 단위 paired bootstrap(10,000회, seed 42)에서 Hybrid section의 페이지 적중 차이는 기존 대비 -15%p, 95% 구간 [-30, -2.5]%p였다. 구절 차이 -15%p 구간 [-32.5, 0]%p이며 표본이 작다. Dense 기존 구성은 MRR이 가장 높고 Hybrid는 전체 적중률이 높아 모든 지표에서 단일 승자라고 주장하지 않는다. 한·영 번역을 독립 40개 사실처럼 resampling하지 않았다.

**결정:** 기존 PyPDF/recursive를 유지한다. Hybrid를 다음 차원 실험의 잠정 기준으로 삼되 운영 검색 기본값·리랭커는 변경하지 않는다. PDFPlumber/section은 긴 페이지의 문맥 잘림을 해결했지만 전체 근거 적중 개선이 없어 채택하지 않는다. 파서/청킹 추가 탐색은 여기서 종료하고, 선정 기준선의 Gemini 768/1536/3072차원 비교로 넘어간다.

### 원문 보존 수정과 오류 기록

### 선정 해석: 관측 사실과 가설의 구분

Docling/page는 작은 파일럿에서 검색 점수 0.55로 좋은 결과를 보였지만 전체 코퍼스에서는 처리 안정성 기준을 충족하지 못했다. 따라서 “전체 검색 정확도가 PyPDF보다 낮았다”가 아니라 “전체 처리 성공률·안정성 때문에 탈락했고, 완료된 비교에서는 PyPDF/recursive 조합을 유지했다”라고 설명한다. 실패한 부분 결과를 전체 정확도 점수로 만들지 않는다.

page 청킹의 문맥 잘림은 측정된 원인이다. recursive의 작은 검색 단위가 문장 중심 질문에 유리했을 가능성은 가설이며 인과관계가 입증된 것은 아니다. section도 잘림 없이 적중률이 낮았으므로 잘림만으로 모든 차이를 설명하지 않는다. 표 구조 보존 개선과 검색 정확도 개선은 별도로 평가해야 한다. 현재 질문은 문장·조건 중심이고 표 계산·그림 해석을 대표하지 않는다.

Docling은 구조화된 문서 표현에서 표·그림·페이지/좌표 정보를 다루고 Markdown/HTML/JSON으로 내보낼 수 있다. 그러나 구조 감지·이미지 보관·그림 의미 해석은 서로 다르다. 복잡한 병합 셀은 Markdown보다 HTML/JSON 보존이 적합하며 OCR와 그림 설명은 실제 설정·실행 여부를 확인해야 한다. 이번 전체 후보의 성공이나 모든 구조의 정확한 보존을 보장하지 않는다. 참고: https://docling-project.github.io/docling/concepts/serialization/ 및 https://docling-project.github.io/docling/usage/vision_models/.

파서 자체의 효과를 분리하려면 동일 페이지·동일 recursive 설정으로 PyPDF/PDFPlumber/Docling을 비교하고, 청킹 효과는 동일 파싱 산출물에서 page/parent-child/section 또는 recursive 기준선으로 비교해야 한다. 텍스트·표·그림/OCR 유형별 원문 골드를 만들고 수치·부호·단위·행열 대응·조건·출처와 처리 성공률/시간을 따로 채점한다. Docling 부분 결과는 공통 성공 페이지의 조건부 품질로만 비교하고 전체 실패율을 별도로 보고한다. 상위 구성만 전체 코퍼스에 적용해 고정 생성 모델·judge의 Ragas 및 답변 정답 평가를 3회 반복한 뒤, 튜닝에 쓰지 않은 독립 사실 그룹으로 최종 확인한다. 모든 파서 조합을 다시 확대하지 않고 기존 1주 범위에서는 이 분리 실험을 추가 계획으로 남기며, 현재 잠정 기준선의 임베딩 차원 비교 순서를 유지한다.

### 원문 보존 수정 상세

- PDFPlumber 기본 추출이 가장자리 셀을 누락했는데 해당 표 bbox 원문도 제거하던 문제를 수정했다. KDRI 1권 PDF p64의 `+115.5/+22/+20`, p65의 `+340` 등이 대상이다. 원문 좌표로 빈 셀만 복구하고 부호·숫자·출현 횟수가 보존된 경우에만 원문 중복을 제거한다. 실패하면 원문을 유지하고 불완전 파생 표는 검색에서 제외한다. 값 추정/자동 채움은 하지 않는다.
- 원본 렌더링과 대조한 수치·단위·조건 앵커 6/6, 표 행 5/5, 골드 사실 핵심 구절 20/20을 보존했다. 모든 표의 행·열 정확도나 임상 승인을 의미하지 않는다. Docling에서 대상자 수 `9`가 연령 열로 이동하는 사례도 기록했다.
- PDF 밖 table bbox로 KDRI p261–264와 비만지침 초기 페이지에서 실패했다. 실제 페이지 경계 제한과 원문 유지로 복구했고, 실패 v3는 보존했다. 최종 v4 전체 1,953페이지 처리에 실패 배치는 없다.
- PDFPlumber/page 1,932청크, section 3,729청크. 21페이지는 색인 가능한 텍스트가 없으며 OCR나 그림 의미 추출을 완료한 것은 아니다.
- Gemini 임베딩 503 UNAVAILABLE를 첫 실패 로그에 보존하고 동일 설정의 한 차례 stage 재개로 완료했다. 성공 벡터 캐시를 재사용했다. 벡터 수로 API 호출 비용을 추정하지 않는다.
- SDK의 `GOOGLE_API_KEY`/`GEMINI_API_KEY` 동시 존재 경고가 기록됐다. adapter는 settings의 Gemini 키를 명시 전달하며 비밀값은 로그/보고서에 기록하지 않았다.

### 재현 및 한계

백엔드에서 프로젝트 venv를 사용한다. 파서 runtime 패키지 버전, 코드/문서 SHA와 배치 로그는 산출물에 보존한다.

```powershell
.\venv\Scripts\python.exe scripts/eval/run_full_recipe_comparison.py --stage parse-fallback --batch-pages 8 --workers 2 --output artifacts/full-recipes-v4
.\venv\Scripts\python.exe scripts/eval/run_full_recipe_comparison.py --stage export-baseline --output artifacts/full-recipes-v4
.\venv\Scripts\python.exe scripts/eval/run_full_recipe_comparison.py --stage embed --output artifacts/full-recipes-v4
.\venv\Scripts\python.exe scripts/eval/run_full_recipe_comparison.py --stage evaluate --output artifacts/full-recipes-v4
.\venv\Scripts\python.exe scripts/eval/audit_full_recipe_parsing.py --directory artifacts/full-recipes-v4
.\venv\Scripts\python.exe artifacts/full-recipes-v4/analyze_paired.py
.\venv\Scripts\python.exe -m pytest --basetemp artifacts/pytest-full-recipes-release -q
```

동일 parse artifact를 재조립하면 control을 제거하므로 export-baseline을 다시 실행한다. 변경된 파서 코드/버전에는 새로운 output 디렉터리를 사용한다. 기준선 캐시와 원본 벡터 산출물이 있어야 API 호출 없이 control export를 재현할 수 있다.

구조화 요약은 `docs/rag_experiments/full_recipe_summary_v1.json`, 실제 문맥/질문별 오류/paired 구간은 `backend/artifacts/full-recipes-v4/`에 있다. 이 단계는 개발셋 기반 잠정 선택이며 3회 반복·독립 최종 평가·Agent 안전 평가·Ragas 답변 평가를 완료한 결과가 아니다. 로컬 검색 시간은 질의 임베딩·번역·Pinecone 네트워크와 전체 요청 지연을 제외하므로 운영 속도 개선으로 주장하지 않는다.

최종 검증: 183 passed / 1 skipped / 기존 deprecation warnings 3개, 수정 스크립트 구문 검사 및 diff 공백 검사 통과. 다음 순서는 임베딩 차원 비교 → 고정 구성의 Jev 리랭킹 재비교 → Agent/안전 골드 및 Jev routing/tool 비교 → 독립 최종 평가다. 기능·평가 완료 후 streaming/Deep Agent/MCP/kind와 Cue 참고 UI 순서를 유지한다.

## 12. Docling 복구와 GPU 대조 (2026-10-10)

전체 후보 탈락의 원인을 로그로 다시 검사했다. 8페이지 CPU 배치의 표 처리가 120초 제한을 넘어 `partial_success`로 끝났다. 제한만 300초로 늘린 대조 실행은 8/8페이지를 완료했다. 1스레드로 줄이는 시도는 더 느렸으므로 4스레드를 유지했다. 실패 산출물은 정상 결과에 섞지 않는다.

PDFium backend의 KDRI p10 표는 원본 14열을 6열로 잘못 구성했다. native `docling_parse` backend는 14열을 복구했지만 일부 연령 행 병합은 남았다. FAST는 대표 표 행 4/5만 보존했고 ACCURATE는 5/5를 보존해 ACCURATE를 유지한다. 이는 작은 구조 점검 결과이며 전체 표 정확도가 아니다. OCR 및 그림 의미 설명은 이번 복구에서 실행하지 않는다.

실제 RTX 3070 Laptop GPU(8GB)가 있으나 기존 torch는 CPU build였다. CUDA torch를 실험 전용 `backend/artifacts/gpu-runtime`에 설치했고 기존 서비스 환경과 드라이버는 보존했다. 최초 C 임시 공간 부족은 설치 프로세스의 임시 디렉터리를 D로 지정하여 해결했다. [공식 PyTorch 설치 조합](https://pytorch.org/get-started/previous-versions/)을 사용했다.

| 대조 | 동일 조건 | 전체 worker 시간 | 구조 점검 |
|---|---|---:|---|
| CPU | torch 2.11.0+cu128, native, ACCURATE, 4threads, 300초, p10·64·65 | 73.665초 | 수치 앵커 6/6, 표 행 5/5 |
| GPU | 위 조건에서 device만 cuda | 34.847초 | 수치 앵커 6/6, 표 행 5/5 |

약 2.11배의 단일 표본 속도 차이로, 초기화·파싱·산출물 저장을 포함한다. 반복 측정이나 전체 코퍼스 처리량으로 일반화하지 않는다. 양쪽 원문 SHA, 런타임 버전, 설정, 로그, 산출물은 `backend/artifacts/docling-recovery-v1/native-{cpu-same-version,gpu-accurate}`에 보존한다.

전체 확대는 4페이지씩, GPU worker 1개로 실행한다. 배치의 요청 페이지가 아니라 canonical JSON에 실제 변환된 페이지를 확인한다. 중단 캐시는 검증 실패 시 재처리하고 marker는 임시 파일 작성 후 교체한다. 현재 설정과 다른 완료 marker는 집계에서 제외한다. 전체 결과는 `backend/artifacts/docling-recovery-v1/full-gpu-v2/report.json`에 기록한다. 전체 완료·검색 평가 전에는 Docling이 기존 PyPDF/recursive보다 우수하다고 판정하지 않는다.

재현 진입점(backend cwd, 프로젝트 venv):

```powershell
venv\Scripts\python.exe scripts\eval\run_docling_recovery.py --job artifacts\docling-recovery-v1\native-cpu-same-version-job.json
venv\Scripts\python.exe scripts\eval\run_docling_recovery.py --job artifacts\docling-recovery-v1\native-gpu-accurate-job.json
venv\Scripts\python.exe artifacts\docling-recovery-v1\run_full_gpu.py
venv\Scripts\python.exe artifacts\docling-recovery-v1\collect_full.py
```

전체 반복 실행은 검증된 완료 배치를 재사용하므로 새 속도 측정으로 세지 않는다. 새로운 측정은 별도 output 경로를 사용한다. GPU/runtime 설치 helper와 설치 오류 로그는 동일 recovery 폴더에 있으며, API 키는 필요하지 않다.

전체 복구 결과: 10개/1,953페이지의 실제 canonical 페이지와 원문 SHA·code SHA·Docling 버전·backend·페이지·config가 일치함을 검증했다. page 검색용 산출물은 1,925청크이며 아직 새 임베딩/운영 색인에 적용하지 않았다. 원문 대조는 수치·단위·조건 앵커 6/6, 표 행 5/5, 개발 골드 사실 그룹 핵심 구절 20/20 통과했다. 이 검사는 보존 여부이며 검색 Recall·답변 정확성·모든 표/그림 정확성이 아니다.

전체 시도 시간 합계는 2,843.081초(약 47.4분, 실패 포함)다. 수동 점검 대기·설치·별도 진단 실험 시간은 제외한다. KDRI 1권은 첫 실행에 완료됐으나 2권에서 heap/access violation 3회, 3권에서 access violation 3회가 발생했다. 3권 남은 15페이지의 native parser pool=1 실험도 8페이지 이후 access violation이 발생했고, 나머지 7페이지는 PDFium GPU에서 완료했다. WHO 탄수화물은 PDFium에서도 access violation 1회 이후 재개했다. 즉 실패 8회가 있었으며 GPU만으로 안정성 문제가 해결된 것은 아니다. 종료 위치는 native iter_pages/iterate_results와 모델/스레드 스택에 나타났지만 정확한 결함 DLL·경쟁 상태는 확정하지 못했다. [공식 프로젝트의 유사 native crash 보고](https://github.com/docling-project/docling/issues/4147), [다른 backend에서도 발생한 표 처리 오류 보고](https://github.com/docling-project/docling-ibm-models/issues/170)를 근거로 격리·재개·backend 변경을 시도했으며 동일 버그라고 단정하지 않는다.

`uniform_config=false`: KDRI 일부 native 기본/단일 parser thread, 나머지 PDFium으로 복구한 자료다. 전부 Docling으로 처리했지만 하나의 고정 backend 설정으로 전체 성공한 실험은 아니다. 이 산출물로 'Docling이 PyPDF보다 우수하다' 또는 순수 파서 속도를 주장하지 않는다. 전체 로그와 시도별 시간은 보존했고 운영은 기존 PyPDF/recursive를 유지한다. 복구는 여기서 마치며, 다음은 대표 문장·표·조건 페이지에서 같은 청킹으로 파서 효과를 분리한 비교 → 선정 구성의 임베딩 차원 비교다.

재개/우회 진입점:

```powershell
venv\Scripts\python.exe scripts\eval\run_docling_recovery.py --job artifacts\docling-recovery-v1\native-gpu-vol3-parser1-job.json
venv\Scripts\python.exe scripts\eval\run_docling_recovery.py --job artifacts\docling-recovery-v1\gpu-vol3-pdfium-final-job.json
venv\Scripts\python.exe artifacts\docling-recovery-v1\run_remaining_gpu.py
venv\Scripts\python.exe artifacts\docling-recovery-v1\collect_full.py
```

기존 실패를 성공으로 바꾸지 않고, collector의 전체 페이지 검증으로 복구 완료 범위만 인정한다.

## 13. Docling 종료 원인 분리 — 2026-10-10

이전의 ‘native 종료 8회’는 운영 파서의 단일 결함 8회라는 의미가 아니었다. 원래 실패 기록은 보존하고, Windows Event 1000·크래시 덤프·동일 Python 버전의 공식 PDB로 종료 위치를 추가 분석했다.

- 원래 전체/보완 실행의 최종 종료 직전 Windows 기록은 7회 `python313.dll` 접근 위반, 1회 `ntdll.dll` heap corruption이었다. 동일 PID에서 더 이른 `pdf_parsers.cp313-win_amd64.pyd` 오류도 있었다. 이벤트 개수와 프로세스 실패 개수를 동일하게 세지 않는다.
- Python의 RVA `0x2b0b98`, `0x2b0bab` 및 최소 재현의 `0x2b0baf`는 공식 Python 3.13.3 PDB에서 **`dump_frame`, `Python/traceback.c:907`**로 해석됐다. 실행 중인 프레임의 code/file-name 정보를 읽는 진단 함수다. PyTorch가 출력된 스택은 조사 대상 스레드의 스택일 수 있으며, 그것만으로 PyTorch 연산 자체의 충돌을 뜻하지 않는다.
- Docling/PDF를 완전히 제외한 `MultiheadAttention`+스레드+주기적 faulthandler 실험: 진단 타이머 ON 3/3 access violation, OFF 3/3 정상 완료. OFF도 동일한 CUDA context 경고를 출력하고 성공했다. 최소 재현은 발생 확률을 높이기 위해 타이머를 1ms로 설정했으며, 원래 실행의 90초 타이머 오류율을 추정하는 벤치마크가 아니다. 순수 Python code-churn 재현은 3/3 성공했다. 따라서 이 설치 조합에서 비동기 프레임 덤프가 충돌을 유발한다는 근거를 확보했으며, 모든 Python 버전·모델에 일반화하지 않는다.
- 복구 runner에서 `dump_traceback_later`를 제거했다. fatal-exception handler와 부모 프로세스 wall timeout은 유지한다. 전체 10개 자료를 다시 파싱하지 않고 이전 실패 조건의 KDRI 3권 521~535페이지로 반복 대조했다. 최종 횟수·시간은 `backend/artifacts/docling-recovery-v1/crash-probe-no-watchdog-summary.json`에 기록한다.
- 별개의 파서 오류: `docling-parse 7.22.2`의 **`pdf_parsers.cp313-win_amd64.pyd + 0x7e5a97`**에서 `0xffffffffffffffff` 주소 읽기 오류가 덤프에 확인됐다. 모델 추론·GPU·faulthandler를 제외한 threaded parser/render-only 실험에서도 같은 모듈/주소의 Event 1000을 확인했다. 이 경로는 `DoclingThreadedPdfParser`가 사용하는 `_threaded_pdf_renderer` C++ 확장이다. heap-corruption 덤프의 원시 stack 주소 후보에도 해당 모듈이 있다. 원시 주소 후보는 unwind된 호출 스택이 아니므로 함수 순서·최초 메모리 오염 위치를 주장하지 않는다.
- 파서-only 긴 실행의 제한 시간 종료와 Windows 접근 오류는 별도로 기록한다. 문제 발생 직후로 추정한 489~492페이지 단독 반복이 성공해, 해당 페이지 자체의 결정적 오류라는 결론은 내리지 않는다. 단일 thread도 모든 문서에서 안정적이라는 결론은 내리지 않는다.

**결론:** 진단용 비동기 프레임 출력 오류는 위치와 최소 재현을 확보해 제거했다. 별개의 native PDF parser/render 경로도 구성요소까지 분리했지만, 내부 C++ 함수의 잘못된 할당/해제 또는 경쟁 상태는 미확정이다. Windows wheel에는 해당 결함을 소스 행으로 해석할 PDB가 제공되지 않아, 더 깊은 규명에는 동일 버전의 debug/sanitizer 빌드가 필요하다. 새 결과로 이전 Docling 안정성 탈락 판정을 단순 유지하지 않고, 파서 비교 전 안정성을 다시 확인한다. 운영 PyPDF/recursive와 Gemini 색인은 변경하지 않았다.

관련 원본: `backend/artifacts/docling-recovery-v1/{windows-crash-events.json,dump-exceptions.json,dump-stack-candidates.json,symbol-resolution.txt,faulthandler_torch_probe.json,faulthandler_torch_control.json,parse-only-summary.json,parse-focus-summary.json}`. 원본 crash dump에는 프로세스 메모리가 포함돼 공개 포트폴리오에 복사하지 않는다.

공식 근거: [Python 3.13.3 심볼](https://www.python.org/ftp/python/3.13.3/amd64/), [해당 버전 dump_frame 소스](https://github.com/python/cpython/blob/v3.13.3/Python/traceback.c#L907), [faulthandler 비동기 덤프 crash 보고](https://github.com/python/cpython/issues/158200), [native parser 유사 오류 보고](https://github.com/docling-project/docling/issues/4147). 유사 보고가 이 설치의 동일 버그라는 의미는 아니다.

검증: 관련 복구·파서 테스트 12개 통과(기존 Pydantic 경고 1개). 첫 실행의 기본 TEMP 권한 오류는 새 workspace `--basetemp`로 재실행해 해소했다.

최종 대조 결과: 진단 타이머를 제거한 KDRI 3권 521~535페이지 처리 **3/3회 완료**, 각 15페이지의 manifest/실제 페이지 검증 통과(203.921초, 290.307초, 208.192초). 단독 489~492페이지 10회 반복은 parser threads=4/1 모두 성공(각 50.168초/52.013초); 이는 긴 실행의 메모리 수명·동시성 문제를 배제하지 않는다. 모델 없는 긴 파싱 실험은 두 설정 모두 240초 제한에 도달했고, threads=4에서 그 전에 native 접근 오류가 Windows에 기록됐다. 전체 corpus 안정성 성공으로 계산하지 않는다. 최종 결과는 [진단 JSON](docs/rag_experiments/docling_crash_diagnosis_v1.json)에 저장했다. 문법 검사와 `git diff --check`도 통과했다.
# 14. 동일 페이지 파서·청킹 재비교 (2026-10-10)

반복 진단 타이머를 제거한 뒤 10개 문서의 동일한 선정 페이지 26개에서 PyPDF/PDFPlumber/Docling을 비교했다. 각 파싱 결과에 page/parent-child/section/recursive를 적용하고 BM25 dual query, 후보 20개·반환 4개, 문맥 6,000/12,000자를 고정했다. 개발 질문 40개는 한·영 쌍을 포함하는 사실 그룹 20개다. 이 실험은 전체 코퍼스 검색이나 Ragas 답변 품질의 최종 평가가 아니다.

Docling은 GPU/native backend, parser threads=1, model threads=4, ACCURATE, OCR off의 동일 설정으로 10/10 문서 선정 페이지 처리를 완료했다. 이번 30개 parser worker에서 native 종료는 없었다. 이전 장기 실행의 독립적인 docling-parse 접근 오류가 근본 해결됐다는 뜻은 아니다. 문서별 process 격리·유한 timeout·실제 페이지 검증을 유지한다.

| 조합 | 페이지 적중 | 구절 적중 | MRR |
|---|---:|---:|---:|
| PyPDF/page | 72.5% | 72.5% | 0.683 |
| PyPDF/parent-child | 75.0% | 75.0% | 0.571 |
| PyPDF/section | 75.0% | 67.5% | 0.679 |
| PyPDF/recursive | 75.0% | 62.5% | 0.642 |
| PDFPlumber/page | 72.5% | 72.5% | 0.683 |
| PDFPlumber/parent-child | 75.0% | 65.0% | 0.571 |
| PDFPlumber/section | 75.0% | 67.5% | 0.667 |
| PDFPlumber/recursive | 75.0% | 62.5% | 0.638 |
| Docling/page | 72.5% | 72.5% | 0.667 |
| Docling/parent-child | 70.0% | 60.0% | 0.571 |
| Docling/section | 75.0% | 65.0% | 0.583 |
| Docling/recursive | 75.0% | 65.0% | 0.633 |

표의 수치는 문맥 6,000자 조건이다. 12,000자에서는 잘림이 줄었으나 이 개발셋의 적중률/MRR은 변하지 않았다. 따라서 문맥 확대 자체를 성능 향상으로 주장하지 않는다. recursive는 선정 페이지를 같은 1200/150 splitter로 나눈 대조군이며 운영의 전체 문서 전처리를 그대로 재생한 결과는 아니다. GPU/CPU 환경이 다른 파서들의 소요 시간도 순수 파서 속도 비교로 해석하지 않는다.

텍스트 수치·단위·조건 앵커는 세 파서 모두 6/6, 사실 구절은 20/20이었다. 표 행·열 관계 앵커는 PyPDF 0/5, PDFPlumber/Docling 5/5다. PyPDF에 표 값이 없다는 의미가 아니라 구조화된 행·열 관계 검사를 통과하지 못했다는 뜻이다. 표 앵커 5개로 전체 표 정확도를 일반화하지 않는다. 이미지 산출물은 존재 여부만 기록했고 OCR/캡셔닝 의미 정확도는 평가하지 않았다.

실패 분석: Docling의 `700–3000 mg`/`every 3–4 h`가 ASCII 하이픈으로 추출돼 기존 평가가 구절 누락 2건으로 잘못 판정했다. 숫자 사이 en dash만 통일하고 음수 부호는 보존하는 회귀 테스트 후 18/20→20/20으로 정정했다. 이것은 파서 품질 개선이 아니라 평가 오류 수정이다. 기존 v1/v2 산출물은 보존하고 수정한 helper/code/runtime identity로 v3 평가를 재생했다.

재현성 보완: 실패 캐시 재사용 금지, 원문/페이지/파서 버전/backend/config/code 및 donor Docling dependency 버전 검사, 비연속 선정 페이지의 section 연결 금지, 불완전 비교 행렬의 실패 종료를 적용했다. 초기 pytest의 C sandbox 임시 경로 오류 및 D basetemp 부모 미생성 오류는 D 부모 디렉터리를 생성하고 명시해 해결했다. 관련 공식 근거: [pytest temporary directories](https://docs.pytest.org/en/stable/how-to/tmp_path.html), [Python tempfile](https://docs.python.org/3/library/tempfile.html).

판정: Docling을 실험 후보로 복귀시키되 운영 PyPDF/recursive는 유지한다. 선정 페이지에서 PyPDF/parent-child가 높은 구절 적중을 보였지만 MRR이 낮아 단일 최적 조합으로 확정하지 않는다. 다음 단계는 전체 코퍼스 후보 확인과 Gemini 임베딩 768/1536/3072 비교, 이후 독립 답변 평가다. 신규 운영 임베딩·Pinecone 교체는 실행하지 않았다.

결과: `docs/rag_experiments/controlled_parser_summary_v1.json`, 원본 `backend/artifacts/controlled-parsers-v3/`. 백엔드 196 passed/1 skipped/기존 warnings 3, 프론트 변경 없음. C의 이번 작업 crash dump 9개(4,995,261,126 bytes)를 D archive로 이동해 C 여유를 약 5.7GB로 확보했다. dump는 프로세스 메모리이므로 공개 포트폴리오에는 포함하지 않는다.

## 15. 전체 코퍼스 공정 비교와 임베딩 차원 독립 검증 (2026-10-10)

범위: PDF10개/1,953페이지 전체를 PyPDF·PDFPlumber·Docling으로 각각 처리하고, 같은 파싱 결과에 page/parent-child/section/recursive를 적용했다. 30개의 완료 영수증, 원문SHA, 실제 페이지 범위, 파서·의존성 버전과 설정을 검증했다. 기존 혼합 backend 복구 산출물은 재사용하지 않았다. 이번 결과는 기존 선정26페이지 비교와 구분한다.

Docling은 CUDA/native backend/parser_threads1/model_threads4/ACCURATE/OCR off/배치24페이지/배치timeout300초/문서wall1800초를 고정했다. 전체 처리 소요는 PyPDF50.4초, PDFPlumber147.8초, Docling2352.7초였다. 서로 다른 구현 및 CPU/GPU 조건이므로 순수 알고리즘 속도 비교로 일반화하지 않는다. 텍스트 수치·단위·조건6/6, 사실구절20/20은 모두 통과했다. 표 행 관계5개는 PyPDF0/5, PDFPlumber·Docling5/5였다. PyPDF에 숫자가 없다는 뜻은 아니다. OCR/그림 캡션의 의미 정확도는 평가하지 않았으며 표 앵커5개로 전체 표 정확성을 주장하지 않는다.

첫 검색 단계는 BM25 단독 선별이다. 40개 개발 문항/20사실그룹, 고정 번역, 후보20/반환4, 문맥6k/12k 조건의 12조합×2예산 전체 결과를 보존했다. 6k 핵심구절 적중률은 PyPDF/recursive25%, Docling/page40%였다. 이 수치는 dense나 답변 정확도가 아니다. 운영 알고리즘 대조군 PyPDF/recursive와 6k 구절 적중·MRR 기준 최상위 도전자 Docling/page만 차원 실험으로 확대했다. 나머지10조합의 dense 전수 탐색은 제외했으므로 전역 최적 파서·청킹을 확정하지 않는다.

차원 실험: Gemini Embedding2 동일3072 벡터에서 768/1536 prefix를 정규화한다. 공개·합성 문서/질의2개×3차원 실제API6호출로 direct768/1536와의 cosine최소0.99999988을 확인한 후 캐시를 재사용했다. 임베딩 모델3종 비교가 아니라 같은 모델의 MRL 차원 ablation이다. [공식 Gemini 임베딩 설명](https://ai.google.dev/gemini-api/docs/embeddings)에 따른 방법이며, 차원을 줄여도 입력 토큰 API 비용이 줄었다고 주장하지 않는다.

| 고정 조합 | 차원 | 개발40 구절 적중 | 독립20 구절 적중 | 벡터 저장 MiB |
|---|---:|---:|---:|---:|
| PyPDF/recursive | 768 | 70.0% | 70.0% | 12.13 |
| PyPDF/recursive | 1536 | 67.5% | 75.0% | 24.26 |
| PyPDF/recursive | 3072 | 67.5% | 75.0% | 48.53 |
| Docling/page | 768 | 57.5% | 65.0% | 5.63 |
| Docling/page | 1536 | 50.0% | 65.0% | 11.27 |
| Docling/page | 3072 | 50.0% | 70.0% | 22.54 |

독립20문항/10사실그룹은 개발20그룹과 겹치지 않는다. 한·영 번역쌍은 같은 분할에 두고, 후보·조건은 개발 결과를 본 뒤 독립 검색 실행 전에 고정했다. 개발에서 선택한 PyPDF/recursive768은 독립 평가에서3072보다5%p 낮아 채택하지 않았다. 그룹 단위 paired bootstrap2000회 차이95%구간은 개발[0,+7.5%p], 독립[-15,0%p]다. 작은 표본으로 안정적 비열등성을 확인했다고 주장하지 않는다. 1536은 유망한 후속 후보이나 이 독립셋을 보고 선택한 뒤 같은 셋을 다시 독립 확인으로 사용할 수 없다.

PyPDF/recursive 로컬 exact cosine 검색p95는 개발768/1536/3072=2.88/3.03/5.36ms, 독립=2.59/2.99/4.82ms다. query API·Pinecone·답변 생성이 제외된 값이며 전체 서비스 지연20% 개선으로 해석할 수 없다. 3회 반복은 지연 측정이며 독립 표본 수가120/60으로 증가한 것이 아니다. 벡터 저장량은 float32행렬이며 Python/Pinecone/원문 이미지 저장 overhead와 실제 API 청구액은 포함하지 않는다.

실패와 진단:

- 첫 임베딩 실행은 sandbox DNS getaddrinfo11001/HTTPX ConnectError로 중단됐다. 로그를 별도 보존하고 [HTTPX 오류 분류](https://www.python-httpx.org/exceptions/)를 대조한 뒤 승인된 네트워크 환경에서 같은 identity로 재실행해 성공했다.
- Docling은 exit0/전체 페이지를 완료했지만 vol3 배치385–408에서 접근 오류 메시지2개 및 Windows 오류 이벤트/dump1개가 발생했다. Python3.13.3 공식PDB로 dump의 오류 위치를 python313.dll+0x2b0b98=`dump_frame`, traceback.c:907/read0x71로 확인했다. stack 내 pdf_parsers 주소는 unwind된 원인 stack이 아니므로 최초 메모리 오류 함수를 확정하지 않는다. [CPython Windows faulthandler 이슈](https://github.com/python/cpython/issues/74311), [Windows 예외 처리 설명](https://github.com/python/cpython/issues/75882)을 대조했다. 동일24페이지 재실행은 오류0/페이지검증 통과, 원래174개 블록과 페이지·종류·텍스트 multiset이 완전히 같았다. 산출물 일관성을 확인했지만 native 오류 근본 해결을 선언하지 않는다. crash dump는 D private archive로 이동했고 공개 요약에 포함하지 않았다.
- Docling MatchingPostProcessor의 표 셀 누락 경고28개를 원본 로그·JSON과 보존했다. 설치 소스의 row/column band 밖 orphan cell 제거 경로 및 [공식 이슈3921](https://github.com/docling-project/docling/issues/3921)을 조사했다. 표 앵커 통과와 이 경고는 별개다. 비교 중 설정을 바꾸지 않았으며 전체 표 무손실을 주장하지 않는다.
- 완료 캐시가 artifact 수집 전에 저장되던 창을 막고, 차원 runner가 과거 혼합 설정이나 불완전 페이지 결과를 받아들이지 않도록 provenance 검사를 강화했다. 실행 중 v1 runner는 원본 코드 snapshot/hash를 보존했으며 후속 수정 코드의 hash로 결과를 포장하지 않는다.
- 독립셋 실행은 명시적 --split heldout이 필요하다. 개발 전용 검증을 완화하지 않고 별도 검토/중복 경계를 테스트했다.

판정: 운영 PyPDF/recursive·Gemini3072 유지. Docling은 전체 공정 비교까지 수행했으나 안정성·문맥 잘림과 dense 결과를 고려해 자동 채택하지 않는다. 다음 단계는 고정 검색 구성의 답변 생성+Ragas 검증, Jev 리랭킹과 Supervisor/도구 선택의 분리 비교다. 새로운 평가 그룹이 필요한 경우 기존 개발/이미 관찰한 독립셋과 분리한다. 현재 결과를 서비스 전체 품질 또는 Ragas 결과라고 표현하지 않는다.

재현 명령(backend, D temp/cache; Gemini 네트워크 허용):

```powershell
venv/Scripts/python.exe scripts/eval/run_uniform_full_comparison.py --output artifacts/uniform-full-v2
venv/Scripts/python.exe scripts/eval/run_dimension_comparison.py --source artifacts/uniform-full-v2 --output artifacts/dimension-full-dev-v2 --recipes pypdf-recursive docling-page
venv/Scripts/python.exe scripts/eval/run_dimension_comparison.py --source artifacts/uniform-full-v2 --output artifacts/dimension-full-heldout-v2 --recipes pypdf-recursive docling-page --split heldout --dataset ../docs/rag_experiments/gold_heldout20_v1.json --translations artifacts/heldout20-frozen-translations-v1.json
```

재실행은 변경 코드 때문에 새 출력 디렉터리를 사용한다. 번역·후보를 다시 튜닝하지 않는다. v1 원본/manifest/버전/고정 설정/contexts/실패 로그는 backend/artifacts의 uniform-full-v1, dimension-full-dev-v1, dimension-full-heldout-v1에 보존했다. 공개 요약은 docs/rag_experiments/uniform_full_summary_v1.json 및 dimension_full_summary_v1.json. 백엔드206passed/1skipped/기존warning3, 변경파일 py_compile통과. 프론트·운영.env·Supabase·Pinecone 변경 없음.

추가 진단(2026-10-10): recovery worker fatal handler를 all_threads=False로 제한해 Python dump_frame의 다른 스레드 순회 경로를 줄였다. [CPython 이슈116008](https://github.com/python/cpython/issues/116008)은 유사 스택 출력 오류 사례이며 현재 사례와 동일 원인이라는 증거는 아니다. 새 프로세스2회/각24페이지에서 접근오류0, 기존174블록 완전일치. 기존 설정의 짧은 재실행도 성공했으므로 장시간 native 오류의 근본 해결은 미확정이다. 비교v1산출물/identity는 유지하며 다음 실행은 변경 코드의 새identity로 구분한다. 관련 회귀1passed, py_compile/diff-check통과. 상세 verified-summary는 backend/artifacts/uniform-fatal-current-thread-v1에 보존했다.

## 16. 전체 코퍼스의 검색 방식과 고정 문맥 답변 비교 (2026-10-10)

PDF 10개/1,953페이지에서 얻은 PyPDF/recursive와 Docling/page를 Gemini embedding-2 3072차원으로 비교했다. 개발 40문항(20사실 그룹), 원질문과 고정 번역, 후보20/반환4/전달문맥6,000자를 유지했다. Dense는 로컬 exact cosine이며 Pinecone 요청 지연이 아니다. BM25는 Kiwi, Hybrid는 query별 및 최종 RRF(k=60)이다. 결과는 실제 답변에 전달한 문맥으로 채점했다.

| 구성 | 검색 | 페이지 적중 | 핵심 구절 적중 | MRR |
|---|---|---:|---:|---:|
| PyPDF/recursive | Dense | 75% | 67.5% | 0.6375 |
| PyPDF/recursive | BM25 | 27.5% | 25% | 0.1708 |
| PyPDF/recursive | Hybrid | 80% | 75% | 0.5604 |
| Docling/page | Dense | 52.5% | 50% | 0.4646 |
| Docling/page | BM25 | 40% | 40% | 0.2958 |
| Docling/page | Hybrid | 60% | 57.5% | 0.5292 |

두 Hybrid의 고정 문맥으로 Gemini 3.8 Flash가 답변하고 별도 Gemini 3.1 Pro Preview가 Ragas 0.2.15 faithfulness/context_recall을 채점했다. 각각40/40 유효, 실패0, 채점불가0이다.

| 구성 | Faithfulness | Context recall | 근거 부족 응답 |
|---|---:|---:|---:|
| PyPDF/recursive Hybrid | 0.996875 | 0.775 | 4/40 |
| Docling/page Hybrid | 0.964286 | 0.600 | 11/40 |

Faithfulness만으로 답변 정확성을 주장할 수 없다. 답변 보류가 포함되며 참조답변의 주장 회수와 함께 읽어야 한다. Docling/page는38/40문항에서 일부 문맥이 잘렸다. 이 실험은 현재 page/6k 조건의 결과이며 Docling 자체의 열등함이나 모든 표·그림 평가를 뜻하지 않는다. PyPDF Hybrid는 Dense보다 근거 적중이 높지만 MRR은 낮았다. 다음 Jev 비교 대상으로 PyPDF/recursive Hybrid를 고정하며 운영 설정은 변경하지 않았다.

재현: backend에서 `venv/Scripts/python.exe scripts/eval/compare_search_modes.py --output artifacts/search-modes-v2`, `venv/Scripts/python.exe artifacts/generate_search_mode_answers.py`, `venv/Scripts/python.exe scripts/eval/score_saved_answers.py --answers artifacts/search-modes-v2/pypdf-recursive-hybrid/answers-none.json` (Docling도 같은 방식). 입력/벡터/코드 SHA, 사례별 원본은 artifacts/search-modes-v2에 보존한다. 벡터 cache identity와 frozen candidate parity를 fail-closed로 검사한다. LangSmith 생성·judge trace와 로컬 재생 평가를 실서비스 지연으로 혼동하지 않는다.

독립 최종 답변 평가, 세 번 반복, 요청 전체 p95/실제 비용, Agent 목표 달성은 아직 이 결과의 범위 밖이다.

### 동일 후보 Jev 리랭킹 결과 및 결정

PyPDF/recursive Hybrid의 검색 후보20개와 번역을 고정하고 Jev 1.13.0으로 관련성을 각각 평가했다. 40문항/800호출, fallback0. 같은 생성 모델·QA 프롬프트·별도judge로40답변을 채점했다.

| 항목 | 리랭킹 없음 | Jev |
|---|---:|---:|
| 핵심 구절 적중 | 75% | 80% |
| 페이지 적중 | 80% | 80% |
| MRR | 0.5604 | 0.6500 |
| Ragas faithfulness | 0.996875 | 0.968750 |
| Ragas context recall | 0.7750 | 0.8125 |
| 근거 부족 응답 | 4/40 | 2/40 |
| 추가 리랭킹 호출/질문 | 0 | 20 |
| 추가 리랭킹 평균/p95 | 0 | 7.55초/8.04초 |

Jev의 토큰 사용량은 입력655,031/출력29,600이다. 실제 청구금액이나 전체 요청 지연 절감은 측정하지 않았으므로 비용 절감으로 해석하지 않는다. 사실그룹 단위 paired bootstrap(2,000회)의 구절 적중 차이95% CI는-5~15%p, faithfulness -8.44~0.63%p, context recall -12.5~20%p다. 작은 개발셋의 한 번 실행이며 반복3회·독립 최종평가는 아니다. 현재 품질 비열등성/지연 또는 비용20%절감 채택기준을 증명하지 못했다. **RAG Jev는 운영 비활성 유지, PyPDF/recursive 3072와 리랭킹 없음 유지. Hybrid는 다음 독립 검증 우선 후보이며 운영 설정은 변경하지 않았다.** Docling은 표/그림 강점을 별도 평가할 후보로 남긴다. 이번결과는 parser와chunking이 함께 달라진 조합평가이지 파서단독 우열판정이 아니다.

총 답변120개/240metric이 모두유효, 평가실패0/채점불가0. 수정 후210테스트통과/1건skip/기존warning3, 두runner구문검사 및 diff-check통과. 보조요약 UTF8/CP949 오류와 LangSmith 조회500건 제한HTTP400은 로그·공식문서 확인 후 수정/재검증했다. 모델실험 자체의 API실패나Jevfallback은 없었다. 이전Docling장시간native오류는 이번실험에서 재파싱하지 않았으며 근본해결 완료라고 주장하지 않는다.

재현 추가: `venv/Scripts/python.exe scripts/eval/compare_frozen_jev.py --directory artifacts/search-modes-v2/pypdf-recursive-hybrid`, `venv/Scripts/python.exe artifacts/generate_jev_search_answers.py`, `venv/Scripts/python.exe scripts/eval/score_saved_answers.py --answers artifacts/search-modes-v2/pypdf-recursive-hybrid/answers-jev.json`, `venv/Scripts/python.exe artifacts/summarize_search_modes.py`. 공개요약: docs/rag_experiments/search_modes_summary_v1.json. 중단시identity일치성공사례만재사용하고 실패는진단후한번만재시도한다.

다음: Agent/안전 골드 보완 → Supervisor의최초위임과전문Agent의도구선택을서로분리한Gemini/Jev비교 → 독립최종RAG/Agent평가(운영후보고정후) → 실제스트리밍/DeepAgent/MCP/kind → 기능검증후Cue참고UI. 기존1주범위,후보제한과HITL/권한/예산가드레일을유지한다.
# 17. Agent 의사결정·안전 고도화 (2026-10-10)

이번 단계는 [Agent 실험 안내](docs/agent_experiments/README.md)와 [합성 gold 60개](docs/agent_experiments/gold_agent60_v2.json)를 추가했다. 결정 30개(개발20/heldout10), 흐름10개(8/2), 안전20개(16/4)를 분리한다. 결정은 동일 시나리오 3회 반복, 흐름은 1회 파일럿이며 반복을 독립 표본으로 세지 않는다. RAG60을 합친 120개 목록은 평가 자산 목록이다. 기존 RAG heldout은 이전 임베딩 실험에 사용됐으므로 전체120이 새로운 독립 평가라는 뜻이 아니다.

AgentEvals trajectory subset/superset와 자체 인자·권한·최종 상태·HITL 계약을 함께 사용한다. 고정 next-action 실험과 실제 Agent 루프/합성 IO 흐름을 구분하고, provider 호출·usage·fallback·공유 예산·LangSmith trace를 기록한다. 실제 DB 저장은 차단하며 쓰기 제안은 pending만 생성한다. 안전20개는 악성 scripted 모델로 코드 경계를 검사하므로 실제 LLM 안전 일반화·임상 승인·DB 원자성의 증거가 아니다.

평가 도구의 v1 binding 오류는 이전 tool schema를 후속 finish에 남겼다. 테스트로 재현하고 별도 binding wrapper로 수정했으며 v1을 채택 근거에서 제외하고 v2 전체 재실행했다. 누락 양 질문 검사와 Validator raw usage 수집도 보완했다. 원본 snapshot/코드·골드 SHA/원점수는 보존한다.

| 고정 의사결정 실험 | Gemini 계약 통과 | Jev 포함 계약 통과 | Jev 자체 선택 정확도 | Jev fallback |
|---|---:|---:|---:|---:|
| 개발 Supervisor, 10문항×3 | 30/30 | 30/30 | 9/30 (30%) | 30/30 |
| 개발 도구 선택, 10×3 | 30/30 | 30/30 | 30/30 | 6/30 |
| 미사용 Supervisor, 5×3 | 15/15 | 15/15 | 9/15 (60%) | 15/15 |
| 미사용 도구 선택, 5×3 | 15/15 | 15/15 | 15/15 | 2/15 |

Jev 포함 성공은 fallback Gemini의 성공을 포함한다. 미사용 Supervisor p95는 Gemini 6.01초/Jev 6.90초, 도구 선택은4.82/5.16초였고, Jev 경로는 인자 생성을 위해 Gemini까지 호출하므로 총 모델 호출이 15→30으로 늘었다. confidence0.9는 고정했고 heldout을 보고 낮추지 않았다. 운영 채택의 p95 또는 비용20% 개선을 입증하지 못했으므로 Gemini를 기본으로 유지한다. 지연은 합성 벤치마크이며 실제 전체 서비스 지연이 아니다. 실제 청구 달러 비용은 검증하지 않았다.

미사용 흐름 v2는 Gemini와 Jev Supervisor가 각각1/2, Jev tools가2/2 목표 달성했다. 실패 로그는 CSV 식품 DB 영양값을 Validator가 RAG 근거 누락으로 거절하고, 빈 검색이 반복돼 모델12회 한도에 도달한 것을 보여준다. 식품 영양 수치와 지침 근거를 구분하는 Validator 지시를 보강했다. 수정 후 v3 흐름은 **재시험**이며 독립 최종 평가로 재표기하지 않는다. 원래 실패 결과는 보존한다. 이 수정은 목표·알레르기·사용자 제약과 전략 변경의 지침 검증을 유지한다.

결과 원본은 `backend/artifacts/agent-*-v2/analysis.json`, 수정 후 흐름은 `agent-flow-*-v3/analysis.json`, 공개 요약은 [summary_v1.json](docs/agent_experiments/summary_v1.json)에 남긴다. 다음 단계는 실제 RAG 근거 판본/충돌 정책을 Agent Validator·HITL·쓰기 차단까지 연결하고, 새 시나리오로 통합 검증하는 것이다. 이후 실제 스트리밍→Weekly Deep Agent/MCP→컨테이너/kind→기능 검증 후 Cue 참고 UI 순서를 유지한다.

수정 후 v3 흐름 결과(파일럿 1회, 독립 최종 평가 아님):

| 구성 | 개발 흐름 | 수정 후 추가 흐름 | 개발 p95 | 개발 전체 모델 호출 |
|---|---:|---:|---:|---:|
| Gemini | 8/8 | 2/2 | 21.20초 | 33 |
| Jev Supervisor + Gemini | 8/8 | 2/2 | 23.72초 | 41 |
| Jev tools + Gemini | 7/8 | 1/2 | 21.79초 | 52 |

Jev-tools의 개발 실패는 네트워크 장애 주입 후 검색 재시도에 성공했지만 이후 Gemini가 제공되지 않은 `get_user_profile`을 요청했고, 추가 Jev 호출과 함께 공유 모델 예산을 소진한 사례다. 서버가 요청을 거절하고 쓰기 없이 종료했다. 예산을 늘려 통과시키지 않았으며 현재 Jev 구성의 회복 능력 한계로 기록한다. 추가 흐름 실패는 LangSmith에서 확인한 Gemini504이며 별도1회 재확인은 성공했다. 첫 실패 점수는 유지한다. 개발 Jev Supervisor의 `invalid_response`는 fallback 성공했지만 최초 원응답이 없어 세부 필드 원인은 미확정이다. 별도 원응답 저장 진단 호출은 정상으로, 최초 오류 해결 증명으로 사용하지 않는다.

최종 검증: 백엔드220통과/1제외/기존경고3, py_compile 및 git diff --check 통과. 새로운 프론트 변경이 없어 이번 단계 프론트 빌드는 재실행하지 않았다. 안전 scripted20/20, 실제 trace 저장 확인. 실제 DB 트랜잭션·프로세스 재시작·SSE·임상 정책 승인은 이 단계 완료 범위가 아니다.

# 18. 근거 정책을 실제 전략 변경 경계에 연결

`strategy_evidence.py`는 기존 `resolve_claims`를 재사용한다. 검토된 정책·명시적으로 확인된 일반 성인 적용 대상·최신 판본의 실제 인용·단위 및 수치 범위가 모두 통과해야 전략 제안을 Validator에 전달한다. 정책 receipt/catalog SHA/선정·충돌 근거는 proposal에 보존하고 선택 이유를 HITL 설명에 표시한다. 확정 직전에도 재계산하므로 근거 정책이 바뀌었거나 충돌하면 전략 UPDATE/INSERT 전에 차단한다. 구형 직접 저장 도구와 기존 사용자의 재온보딩 전략 덮어쓰기 우회도 막았다.

운영 claim catalog는 아직 비어 있다. 합성 테스트 수치를 실제 식단 정책으로 활성화하지 않았으며, 현재 자동 수치 전략 변경은 보류한다. 기존 목표 기반 추천·식사 기록은 유지한다. 신규 가입 초기 계산, 실제 자료의 정책식/적용 조건 검토, 적용 대상 저장/입력 경로, 실제 DB 통합 검증은 후속 필수 작업이다. 전체 서비스 또는 임상 정책 검증 완료로 해석하지 않는다.

테스트: 근거 공백·미검토·충돌·구판·잘못된 해시·단위·범위·대상·정책 변경·Agent/Validator/HITL 설명·저장 우회·승인된 정상 저장을 합성 catalog/mocked DB로 확인했다. 백엔드 **236통과/1제외**, 기존 경고3. 실제 외부 API/DB 변경 없음. 상세 설계·한계: [EVIDENCE_INTEGRATION.md](docs/agent_experiments/EVIDENCE_INTEGRATION.md).

# 19. 초기 유지 기준선의 실제 DB/HITL 연결
2026-10-10: 18장의빈catalog는이번단계KDRI2025원문대조유지식/비율4claims로갱신했다. personalized maintenance_ratio와계산입력receipt를사용하며감량·증량처방은미활성. 신규POST /users/onboarding은profile/pending동일transaction,명시확정후strategy저장. 실제Supabase additive JSONB컬럼적용,합성사용자의pending복구/취소/중복/기존보존/변경차단/실패rollback검증성공(합성데이터롤백). Backend259passed1skipped3warnings,frontend8passed/build성공. 조회및실제DB계약검증이며임상효과/독립LLM최종평가완료아님. 상세 [ONBOARDING_HITL.md](docs/agent_experiments/ONBOARDING_HITL.md).

# 20. 목표 적용 조건과 보류 계약
감량/증량 자동칼로리조정은미활성. 목표방향·날짜·요청산술/추천구분·receipt 목표변경·Agent완료오표기차단13개추가,전체272pass1skip3warnings. realDB합성목표변경시승인차단/원자적rollback검증. 임상정책승인 또는 새로운독립Ragas평가완료아님. 상세 [GOAL_POLICY.md](docs/agent_experiments/GOAL_POLICY.md).

# 21. 현재 운영 Gemini Agent 통합 평가

2026-10-10 현재 코드와 운영 기본 Gemini 경로를 다시 실행했다. 결정 개발60/60, 결정 heldout 회귀30/30, 전체 흐름 개발8/8, 전체 흐름 heldout 회귀2/2, 악성 scripted model 안전경계20/20, 최신판본·충돌·목표정책·HITL 통합42/42다. 결정 평가는 다음 행동 정확도이고 전체 목표 달성과 구분한다. 흐름은 합성 IO로 실제 DB 쓰기가 없으며 안전 replay는 LLM 일반화 평가가 아니다.

흐름의 p95는 개발27.08초, heldout38.35초였다. 골드 최소 경로보다 추가된 전문도구 성공 호출은 개발4회, heldout2회였고 구조적 delegate 호출은 제외했다. 금지도구 성공과 무승인 domain write는0건이다. LangSmith root trace의 실험 metadata 누락을 수정한 후 smoke10건을 실험ID/caseID로 조회했고 error0/status success10을 확인했다.

첫 실행56/60은 모델 실패가 아니라 runner가구버전gold v1, analyzer가v2를 읽은 평가기 오류였다. 원본을보존하고default계약테스트후v5에서60/60. 안전평가무출력정지는faulthandler로Windows socketpair accept와sandbox loopback제약을확인했고승인된로컬실행에서20/20. 자세한 결과·재현·한계는 [AGENT_INTEGRATION_V2.md](docs/agent_experiments/AGENT_INTEGRATION_V2.md)에 기록했다. 과거 heldout은이미열어본자료이므로새로운독립최종평가라고주장하지않는다. 다음단계는새로운봉인사실·시나리오를사용한Ragas/Gemini judge와LangSmith독립최종평가다.

최종 리뷰에서 dataset SHA/snapshot과 실행 variant manifest가 분석 시 강제되지 않던 provenance 문제 2건을 발견했다. dataset SHA·snapshot·domain·split·variant가 실행 identity와 다르면 분석을 중단하도록 수정했고 관련 회귀를 포함한 전체 결과는277passed1skipped3warnings다.
## 22. RAG 최종 post-selection 평가 (2026-10-10)

파서·청킹·임베딩 차원·검색·리랭커 선택이 끝난 뒤 기존 평가 사실 그룹과
겹치지 않는 10개 사실 그룹을 한영 20문항으로 구성했다. 이전 heldout20은
차원 비교에서 이미 조회됐으므로 독립 최종셋으로 재사용하지 않았다.

고정 구성은 PyPDF/recursive, `gemini-embedding-2` 3072차원, Hybrid,
reranker 없음, top-4/6,000자다. 20/20 실행 완료, 지정 페이지·구절 Recall@4
85%, 원문 대체 페이지 adjudication 후 evidence support 95%, Ragas
faithfulness 1.00, context recall 0.95였다. 지연은 p50 11.23초, p95
25.02초였다. 실제 근거 누락 1건은 답변을 보류했다.

Ragas FactualCorrectness는 기본 0.325, 한국어 prompt adaptation과 한국어
참조 오버레이에서도 0.347이었다. 정확한 답변도 0점으로 판정한 사례가 있어
서비스 정확성 지표로 채택하지 않았다. 해당 결과와 공식 권고를 적용한 실패
분석은 evaluator calibration 사례로 보존한다. 비맹검 원문 대조 답변 정확성은
19/20이며 임상 정책 승인과 구분한다.

데이터셋 SHA는
`9182df0b969772b1e63c713f6efeaa2ada64a1dd78d1cf5350fc5586e5a807f6`, capture
identity는 `911f0cc524201b91e746`이다. 상세 조건·오류·재현 경로는
`docs/rag_experiments/RAG_FINAL_EVALUATION_V1.md`에 기록했다.

최종 리뷰 후 재현성 경계를 강화했다. 실행기는 활성 namespace·Gemini 모델·
3072차원·candidate 20과 4,139개 청크 전부의 PyPDF/recursive metadata를
검증한다. 완료 캐시는 질문·언어·참조·필수 결과가 일치할 때만 재사용하고,
실패 캐시는 누적 3회 한도 안에서 재개한다. Ragas scorer와 수동 판정은 실제
dataset/answers SHA와 capture identity가 모두 맞아야 실행된다. 재생성한
answers SHA는 `3cfed2c001a66f405052722e368d7d921137a983d03c1809aab8d33d5020b2f1`이며,
전체 회귀는 **285 passed, 1 skipped, 기존 warning 3건**이다.

## 23. 목표별 칼로리 조정 정책 (2026-10-10)

KDRI 2025 유지 에너지를 기준으로 대한비만학회 2022 식사치료의 일반 성인 감량 범위를 연결했다. BMI 23 이상, 완전한 감량 목표, 일반 성인 적용 확인과 최소 열량 기준을 통과할 때만 500 kcal 감량안을 pending strategy로 만든다. 승인 전 DB 변경은 없고 승인 직전 동일 정책·source SHA·catalog SHA를 다시 검증한다. 500~1,000 kcal 중 속도 옵션으로 상한을 선택하지 않으며, 하한과 충돌하면 임의 조정 없이 유지 기준선으로 보류한다. 증량 숫자 정책은 계속 비활성이다.

28~42일 체중 기록에서 2.5% 미만이면 생활습관 중재 검토 신호를 반환하지만 추가 자동 칼로리 변경은 0이다. Agent에는 결정적 `assess_goal_progress` 도구를 제공하고 이후 수치 변경은 기존 근거 검증과 HITL을 통과해야 한다. PDF page와 공백 정규화도 실제 Agent 검색 경로에 통일했다. 전체 백엔드는 **292 passed, 1 skipped, warning 3건**, 프론트 테스트 **8 passed**, production build 성공이다.

실제 Supabase 합성 트랜잭션에서도 감량안 -500 kcal, 승인 전 미저장, 취소·재시도, 확정·중복 방지, 기존 전략 보존, 프로필·목표 변경 차단과 실패 롤백을 확인한 뒤 전체 합성 데이터를 롤백했다.

## 24. 실행 스트리밍 회귀 검증 (2026-10-10)

- SSE parser의 1바이트 UTF-8 분할, CRLF, 오류 프레임, 불완전 종료를 검증했다.
- `stream_run_id`/`seq` 중복 제거와 마지막 수신 순번 복구를 검증했다.
- Supervisor·위임·도구 시작 이벤트가 응답 완료 전 실제 순서로 전달되는지 검증했다.
- 재접속은 최대 한 번이며 같은 실행 ID를 재사용한다. 완료 체크포인트는 그래프를 다시 실행하지 않는다.
- 전체 회귀는 backend **297 passed, 1 skipped**, frontend **11 passed**, production build 성공이다. 기존 deprecation warning 3개는 이번 변경과 무관하다.

## 25. Weekly Deep Agent와 읽기 전용 MCP (2026-10-10)

- `weekly_review` 경로에 주간 Supervisor와 최대 두 전문 Agent를 연결했다. 분석 Agent는 인증된 사용자 클로저를 통해 최근 7일 기록·프로필·측정·목표 추세만 읽고, 근거 Agent는 MCP의 공식문서 검색만 사용한다.
- MCP SDK 2.3.0 서버는 `search_foods`, `nutrition_lookup`, `search_evidence` 세 읽기 도구만 공개한다. 사용자 DB와 저장·수정·삭제 도구는 공개하지 않는다.
- 전략 변경은 Supervisor가 직접 저장하지 않고 기존 `propose_strategy`의 근거 정책·Validator를 통과한 pending proposal로만 만든다. 실제 적용은 기존 HITL 승인과 승인 직전 정책 재검증을 거친다. `GET /report/weekly`는 읽기 전용 policy와 대화 lock을 강제하며, 변경 제안은 `/chat`의 명시적 `weekly_review`에서만 허용한다.
- Deep 실행은 하위 Agent와 같은 durable budget을 공유하며 모델 20회, 도구 30회, 180초, 전문 Agent별 1회 위임으로 제한한다.
- MCP 초기 등록은 bare `dict` 반환형 때문에 `InvalidSignature`가 발생했다. SDK 로그에 따라 `dict[str, Any]` 출력 스키마로 수정했고 실제 SDK `call_tool` structured content를 회귀 테스트했다.
- 검증은 신규 집중 테스트 **11 passed**, 전체 백엔드 **308 passed, 1 skipped**, 기존 deprecation warning 3건이다. 실제 운영 사용자 주간 리포트의 품질·지연과 독립 gold 평가는 아직 수행하지 않았으므로 Deep Agent 성능 개선을 주장하지 않는다.

## 26. Container·kind 배포와 장애 복구 (2026-10-10)

- 동일 이미지에서 API, scheduler worker, read-only MCP를 분리하고 API는 2 replicas로 실행했다. 실제 kind 결과는 API 2/2, worker 1/1, MCP 1/1 Ready였다.
- API rollout restart 전후 Pod 이름이 모두 바뀌었고, 교체된 두 Pod가 각각 Supabase `AsyncPostgresSaver` 테이블 준비와 LangGraph 빌드를 완료했다. 클러스터 내부 서비스 호출은 `/health` 200과 MCP endpoint 도달을 확인했다.
- 첫 배포는 `runAsNonRoot`가 문자열 이미지 사용자 `app`을 검증하지 못해 `CreateContainerConfigError`가 났다. 이미지에서 확인한 UID/GID 999를 매니페스트에 명시하고 회귀 테스트를 추가해 해결했다.
- kind 준비 중 Docker WSL 데이터 디스크 쓰기가 실패해 ext4가 read-only로 재마운트됐다. 커널 로그의 `hv_storvsc` I/O 오류, aborted journal, `Remounting filesystem read-only`와 C 드라이브 약 3.2GiB 잔여를 원인 증거로 사용했다. Docker 런타임의 stale `dockerInference`/Secrets Engine AF_UNIX 소켓도 백엔드 로그로 분리 진단해 런타임 디렉터리를 보존 이름으로 이동하고 재생성했다.
- Windows 호스트의 async pytest는 Python 3.13 `socket.socketpair()`가 localhost `accept()`에서 대기하는 스택을 남겼다. 애플리케이션 테스트 실패로 해석하지 않고 동일 소스를 Linux 이미지에 read-only mount해 전체 회귀를 수행했다: **313 passed, 1 skipped, 기존 deprecation warning 3건**.
- 상태·호출 예산·중복 확정은 집중 회귀 17개와 기존 원자적 proposal/checkpointer 테스트로 검증했다. 실제 인증 사용자의 진행 중 요청을 강제 재시작하는 실험은 데이터 오염 위험 때문에 이번 로컬 복구 데모에 포함하지 않았다.
- 독립 리뷰에서 read-only MCP가 공용 Secret 전체를 받고 인증 없는 NodePort로 노출되는 최소 권한 위반을 발견했다. MCP Secret을 Gemini/Pinecone 두 키로 분리하고, Kubernetes Service를 ClusterIP로 제한했으며, Compose 공개 주소도 `127.0.0.1`로 고정했다. 실제 Secret의 키 이름, 새 Pod 1/1 Ready, 내부 MCP 응답을 재검증했다.
- 검색 런타임이 Pinecone 인덱스 부재 시 새 인덱스를 만들던 경로도 차단했다. 인덱스 생성은 명시적 build 경로에서만 가능하고, MCP를 포함한 일반 검색은 fail-closed한다.

## 27. Cue 참고 스트리밍 UI (2026-10-10)

- 실제 SSE `phase`/`label`만 진행 타임라인에 누적하고 완료 답변에는 접을 수 있는 검토 과정으로 보존한다. 내부 추론이나 실행하지 않은 단계를 생성하지 않는다.
- 전략 제안은 칼로리·영양소·적용일과 근거의 출처·페이지·판본·적용 대상을 표시하고, 기존 proposal ID/version HITL 경계를 그대로 사용한다.
- 연결 실패는 사용자가 재요청할 수 있는 오류 상태로 표시하며, 불완전 응답을 성공처럼 보이지 않는다.
- 컴포넌트 및 SSE 통합 회귀를 포함해 프론트 **15 passed**, production build 성공이다. Playwright 개발 프리뷰에서 데스크톱과 390px 모바일을 확인했고 콘솔 error/warning은 0건이었다. 프리뷰용 인증 우회 코드는 검증 후 제거했다.

## 28. 실제 인증 E2E와 RAG 런타임 정합성 (2026-10-11)

- 실제 Supabase 합성 사용자가 가입·온보딩·전략 확정·식사 기록 확정을 수행했다. 확정 전 전략/식사 저장 0건, 확정 후 활성 전략 1건과 식품 2건(244.2 kcal), 동일 결정 재전송 뒤에도 식사 2건으로 HITL·멱등성을 확인했다.
- 최종 평가에서 채택한 `PyPDF/recursive + Gemini 3072 + Hybrid + reranker 없음`과 달리 런타임 기본값이 FlashRank를 켜고 있었다. 동시에 kind ConfigMap의 namespace와 chunks 경로도 구형이었다. 활성 build identity를 배포 설정에 연결하고 `RAG_USE_RERANK=false`를 기본값으로 만들었다. 수정 전에는 FlashRank 로드 중 1 GiB Pod가 OOMKilled됐고, 수정 후 실제 4,139청크 BM25+Pinecone 검색은 grounded=true/max_score=0.862, API 2개 Pod restart 0으로 완료됐다.
- 근거 검색 실패 시 모델이 저녁 30~35%를 일반 지침처럼 생성한 사례와, 검색 성공 뒤에도 “끼니별 고정 비율 없음”과 “약 30% 권장”을 함께 말한 모순을 발견했다. 검색 실패 또는 검색 근거에 끼니별 비율이 없으면 해당 비율에서 계산한 칼로리 권고를 최종 출력에서 보류하도록 결정적 가드를 추가했다.
- 명백한 식단 추천에서 Evidence Agent와 Meal Agent가 차례로 같은 근거를 찾으며 모델 12회 한도를 소진했다. Meal Agent가 근거 도구를 보유하므로 이 요청 유형의 위임 후보를 Meal Agent로 좁혔다. Supervisor의 tool calling은 유지하며 근거 설명만 묻는 요청의 Evidence Agent도 유지한다. 최종 실제 요청은 Meal Agent 1회 위임, model 12/12·tool 17/20·99.76초에 완료됐다. 품질 가드는 통과했지만 예산 여유와 지연은 후속 최적화 대상으로 남긴다.
- 실제 UI는 요청 중 실제 SSE 단계가 누적되고 완료 뒤 접힌 검토 과정으로 보존됐다. 설계 프리뷰의 전략 제안 카드는 전략 proposal이 생성된 경우에만 나타나므로 일반 설명/보류 응답에는 표시되지 않는다. 이전 `Failed to fetch` 3회는 API rollout 때 끊어진 로컬 `kubectl port-forward`의 누적 콘솔 기록이며 새 Pod의 애플리케이션 오류로 분류하지 않는다.
- 최종 회귀: backend **318 passed, 1 skipped**, frontend **15 passed**, production build 성공. 알려진 경고는 Pydantic class Config 및 LangChain 구형 패키지 deprecation 3건이다.

## 29. Agent 호출·지연 최적화 (2026-10-11)

- 동일 정규화 질의의 공식 근거 검색 결과와 음식 후보를 요청 실행 안에서 재사용한다. 동일 food ID·중량의 영양 계산 quote도 다시 CSV를 읽지 않는다. 런타임은 성공한 동일 인자의 읽기 도구를 한 번만 실행하고 이후 결과를 재생한다. proposal·delegate 등 효과가 있는 도구와 실패 결과에는 캐시를 적용하지 않는다.
- Supervisor가 전문 Agent의 성공 응답을 받은 뒤 같은 내용을 다시 요약하기 위해 LLM을 한 번 더 호출하던 경로를 제거했다. 최초 Agent 선택은 계속 모델이 tool calling으로 수행하며 전문 Agent 내부 도구 선택·실패 피드백·HITL 경계도 유지한다.
- 변경 전 고정 개발 흐름 v2와 최적화 후 같은 개발 8개 1회 실행을 비교했다. 목표 달성률은 모두 8/8, 정책 위반은 0건이었다. p50은 16.64→9.31초(-44.0%), p95는 24.92→13.69초(-45.1%), 총 모델 호출은 35→30(-14.3%)이었다. 이전 artifact에는 총 tool_calls 필드가 없어 전후 도구 호출 감소율은 주장하지 않는다. 최적화 후 도구 호출은 27회다.
- 기존 heldout 회귀 2개도 2/2 성공, 정책 위반 0, p95 23.69초였다. 모든 개별 개발/heldout 흐름은 모델 8회 이하, 도구 12회 이하, 60초 이하 목표를 충족했다. 이 heldout은 과거에 이미 열어본 자료이므로 새로운 독립 최종 평가가 아니다.
- 실제 인증 E2E에서 관찰한 12/12 모델·17/20 도구·99.76초 요청은 변경 전 기준선으로 유지한다. 최적화 후 실제 사용자 재측정은 합성 사용자 재생성 비용과 외부 변동을 분리하기 위해 다음 독립 E2E에서 수행하며, 이번 합성 fixture 결과를 실제 서비스 p95로 표현하지 않는다.
- 원본은 `backend/artifacts/agent-flow-optimized-v1`과 `agent-flow-optimized-heldout-v1`에 보존했다. 전체 회귀는 **322 passed, 1 skipped**, 기존 deprecation warning 3건이다.

## 30. 새로고침 화면 상태 복원 (2026-10-11)

- 인증된 `GET /session/restore/{thread_id}`는 LangGraph 체크포인트, 유효한 pending proposal, 최근 대화, 오늘 섭취 열량과 활성 목표를 읽기만 한다. 복원 중 `ainvoke`를 호출하지 않으므로 완료된 Agent 실행이나 도구 호출을 반복하지 않는다.
- 프론트는 첫 mount에서 한 번만 복원하고, 메시지·proposal 카드·오늘 섭취량을 기존 화면 상태에 반영한다. proposal은 `pending` 상태일 때만 확인 카드로 복원하며 승인·취소는 기존 proposal ID/version 멱등성 경계를 그대로 사용한다.
- 현재 `chat_history` 스키마에는 thread ID가 없어 최근 메시지는 같은 사용자의 최근 20건을 복원한다. 체크포인트와 proposal은 요청 thread로 제한된다. 멀티 thread UI를 공개할 때는 `chat_history.thread_id` 마이그레이션과 필터를 선행해야 한다.
- TDD에서 복원 API 부재와 프론트 미복원을 각각 실패로 확인한 뒤 구현했다. 최종 회귀는 backend **323 passed, 1 skipped**, frontend **16 passed**, production build 성공이다. 기존 Pydantic/LangChain deprecation warning 3건과 Node `fs.F_OK` deprecation은 기능 실패가 아니다.

## 31. Weekly Deep Agent·MCP 장애 통합 평가 (2026-10-11)

- 정상 경로 외에 부분 기록, MCP 장애, 모델 호출 예산 소진, 동일 우선순위 근거 충돌, MCP 쓰기 도구 요청의 다섯 시나리오를 독립적으로 주입했다.
- 부분 기록은 `record_completeness=unknown`을 유지하고 미기록을 0 kcal로 바꾸지 않았다. MCP 장애는 구조화된 `tool_failed` 피드백을 Agent에 전달하고 수치 변경을 보류했다. 예산 소진은 설정된 첫 모델 호출 뒤 `blocked`로 종료됐다.
- 해결되지 않은 근거 충돌은 `evidence_policy_blocked`에서 strategy proposal 생성을 차단했다. MCP 공개 allowlist 밖의 `save_meal` 요청도 거절됐다. 다섯 시나리오 모두 승인 전 저장 0건, 정책 위반 0건으로 통과했다.
- Windows Python 3.13 실행은 기존 `asyncio/socketpair` 대기 증상을 재현했다. 테스트 assertion 실패로 오인하지 않고 기존 `metadiet:local` Linux 이미지에 저장소를 read-only mount해 검증했다: Weekly/MCP 집중 테스트 **15 passed**.
- 이번 결과는 scripted model을 사용한 orchestration·안전 계약 평가다. 실제 Gemini 답변 품질·지연·비용은 주장하지 않으며 다음 독립 최종 Agent/Ragas/LangSmith 실행에서 별도로 측정한다. 원본 요약은 `backend/artifacts/weekly-deep-integration-v1/summary.json`이다.
- 저장소 전체를 read-only mount한 Linux 컨테이너 최종 회귀는 **327 passed, 1 skipped**다. Pydantic/LangChain deprecation 3건과 read-only pytest cache warning 1건은 결과에 영향을 주지 않았다.

## 32. 독립 Agent 최종 평가·LangSmith 관측 (2026-10-11)

- 기존 개발/heldout 문항과 다른 8개 flow 계약을 `final_agent_flow_v1.json`으로 먼저 동결하고, 실행 뒤 문항·코드 SHA를 artifact identity에 고정했다. 모두 합성 공개 fixture이며 임상 승인 자료나 실제 사용자 데이터가 아니다.
- Gemini 운영 경로만 각 1회 평가해 **8/8 목표 달성, 정책 위반 0, 승인 전 domain write 0**을 확인했다. p50 16.71초, p95 28.05초, 모델 28회, 도구 24회였다. 모든 사례가 60초·모델 8회·도구 12회 개별 목표 안에 있었다.
- 최소 경로 대비 추가 읽기 2회는 일반 기록 사례의 선제 `read_intake` 1회와, 의도적으로 첫 음식 검색 장애를 주입한 복구 사례의 재시도 1회다. 후자는 필요한 복구 호출이며 두 경우 모두 목표·안전 계약을 위반하지 않았다.
- LangSmith 프로젝트에서 experiment=`agent-final-independent-v1`인 root trace **8개**, 오류 **0개**, case ID 8개를 API로 다시 확인했다. trace metadata에는 case ID, heldout split, Gemini variant, repeat, 실험명이 들어간다.
- Gemini SDK가 Pydantic 도구 스키마의 `additionalProperties` 키를 지원하지 않아 무시한다는 경고가 반복됐다. 모델 측 표현 제약 일부가 빠질 수 있으나 서버의 strict Pydantic validation이 모든 실제 인자에 재적용되므로 권한·인자 검증 경계는 유지된다.
- RAG 최종 품질은 22장의 독립 20문항 결과(근거 support 95%, Ragas faithfulness 1.00/context recall 0.95)를 고정 사용한다. Agent 실행에 맞춰 같은 RAG 문항을 다시 튜닝하지 않았다. Agent 원본은 `backend/artifacts/agent-final-independent-v1`, RAG 원본은 `docs/rag_experiments/RAG_FINAL_EVALUATION_V1.md`에 보존했다.

## 33. 체크포인터 연결 풀 안정성 (2026-10-11)

- `AsyncPostgresSaver`는 단일 장기 연결 대신 `AsyncConnectionPool(min_size=1, max_size=10, timeout=15)`을 받는다. 각 체크포인트 작업은 풀에서 연결을 대여하므로 한 연결의 중단이 모든 후속 요청을 영구 차단하는 단일 실패점이 줄었다.
- lifespan은 pool open을 기다린 뒤 checkpointer schema setup과 graph compile을 수행하고, 종료 시 pool context를 닫고 전역 graph 참조를 해제한다. 가짜 pool/saver 회귀 테스트로 설정값, 준비 순서, graph 주입과 정리를 검증했다.
- 실제 Supabase 최대 연결 수에 맞춘 max_size 조정, pool timeout/대기열 지표와 DB 전체 장애 시 복구 시간은 배포 부하 시험에서 확정해야 한다. 연결 풀 적용만으로 DB 장애 자체가 사라진다고 주장하지 않는다.
- 최종 Linux 컨테이너 전체 회귀는 **328 passed, 1 skipped**다. 기존 Pydantic/LangChain deprecation 3건과 read-only pytest cache warning 1건만 남았다.

## 34. 대화 분리·실제 DB 풀·개인정보 관측 경계 (2026-10-11)

- `chat_history.thread_id` additive migration을 실제 Supabase에 적용했다. 기존 행은 임의의 현재 대화에 섞지 않고 `legacy`로 격리했다. 검증 결과 컬럼은 NOT NULL/default=`default`, `(user_id, thread_id, created_at desc)` 인덱스 1개, 빈 thread 행 0개다.
- 신규 사용자·Assistant 대화와 scheduler reminder는 thread ID를 저장한다. 화면 복원은 user ID와 요청 thread ID를 함께 필터링하므로 다른 대화의 메시지를 섞지 않는다.
- 실제 Supabase에서 사용자 데이터를 읽지 않는 `SELECT 1` 기반으로 20개 동시 요청을 실행했다. 모두 성공했고 총 동시 구간은 0.4292초였다. 10초 쿼리를 0.2초 뒤 취소한 다음 새 쿼리는 0.0314초에 성공했다. 종료 시 pool size/available은 6/6, waiting은 0이었다. 원본은 `backend/artifacts/postgres-pool-recovery-v1.json`이다.
- 첫 migration 명령은 PowerShell이 인라인 SQL의 따옴표를 잘못 파싱해 DB 접속 전에 실패했다. SQL·자격증명을 셸 문자열에서 분리한 `apply_chat_history_thread_migration.py`로 해결했고 동일 migration은 재실행 가능하다.
- stdout의 사용자 메시지·응답·OCR 수치·검색 질의·검증 본문을 제거하고 예외 타입만 남겼다. SSE 내부 오류도 예외 원문 대신 일반 오류 문구를 반환한다.
- 운영 LangSmith는 입력·출력 숨김이 기본이며, metadata의 thread ID는 내부 사용자 UUID가 포함되지 않은 안정적인 SHA-256 가명 ID다. 공개 합성 fixture 평가만 별도 Client에서 입력·출력을 허용한다.
- 최종 Linux 컨테이너 회귀는 **333 passed, 1 skipped**다. 운영 기준은 `docs/OPERATIONS_PRIVACY.md`에 기록했다. 실제 보존 기간·삭제 기한·법적 문구는 출시 국가와 제품 정책 확정 전까지 미확정으로 남긴다.

## 35. 계정 삭제 전파·실행 경쟁 조건 검증 (2026-10-11)

- `DELETE /users/me`는 본문에 정확한 `confirmation="DELETE"`를 요구한다. 인증 주체의 내부 사용자 행을 삭제하면 FK `ON DELETE CASCADE`로 식사·인바디·전략·대화·proposal·실행 예산을 한 트랜잭션에서 제거하고, 사용자 FK가 없는 LangGraph checkpoint 3개 테이블은 `{user_id}_` prefix로 명시 삭제한다.
- Supabase Auth는 Postgres 트랜잭션에 포함할 수 없으므로 앱 데이터 commit 뒤 Auth Admin 삭제를 수행한다. Auth 호출만 실패하면 `auth_deletion_pending` 503을 반환하며, 이 endpoint는 내부 사용자 조회가 아닌 JWT `sub`로 인증하므로 같은 토큰으로 Auth 삭제를 재시도할 수 있다.
- 진행 중 Agent가 삭제 직후 checkpoint를 다시 만드는 경쟁 조건을 막기 위해 대화 실행은 사용자 단위 shared advisory lock을, 삭제는 같은 키의 exclusive advisory lock을 사용한다. 대기하던 실행은 lock 획득 후 사용자 존재를 다시 확인하고, 이미 삭제됐으면 graph에 진입하지 않는다. 기존 thread별 exclusive lock은 함께 유지한다.
- 실제 Supabase에는 고유 합성 Auth 사용자·앱 사용자·대화·checkpoint와 대조 사용자를 생성해 검증했다. 삭제 뒤 대상은 Auth/user/chat/checkpoint 모두 0, 대조 사용자는 user/chat/checkpoint 모두 1이었다. 검증 종료 시 대조 fixture도 정리했다. 원본 요약은 `backend/artifacts/account-deletion-v1.json`이다.
- 검증 중 첫 실패는 직접 실행 스크립트의 Python import path 누락, 두 번째 실패는 Windows ProactorEventLoop와 psycopg async 비호환이었다. 각각 backend 경로 명시와 운영 서버와 동일한 WindowsSelectorEventLoopPolicy로 해결했으며, 두 실패 모두 `finally` 정리 경로로 합성 데이터를 제거했다.
- Linux 컨테이너 전체 회귀는 **339 passed, 1 skipped**다. 남은 warning은 Pydantic/LangChain deprecation 3건과 read-only pytest cache 1건이다.

## 36. 계정 삭제 UI·최근 재인증 경계 (2026-10-11)

- 설정 탭에 계정 삭제 화면을 추가했다. 현재 비밀번호와 정확한 `DELETE` 확인값을 모두 받은 뒤 Supabase `signInWithPassword`로 새 세션을 만들고, 새 access token으로만 `DELETE /users/me`를 호출한다. 성공하면 Supabase JS의 local sign-out과 앱 상태 초기화를 수행한다.
- 서버는 자동 refresh로 새로워지는 JWT `iat`를 최근 재인증 증거로 사용하지 않는다. JWT의 `amr` 중 `method=password`인 최신 timestamp가 5분 이내인지 확인하고 `session_id`를 요구한다. 삭제 트랜잭션은 같은 session ID와 auth user ID가 `auth.sessions`에 실제 존재하는지도 검사한다.
- Auth Admin 삭제만 실패한 `auth_deletion_pending` 상태는 별도 재시도 버튼으로 유지한다. 재시도 전에 5분이 지나면 입력 화면으로 돌아가 비밀번호를 다시 요구한다. 현재 제품에 구현된 이메일·비밀번호 인증만 지원하고 향후 OAuth 로그인에는 provider별 재인증 흐름이 추가될 때까지 삭제 버튼을 잠근다.
- Auth 삭제 부분 실패 중 남은 JWT로 온보딩을 호출해 앱 프로필을 재생성하는 경로를 차단했다. 삭제 트랜잭션은 auth ID의 SHA-256 hash tombstone을 먼저 만들고, onboarding 트랜잭션은 같은 lifecycle advisory lock의 shared mode를 획득한 뒤 tombstone을 검사한다. Auth 삭제 성공 후 tombstone을 제거하며, 제거 DB 호출만 실패하면 hash를 남겨 fail-closed한다. 성공 뒤에도 아직 만료되지 않은 JWT가 온보딩에 들어오지 못하도록 Auth `/user`에서 계정 존재를 재검증한다.
- 실제 Supabase 합성 사용자의 비밀번호 로그인 JWT에서 password AMR timestamp와 session ID를 확인했고, 활성 세션 검증 뒤 Auth/user/chat/checkpoint가 모두 0이 됐다. 대조 사용자의 user/chat/checkpoint는 모두 1로 유지됐다. 갱신된 집계는 `backend/artifacts/account-deletion-v1.json`에 있다.
- 첫 실제 검증은 관리자용으로 캐시된 Supabase client에서 사용자 로그인을 수행해 Authorization 헤더가 사용자 JWT로 바뀌었고, 후속 Admin 삭제가 403 `User not allowed`로 실패했다. 앱 데이터는 이미 삭제됐고 합성 Auth만 남은 것을 새 관리자 프로세스로 정리했다. 검증 스크립트에서 service-role Admin client와 사용자 로그인 client를 분리한 뒤 전체 경로가 통과했다. 이 실패와 해결은 관리자·사용자 인증 컨텍스트를 같은 mutable client에 섞지 않아야 한다는 운영 사례로 기록한다.
- tombstone migration 뒤 Supabase Advisor가 기존 `users`, 식사·인바디·전략·대화 및 checkpoint 테이블의 RLS 비활성과 anon/authenticated의 광범위한 SELECT·쓰기·TRUNCATE 권한을 ERROR로 발견했다. 프론트는 이 테이블을 직접 사용하지 않으므로 RLS를 활성화하고 공개 역할 권한을 전부 회수했다. 기존 소유권 정책도 authenticated와 USING/WITH CHECK로 제한했다. 재검증에서 10개 민감 테이블은 RLS=true, anon/authenticated SELECT=false였고 Advisor ERROR는 0건이다.
- 남은 Advisor 항목은 service-only 테이블에 공개 정책이 없다는 INFO와 Supabase Auth의 leaked-password protection 비활성 WARN이다. 후자는 Dashboard 요금제·제품 정책 설정이 필요해 자동 변경하지 않았다.
- 검증: backend **348 passed, 1 skipped**, frontend **22 passed**, production build 성공. 기존 Pydantic/LangChain deprecation 3건과 read-only pytest cache warning 1건은 기능 실패가 아니다.

## 37. 실제 브라우저 전체 생명주기 E2E (2026-10-11)

- Playwright의 실제 Chromium에서 확인 완료 합성 사용자를 로그인시키고, 온보딩 입력 → 초기 전략 proposal 확인 → HITL 확정 → 식사 중량 확인 → 섭취 proposal 생성 → 새로고침 복원 → 확정 저장 → 기록 조회 → 계정 삭제를 순서대로 실행했다.
- 확인 전 섭취량은 0 kcal였고, 달걀 100g·바나나 100g proposal을 확정한 뒤 222 kcal로 바뀌었다. pending proposal은 백엔드 컨테이너 재시작 뒤에도 같은 ID/version 경계로 복원됐으며, 완료된 실행은 재수행되지 않았다.
- 첫 E2E는 과거 `metadiet:local` 이미지에 현재 `/session/restore` 라우트가 없어 404를 반환했다. 현재 작업 트리로 `metadiet:e2e` 이미지를 재빌드한 뒤 복원이 정상 동작했다. 신규 thread의 정상 404는 프론트에서 빈 상태로 처리하도록 회귀 테스트를 추가했다.
- “오늘 먹은 기록만 요약”을 `record_only` 쓰기 의도로 오분류해 `read_intake`를 차단하던 정규식을 수정했다. 조회·요약·확인 문장은 읽기 도구를 유지하고, meal 전문 Agent가 현재·최근 기록을 답할 때 먼저 조회 도구를 호출하도록 했다. 수정 전 “기록 없음”이던 답변은 같은 질문에서 222 kcal와 두 음식의 영양값을 정확히 반환했다.
- 한 번에 저장된 user/assistant 행이 같은 `created_at`을 가져 복원 순서가 뒤집힐 수 있었다. 새 행에 1µs 차이의 UTC 시각을 기록하고 기존 동률 행은 `role` 보조 정렬로 복원해 질문 → 답변 순서를 고정했다.
- 삭제 화면은 비밀번호 재인증과 `DELETE` 확인을 거쳐 200으로 완료됐고 로그인 화면으로 돌아왔다. 삭제 전에 보관한 access token으로 `/users/onboarding`을 다시 호출한 결과 401이어서 앱 프로필 재생성이 차단됨을 확인했다. 합성 Auth·앱 데이터는 이 삭제 흐름으로 정리됐다.

## 38. Compose 비루트 운영·재시작 검증 (2026-10-11)

- API·worker·읽기 전용 MCP를 현재 작업 트리로 다시 빌드했고 세 컨테이너 모두 `app` 사용자로 실행했다. API HTTP, worker 프로세스, MCP TCP healthcheck를 각각 적용해 모두 `healthy`인지 확인했다.
- 첫 실제 운영 스크립트 실행은 두 가지 이유로 실패했다. 풀 복구 스크립트는 비루트 사용자가 root 소유 `/app` 아래에 새 `artifacts` 디렉터리를 만들 수 없었고, proposal 검증 스크립트는 이미지에 migration 파일이 없었다. 이미지 빌드 시 writable `/app/artifacts`를 만들고 필요한 migration만 명시적으로 복사하도록 수정했다.
- migration 경로 수정 뒤 proposal 검증은 `ProposalConflict`로 종료됐다. 트랜잭션 문제가 아니라 검증용 전략 payload가 현재 fail-closed 근거 정책 도입 전의 `policy_version="test"` fixture였던 것이 원인이었다. 검증도 운영과 같은 `baseline_payload`와 현재 evidence receipt를 사용하도록 바꿨다.
- 실제 Supabase에서 20개 동시 `SELECT 1`은 모두 성공했다. 요청 취소 뒤 후속 쿼리 복구는 재시작 전 0.0182초, API 재시작 후 0.0212초였고 종료 시 대기 요청은 0건이었다. 사용자 데이터는 읽지 않았다.
- 실제 proposal 검증은 계획/섭취 분리, 중복 승인 멱등성, superseded·타 사용자 거절, 섭취·전략 부분 실패 롤백, 식사 수정과 stale 삭제 거절을 통과했다. 합성 데이터와 검증 중 DDL은 마지막에 전부 롤백했다.
- API만 정상 종료 후 재시작했고 worker와 MCP는 계속 `healthy`였다. 재시작 뒤 풀 복구와 proposal 검증을 다시 통과했다. 최종 상태는 세 컨테이너 모두 `restarts=0`, `OOMKilled=false`, `healthy`다. 이는 Compose 단일 API 재시작 검증이며 무중단 다중 replica 검증으로 확대 해석하지 않는다.

## 39. Cue 참고 UI 최종 상태 검증 (2026-10-11)

- 채팅 복원 중 접근 가능한 상태 표시를 추가했다. 복원 실패 시 완료된 Agent 실행을 다시 수행하지 않고 `/session/restore`만 재호출하는 “화면 상태 다시 불러오기” 경로를 제공한다.
- 빈 대화에는 저녁 추천·오늘 기록·목표 진행의 세 빠른 시작을 제공한다. 버튼은 composer에 문장만 채우며 사용자가 전송하기 전에는 모델이나 도구를 호출하지 않는다.
- 인증 화면과 온보딩의 기존 밝은 초록색·인라인 카드 표현을 채팅과 같은 editorial green, serif 제목, 표면·포커스 체계로 맞췄다. 인증 화면은 실제 `<form>`과 연결된 label을 사용해 Enter 제출과 오류 alert를 지원한다.
- 실제 Chromium에서 합성 계정으로 로그인해 데스크톱/390px 빈 상태와 모바일 실제 Agent 스트리밍을 확인했다. 진행 4단계가 완료 뒤 접힌 검토 과정으로 전환됐고 답변이 표시됐다. 당시 콘솔 오류·경고는 0건이었다.
- 합성 계정 삭제 뒤 Supabase SDK가 이미 삭제된 Auth 계정에 `/logout`을 보내 403을 남기는 문제를 발견했다. 성공한 삭제 뒤에는 해당 프로젝트의 로컬 Auth storage만 제거하고 앱 token/state를 초기화하도록 수정했다. 부분 삭제 재시도 경로는 그대로 세션을 유지한다.
- 합성 Auth·앱 데이터는 계정 삭제 흐름으로 정리했고 임시 자격증명 파일도 제거했다. 시각 검토 근거와 한계는 `design-qa.md`에 기록했다.

## 40. 실제 E2E 후속 결함·서비스 날짜 경계 (2026-10-11)

- 실제 Chromium 생명주기를 다시 점검하면서 proposal 자체는 체크포인터에서 복원되지만 proposal을 만든 최신 사용자/Assistant 메시지는 새로고침 뒤 사라지는 결함을 발견했다. 원인은 `interrupt_before=["confirm"]`이 `save_chat`보다 먼저 중단하는 그래프 순서였다. proposal 생성 턴을 먼저 `save_pending_chat`에 기록한 뒤 confirm에서 중단하도록 바꾸고, 새 사과 섭취 proposal에서 새로고침 후 메시지와 동일 ID/version 카드가 함께 복원되는 것을 확인했다.
- 모델이 `오늘` 요청의 `log_date`에 2025-01-01을 반환한 사례도 발견했다. LLM의 구조화 출력이 스키마 형식은 통과했지만 상대 날짜 의미를 보장하지 못한 것이 원인이다. 오늘 섭취의 날짜는 모델 값 대신 서버가 관리하는 `state.today_date`/서비스 날짜로 고정했다. 이 결함이 있는 proposal은 취소했으며 DB에 섭취로 확정하지 않았다.
- Docker의 UTC 날짜와 한국 사용자의 날짜가 자정 부근에 하루 달랐다. `SERVICE_TIMEZONE=Asia/Seoul`과 `service_today()`를 도입해 오늘 섭취, 최근 기록, 분석 기간, 식단 계획, 편집 상대 날짜, 목표 기한, 전략 적용일, 온보딩 및 스케줄러를 같은 기준으로 통일했다. 고정 UTC 시각 `2026-10-10T18:00Z`가 한국 날짜 `2026-10-11`이 되는 단위 테스트와 proposal/그래프 회귀 테스트로 확인했다.
- 독립 RAG 최종셋의 과거 “영어 1건 원인 미확정” 표기는 현재 결과로 대체한다. 실제 누락은 `who_tfa_children_indirect-en`이며, 영어 질의가 WHO 16쪽의 아동 외삽 문장을 후보에 넣지 못한 query-expansion 차이다. 답변기는 근거를 만들지 않고 보류했다. 동결 최종셋은 재튜닝하지 않으며 영어 확장은 별도 개발셋 과제로 남긴다.
- 검증 중 Docker named pipe 권한 오류는 제한 샌드박스의 Docker Desktop 접근 차단으로 진단했고 승인된 동일 명령으로 재실행했다. 이후 세 실패는 모두 UTC `date.today()`를 쓰던 테스트 fixture가 새 서비스 시계와 하루 어긋난 것이 원인이어서 fixture를 `service_today()`로 통일했다.

## 41. kind 스테이징 rollout·부하·복구 검증 (2026-10-11)

- API deployment에 `maxUnavailable=0`, `maxSurge=1`, `minReadySeconds=5`, HTTP startup probe, 60초 종료 유예를 적용했다. PodDisruptionBudget은 API 최소 1개를 유지하며 한국 서비스 시간대는 비밀값이 아닌 ConfigMap으로 API와 worker에 전달한다.
- 실제 `kind-metadiet` 클러스터에 현재 이미지를 적용해 API 2개, worker 1개, MCP 1개가 모두 Ready가 됐다. API rolling restart 중 NodePort에 100ms 간격으로 400회 `/health` 요청을 보냈고 **400/400 성공, 실패 0, p50 3.97ms, p95 5.86ms**였다. 두 API Pod UID가 모두 교체됐고 restart 0, PDB allowed disruptions 1이었다. 원본은 `backend/artifacts/kind-rollout-health-v1.json`이다.
- 새 Pod에서 실제 Supabase 연결 풀은 동시 20건 모두 성공, 취소 후 후속 쿼리 0.0213초, 종료 waiting 0을 기록했다. proposal 원자성 검증은 계획/섭취 분리·중복 승인·소유권·stale version·부분 실패 rollback·수정/삭제 충돌을 통과하고 합성 데이터와 임시 DDL을 전부 롤백했다.
- 첫 이미지 import는 kind 노드의 tmpfs `/tmp`에서 복사한 tar가 후속 exec에 보이지 않아 실패했다. 노드의 영속 writable 경로 `/var`로 분리 복사해 containerd import를 완료했다. 로컬 `kind` CLI가 PATH에 없었지만 기존 Kubernetes 컨텍스트와 노드 컨테이너는 정상이라 클러스터를 재생성하지 않았다.
- 첫 Pod 내부 proposal 검증은 exit 137이었다. Pod/container restart는 0, 이벤트에 OOM 없음, cgroup `oom_kill=0`, memory peak 약 159MiB였고 API는 계속 Ready였다. rollout 직후 exec 연결 중단으로 분리했으며 안정된 Ready Pod에서 동일 명령이 통과했다. 검증 스크립트에 남아 있던 UTC `date.today()`도 한국 서비스 날짜와 충돌하므로 `service_today()`로 수정했다.
- 이번 400회 측정은 health endpoint 가용성 검증이다. 인증된 긴 SSE 요청이 Pod 종료 신호를 받는 동안 재연결되는지와 실제 클라우드 ingress/load balancer 동작은 별도 스테이징 E2E 범위로 남는다.

## 42. 인증 SSE 교차 Pod 복구 검증 (2026-10-11)

- 문제: 진행 이벤트 journal은 API Pod 메모리에 있으므로, 연결을 담당하던 Pod가 사라지고 다른 Pod로 재접속하면 이전 progress event 목록은 존재하지 않는다. 기존 코드는 체크포인트가 `running`인 상태에서 이 경우를 명시적으로 재개하지 않았다.
- 수정: 같은 `stream_run_id`의 로컬 journal이 있으면 기존 stream을 따라가고, journal이 없지만 durable checkpoint가 `running`이면 같은 LangGraph config로 `graph.ainvoke(None, config)`를 실행해 Postgres checkpoint부터 재개한다. terminal checkpoint는 재실행하지 않고 저장 상태만 재생한다.
- 실제 시험: Supabase 합성 사용자를 만들고 특정 API Pod에 port-forward한 뒤 식사 기록 SSE를 시작했다. 첫 progress event(`seq=1`) 직후 그 Pod를 강제 삭제하고 Service NodePort로 같은 run ID와 마지막 seq를 보내 재접속했다.
- 결과: 재접속 후 이벤트 49개를 받아 `completed=true`로 종료됐고 pending proposal은 1건, 승인 전 meal row는 0건이었다. 같은 proposal을 두 번 확정한 뒤 meal row는 **1건**이었다. 합성 Auth 사용자는 시험 후 0건으로 정리됐다. 원본은 `backend/artifacts/sse-pod-recovery-v1.json`이다.
- 해석: LangGraph/Postgres checkpoint 기반 실행 재개와 proposal idempotency/HITL 경계가 실제 Pod 교체에서도 동작했다. 다만 이는 로컬 단일 노드 kind와 합성 사용자 1개 시험이며, 실제 클라우드 ingress의 connection draining과 다중 동시 사용자 부하는 베타 배포 단계에서 별도로 검증한다.

## 43. Render 공개 베타 E2E·제한 부하 시험 (2026-10-11)

- Render Blueprint로 `metadiet-api` Docker Web Service와 `metadiet-web` Static Site를 배포했다. 공개 API `/health`, 정적 사이트 응답, 실제 웹 origin의 CORS preflight가 모두 200이었다.
- 첫 공개 Agent E2E는 Gemini 호출에서 `API_KEY_INVALID`로 실패했다. LangSmith의 `LangGraph → supervisor → ChatGoogleGenerativeAI` error trace를 통해 `GEMINI_API_KEY` 자리에 OpenAI 키가 입력된 설정 오류임을 확인했다. Render secret을 올바른 Google AI Studio 키로 교체하고 재배포한 뒤 같은 검증을 통과했다. 비밀값 자체는 로그·artifact·저장소에 기록하지 않았다.
- 합성 사용자의 가입·온보딩·초기 전략 HITL 확정 뒤 실제 `record_only` 요청을 공개 SSE로 실행했다. 첫 이벤트는 4,180.8ms, 이벤트는 54개였고 progress → answer delta → completed 순서를 보였다. 같은 run ID 재생, pending proposal 새로고침 복원, 승인 뒤 pending 제거를 확인했다.
- 같은 섭취 proposal을 두 번 확정해도 meal row는 1개였다. 초기 전략과 식사 proposal 상태는 모두 confirmed였고 합성 Auth 사용자는 시험 종료 후 삭제했다. LangSmith 최신 trace의 Supervisor와 Gemini 호출도 success였다.
- 제한 부하는 health 50건/동시 10, 인증 조회 30건/동시 5, 실제 Agent SSE 2건/동시 2로 고정했다. 오류는 모두 0건이었다. health p50/p95는 229.7/638.5ms, 인증 조회 p50/p95는 807.2/2,068.8ms였다. 두 Agent의 첫 이벤트는 4,317.4/4,450.3ms, 둘을 동시에 완료한 wall time은 32.48초였다.
- 시험 직후 `/health`도 정상이고 합성 Auth 사용자는 삭제됐다. 이 결과는 제한 베타의 작은 warm-load 표본이며 최대 처리량이나 15분 휴면 뒤 cold start를 대표하지 않는다. 원본은 git-ignored `backend/artifacts/render-beta-smoke-v1.json`과 `render-beta-load-v1.json`, 재현 스크립트는 `backend/scripts/check_render_beta.py`와 `check_render_load.py`다.

## 44. Render 공개 웹 UI 생명주기 검증 (2026-10-11)

- 별도 Playwright Chromium에서 `https://metadiet-web.onrender.com`을 열고 합성 이메일 사용자를 로그인시켰다. 일반 성인 감량 프로필 입력, 2,325 kcal 초기 전략 proposal 검토, 근거 카드 확인과 HITL 확정을 실제 UI로 완료했다.
- 채팅에서 “사과 100g 기록만”을 전송하자 요청 의도 분석 → 식사 Agent 위임 → 음식 검색의 실제 진행 상태가 표시됐다. 완료 뒤 답변과 52 kcal 섭취 proposal이 나타났고 확정 전 상단 섭취량은 0 kcal였다.
- proposal 확정 전에 브라우저를 새로고침했다. 복원 중 상태를 거쳐 사용자 메시지, Assistant 답변, 동일 v1 proposal 카드가 복원됐고 Agent 실행은 다시 시작되지 않았다. 복원된 카드를 확정한 뒤 오늘 섭취량은 정확히 52 kcal로 한 번 증가했다.
- viewport를 390×844로 바꿔 채팅·탭·고정 입력창·설정 화면의 접근 가능한 DOM 구조를 확인했다. 전체 흐름의 브라우저 console error와 warning은 0건이었다.
- 설정 화면에서 현재 비밀번호 재인증과 `DELETE` 확인값으로 계정을 삭제했다. 로그인 화면으로 돌아왔고 직접 확인한 Auth 사용자는 삭제, 내부 `users` 행은 0건이었다. 임시 자격증명 파일과 Playwright 세션도 제거했다.
- 이 검증은 핵심 성공 경로와 새로고침 복원을 다룬다. 네트워크 오프라인·API 5xx의 공개 오류 화면, 다양한 실제 모바일 브라우저의 시각 회귀, 무료 인스턴스 cold start는 별도 운영 점검 범위다.

## 45. 공개 개인정보·무료 베타 안내와 오류 화면 회귀 (2026-10-11)

- 로그인 전 화면과 계정 설정에 개인정보처리방침·베타 이용 안내를 연결했다. 처리 정보와 목적, Supabase·Google Gemini·Pinecone·LangSmith·Render의 역할, 계정 삭제 경로를 공개한다.
- 확정되지 않은 보존 기간이나 법률 준수를 약속하지 않고 제한 베타임을 명시했다. 일반 성인 체중 관리 정보 서비스이며 의료 진단·치료·응급 대응이 아니고, AI 추정값과 전략 변경은 저장 전에 사용자가 확인해야 한다고 안내한다.
- 실제 Chromium에서 390×844 viewport로 두 안내 dialog의 접근성 구조, Escape 닫기, 모바일 스크롤과 외부 오류 제보 링크를 확인했다. 브라우저 console error·warning은 0건이었다.
- 스트림 중단을 주입한 회귀 테스트에서 연결 오류 alert, 불완전 응답 안내, composer 재사용 가능 상태를 확인했다. 기존 복원 실패 테스트는 완료된 실행을 재수행하지 않고 `/session/restore`만 재호출한다.
- 검증은 frontend **32 passed**, production build 성공이다. 공개 Render URL 전환은 커밋 배포 뒤 동일 화면을 다시 확인한다.

## 46. Render 무료 인스턴스 cold start·자동 배포 진단 (2026-10-11)

- 공개 API를 15분 이상 사용하지 않은 상태에서 `/health` 첫 요청을 측정했다. HTTP 200까지 **53,022.0ms**가 걸렸다. 기동 직후 warm 요청을 20회 연속 측정한 결과 중앙값은 **236.2ms**, p95는 **949.9ms**, 범위는 203.9~1,272.4ms였다. 따라서 약 53초 지연은 매 요청이 아니라 무료 Web Service가 휴면에서 깨어나는 첫 API 요청에 해당한다. 정적 프론트엔드는 이 휴면 대상이 아니다.
- 같은 애플리케이션을 로컬의 새 프로세스로 기동해 health가 준비될 때까지 측정한 시간은 **5,720.3ms**였고, `import main`만 3회 측정한 중앙값은 **5,132.3ms**였다. `-X importtime` 분석에서는 `app.api.routes.main` 4.43초, `app.agents.graph` 3.84초, `diet_logger.node` 1.72초, LangGraph 약 0.99초, Gemini 연동 모듈 약 0.76초, Supabase 약 0.64초, pandas/영양 DB 약 0.59초가 누적 경로에 포함됐다. 로컬 앱 기동 전체를 제거한다고 가정해도 관측된 53초 중 약 5.7초만 줄일 수 있어, 주원인은 Render 무료 인스턴스의 scale-to-zero 복구다.
- `/health`만 먼저 응답하도록 무거운 graph import를 지연시키는 방식은 준비 표시만 앞당기고 첫 채팅의 초기화를 뒤로 미루며 동시 초기화·readiness 복잡도를 추가한다. 제한 베타에서는 적용하지 않는다. 15분 미만 주기의 인위적 keep-alive도 무료 자원을 계속 점유하는 우회이므로 채택하지 않는다. 첫 API 요청 지연을 안정적으로 없애야 할 때는 휴면하지 않는 유료 Render 인스턴스로 전환한다.
- 공개 정적 사이트는 GitHub에 새 커밋이 푸시된 뒤에도 이전 번들 `main.f6584129.js`를 계속 제공했다. Blueprint의 기존 서비스는 자동 배포 설정을 생략하면 현재 값을 유지하므로 `render.yaml`의 API·웹 서비스에 `autoDeployTrigger: commit`을 명시하고 매니페스트 테스트로 고정했다.
- `render.yaml` 변경 뒤에도 공개 번들이 바뀌지 않았고 Blueprint Manual Sync도 새 실행을 만들지 않았다. 이후 서비스 수동 배포 로그의 `we don't have access to your repo, but we'll try to clone it anyway`로 Render가 공개 URL clone은 가능하지만 연결된 GitHub provider 권한/webhook은 갖지 못한 것이 확인됐다. 자동 배포는 연결된 Git provider가 필요하므로, GitHub App의 저장소 접근을 다시 승인하거나 deploy hook을 구성하기 전까지 서비스별 수동 배포가 필요하다.
- 인앱 브라우저 자동화는 Codex CUA 초기화 단계에서 `failed to write kernel assets: 지정된 경로를 찾을 수 없습니다`로 두 번 실패했다. 서비스나 Render 오류가 아니며 로컬 Playwright를 사용한 정책 UI 검증으로 우회했다. Dashboard 인증 세션이 필요한 Manual Sync는 이 우회로 실행할 수 없다.
- 2026-10-11 최종 운영 점검에서도 같은 CUA 초기화 오류가 재현됐다. 한 차례 kernel reset 후에도 동일했으므로 반복 조작을 중단했다. 공개 `/health`는 HTTP 200, 719.4ms였고 코드·배포 장애는 아니었다. Dashboard에서만 확인할 수 있는 workspace 장애 이메일 알림 상태는 사용자 UI 확인 항목으로 남긴다.
- 인증된 Render Notifications 화면을 사용자가 직접 확인해 `Notification Destination=Email`, `Default Service Notifications=Only failure notifications`를 확인했다. 화면 아래에 Notification Overrides나 서비스 목록이 없어 서비스별 예외가 없는 workspace 기본 적용 상태로 판정했다.

## 47. 공개 정책 UI 배포·프론트 의존성 감사 (2026-10-11)

- Render 정적 사이트를 커밋 `8dae5b8`로 수동 배포했다. 빌드는 성공했고 공개 HTML이 새 번들 `main.5e73512f.js`를 반환했다.
- 공개 URL의 실제 Chromium에서 로그인 전 개인정보처리방침·베타 이용 안내 버튼과 dialog를 확인했다. 390×844 viewport의 스크롤, Escape 닫기, 의료 서비스 제한·외부 처리자·삭제·민감정보 안내가 정상이며 console error·warning은 0건이었다.
- Render `npm ci` 로그는 91개 취약점을 보고했다. 감사를 분리해 확인한 결과 직접 의존성 중 사용하지 않는 `axios`가 high로 포함돼 제거했고, 전체 프론트 32개 테스트와 production build가 통과했다.
- 제거 뒤 남은 90건은 대부분 `react-scripts`가 설치하는 Jest·Webpack 개발/빌드 체인의 전이 의존성이다. Render는 결과 정적 파일만 배포해 이 도구를 런타임 서버로 노출하지 않는다. `npm audit fix --force`는 `react-scripts`를 깨뜨리는 major 변경을 제안하므로 제한 베타에서 강제 적용하지 않고, Vite 등 유지보수되는 빌드 체인 전환을 별도 후속 작업으로 남긴다.

## 48. 인증 만료 오류 경계 (2026-10-11)

- 공개 오류 흐름 점검에서 API 5xx와 중단된 SSE는 각각 복원 재시도와 불완전 응답 안내로 연결돼 있었지만, 만료된 JWT로 401을 받으면 현재 화면에 머무르는 결함을 발견했다.
- SSE와 세션 복원 API가 401을 받으면 공통 `metadiet:auth-expired` 이벤트를 발생시키고, 앱 루트가 토큰을 지운 뒤 Supabase 세션을 종료해 로그인 화면으로 복귀하도록 수정했다. 복원 404는 새 대화의 정상 빈 상태로 계속 취급한다.
- 401 이벤트 발생, 앱의 로그인 화면 복귀, 스트림 중단, 복원 실패를 회귀 테스트로 분리했다. 검증은 frontend **35 passed**, production build 성공이다.
- 첫 Jest 실행은 Codex 샌드박스 임시 디렉터리에서 Node `realpath`가 `EPERM`을 반환해 실패했고, 프로젝트 내부 임시 경로에서도 동일했다. 제한 밖의 동일 명령으로 재실행해 코드 결과와 실행 환경 문제를 분리했다.

## 49. 실제 브라우저 오류 주입·배포 연결 확인 (2026-10-11)

- production React build를 실제 Chromium에서 열고 네트워크 경계만 Playwright route로 대체했다. 세션 복원 500은 완료된 실행을 다시 호출하지 않고 오류 alert와 “화면 상태 다시 불러오기” 버튼을 표시했다.
- SSE가 progress 1개 뒤 completed 없이 종료되는 응답을 주입했다. 클라이언트는 같은 실행 ID/마지막 sequence로 한 번 재시도한 뒤 “응답을 끝까지 받지 못했습니다”를 표시했고, 수신한 검토 과정 1단계와 입력창을 유지했다.
- 세션 복원 401은 `metadiet:auth-expired` 경계를 통해 Supabase 세션과 앱 토큰을 정리하고 로그인 화면으로 복귀했다. 검증용 합성 Auth 사용자는 종료 후 삭제했고 자격증명 파일도 제거했다.
- 첫 로컬 브라우저 실행은 build에 `http://localhost:8080`이 포함돼 CORS 실패했고, 공개 API URL로 재빌드한 뒤에도 API가 실제 배포 origin만 허용해 로컬 origin을 차단했다. 운영 CORS를 넓히지 않고 검증 대상 응답만 route로 대체했다. 첫 route 명령은 Windows 인자 escaping으로 JSON 따옴표가 손실됐고, 구조화 응답을 담은 임시 Playwright 파일로 교체해 의도한 실패를 정확히 재현했다.
- GitHub App 연결 후 커밋 `4e1a8f4`를 push했지만 새 Render deploy는 생성되지 않았고 공개 사이트는 이전 `main.5e73512f.js`를 계속 제공했다. 기존 서비스가 공개 URL clone 방식의 Git credential을 유지하는 것으로 판단한다. 새 인증 만료 처리는 로컬 build에서 검증됐지만 서비스의 Git credential을 다시 연결하거나 latest commit을 수동 배포하기 전에는 공개 사이트에 반영되지 않는다.
- 이후 Git credential 연결이 전파된 뒤 커밋 `5f86bac` push에서 자동 배포가 동작했다. 공개 번들은 `main.60831615.js`로 바뀌어 인증 만료 수정이 반영됐고, 실제 Chromium의 로그인 화면과 정책 링크는 console error·warning 0건이었다. 따라서 앞선 미배포 상태는 최종 장애가 아니라 기존 서비스 연결 전파 중 관측한 중간 상태로 판정한다.
- Render 공식 운영 설정에 따라 workspace email 알림을 `Only failure notifications`로 두면 deploy/build 실패, unhealthy service, Blueprint sync 실패를 받을 수 있다. 실제 Dashboard 값은 인증된 UI에서 확인해야 하며 현재 코드 검증만으로 알림 활성화를 주장하지 않는다.

## 50. 인앱 베타 피드백 보안·배포 검증 (2026-10-11)

- 설정 화면에 만족도 1~5, 고정 분류, 선택 의견 1,000자만 받는 피드백 카드를 추가했다. 대화·식사·인바디·이메일은 자동 첨부하지 않으며 서버가 JWT에서 내부 사용자 ID와 `settings` 페이지를 결정한다.
- `beta_feedback`은 RLS를 활성화하고 브라우저 정책을 만들지 않았다. 백엔드 전용 Postgres 경로만 저장하며 `(user_id, client_submission_id)` unique 제약으로 재전송을 한 행으로 제한한다. `users.id` FK는 `ON DELETE CASCADE`다.
- 첫 마이그레이션 명령은 PowerShell/Python 인용 오류로 SQL 실행 전 `SyntaxError`가 발생했다. 셸 문자열을 단순화해 재실행했고, 실제 catalog 감사에서 `RLS=true`, feedback FK `CASCADE`, idempotency unique를 확인했다.
- 공개 Render API에서 합성 계정으로 첫 제출 HTTP 201, 같은 UUID 재전송 HTTP 200을 받았다. 재전송 뒤 DB 행은 1개였고 공개 계정 삭제 뒤 0개였다. 측정 시간은 최초 2,388.0ms, 재전송 1,307.5ms로 단일 warm 표본이며 일반 성능 분포로 확대하지 않는다.
- 수명주기 artifact는 상태·행 수·시간·정리 상태만 기록한다. 댓글·토큰·사용자 식별자는 저장하지 않았으며 합성 계정은 공개 삭제 API로 정리됐다.
- 최종 회귀는 backend **376 passed, 1 skipped**, frontend **41 passed**, production build 성공이다. 프론트 번들에서 `beta-feedback-title` 식별자를 확인해 자동 배포 반영도 확인했다.

## 51. 공개 베타 피드백 브라우저 E2E·실패 복구 (2026-10-11)

- 공개 Render 사이트에서 별도 합성 계정으로 로그인하고 설정 화면의 피드백 카드를 실제 Chromium으로 검증했다. 만족도 4점, 답변 품질 분류와 합성 의견을 제출하자 성공 안내가 표시되고 입력값이 초기화됐다.
- `/feedback` 요청에 HTTP 503을 주입한 실패 경로에서는 오류 안내를 표시하면서 만족도 5점, 버그 분류와 의견을 그대로 유지했다. 사용자는 내용을 다시 입력하지 않고 재시도할 수 있다. 이때 console error 1건은 의도적으로 주입한 503 응답이었다.
- 390×844 viewport에서 카드·라디오 그룹·분류·의견·전송 버튼을 확인했다. DOM 기준 `scrollWidth=clientWidth=390`이고 viewport 밖으로 벗어난 요소는 0개여서 실제 가로 overflow는 없었다. 시각 근거는 로컬 `output/playwright/beta-feedback-mobile.png`에 남겼다.
- 계정 삭제 비밀번호가 HTML form 밖에 있어 Chromium이 `[DOM] Password field is not contained in a form`을 기록했다. 삭제 입력과 버튼을 submit form으로 묶고 회귀 테스트를 추가했다. 이 수정은 Enter 제출과 비밀번호 관리자·접근성 도구의 문맥 인식도 개선한다.
- 첫 실패 주입 명령은 Windows/bash 인용이 중첩돼 `unexpected EOF`가 발생했고 실제 API 요청이 한 번 실행됐다. route 코드를 임시 스크립트로 분리한 뒤 Playwright가 요구하는 `async (page) => { ... }` 함수 형식으로 고쳐 정확한 503을 재현했다. 검증 계정은 공개 삭제 흐름으로 제거했고 DB 재조회 결과 합성 사용자와 연결 피드백은 모두 0건이었다.
- Codex CUA는 `failed to write kernel assets: 지정된 경로를 찾을 수 없습니다. (os error 3)`로 초기화되지 않아 공식 Playwright CLI로 전환했다. 이는 서비스 결함이 아니라 로컬 자동화 런타임 결함이며, 공개 UI 성공·실패·모바일 결과에는 영향을 주지 않았다.
- 폼 수정 뒤 전체 프론트 회귀는 **42 passed**, production build는 `main.d694964f.js`로 성공했다.

## 52. 공개 회원가입 이메일 리디렉션 복구 (2026-10-12)

- 공개 베타 회원가입 메일의 확인 링크가 인증 완료 뒤 `localhost`로 이동해 `ERR_CONNECTION_REFUSED`가 발생했다. 회원가입 요청이 `emailRedirectTo`를 보내지 않았고, Supabase Auth가 이 경우 프로젝트 Site URL을 사용한 것이 직접 원인이다.
- 회원가입 호출에 현재 앱의 `window.location.origin`을 명시해 로컬과 Render가 각자의 origin으로 돌아오도록 수정했다. 회귀 테스트는 Supabase `signUp` 인자에 이 주소가 포함되는지 검증한다.
- Supabase 공식 문서 기준으로 이 주소는 Auth Redirect URLs 허용 목록에 있어야 한다. 운영 설정은 Site URL과 Redirect URL에 `https://metadiet-web.onrender.com`을 등록하고, 로컬 개발 주소는 별도 Redirect URL로 유지한다.
- 첫 Jest 실행은 Windows 샌드박스가 임시 디렉터리 `realpath`를 `EPERM`으로 차단했다. 같은 명령을 샌드박스 밖에서 실행해 코드 오류와 환경 오류를 분리했고 수정 회귀 테스트 3개가 통과했다.

## 53. 브라우저 세션 인증·온보딩 화면 깜빡임 복구 (2026-10-12)

- Supabase JS 기본 인증 저장소가 `localStorage`여서 브라우저를 종료한 뒤에도 자동 로그인됐다. 인증 저장소를 `sessionStorage`로 바꿔 같은 브라우저 세션의 새로고침은 유지하되 브라우저 세션 종료 뒤에는 다시 로그인하도록 조정했다.
- 기존 사용자의 온보딩 상태를 API에서 확인하는 동안 실제 키·체중 입력 폼이 먼저 렌더링됐다가 사라졌다. 초기 조회 중에는 전용 로딩 상태만 표시하고, 실패하면 입력 폼 대신 오류와 재시도 버튼을 표시하도록 상태를 분리했다.
- 계정 삭제 경로가 기존 `localStorage`만 비우던 부분도 `sessionStorage`까지 함께 정리하도록 보완했다. 저장 방식, 로딩 화면, 실패 재시도, 계정 삭제 정리를 각각 회귀 테스트로 고정했다.

## 54. 개인정보 최소화 제품 분석 기반 (2026-10-12)

- 제한 베타 사용성을 관찰하기 위해 가입·온보딩·채팅·확정·피드백·오류의 단계 이벤트를 추가했다. 원문 대화, 음식명, 의견, 이메일, 체중·체성분은 이벤트 속성으로 허용하지 않는다.
- `product_events`는 `(user_id, client_event_id)` unique로 브라우저 재시도의 중복 저장을 막고 계정 삭제 시 `ON DELETE CASCADE`로 함께 삭제된다. 공개 스키마의 RLS를 활성화하고 `anon`·`authenticated` 권한을 회수해 백엔드 전용 저장·집계 경로로 제한했다.
- 관리자 조회는 검증된 JWT의 최상위 email과 서버 `ADMIN_EMAILS` allowlist를 비교한다. 사용자가 바꿀 수 있는 metadata는 관리자 판정에 사용하지 않는다.
- 설정 화면의 운영 카드는 DAU·WAU, 온보딩 완료율, 첫 식사 기록률, Agent 성공률과 p95 지연을 1·7·30·90일 범위로 보여준다. 일반 사용자는 403 응답 뒤 카드를 볼 수 없다.
- Supabase 실제 마이그레이션 뒤 catalog에서 RLS 활성화와 브라우저 역할 grant 없음이 확인됐다. `RLS enabled no policy` advisor는 브라우저 접근을 전부 차단한 의도된 백엔드 전용 설계이며, 이 테이블에는 허용 policy를 만들지 않는다.

## 55. 제품 분석 정확성·공개 수명주기 검증 (2026-10-12)

- 온보딩 확정 시 가입 이벤트를 보내던 방식은 가입 후 이탈을 측정하지 못했다. 가입 기간 cohort는 `auth.users.created_at`, 온보딩은 실제 전략 존재, 첫 식사 기록은 실제 `meal_logs` 존재로 계산한다. 삭제된 계정은 포함하지 않으며 미래 시점에 완료하면 동일 가입 cohort의 완료율이 변할 수 있다.
- 1일 조회에서 WAU도 1일로 제한되던 오류를 수정해 활성 사용자는 항상 최근 24시간·7일을 조회한다. 오류 수는 실패한 상담 완료 이벤트만 세어 같은 실패의 `error_shown` 이벤트를 이중 계산하지 않는다. p50/p95는 성공 완료 요청만 포함한다.
- 상담 완료율은 브라우저가 completed 이벤트를 수신한 비율이며 목표 달성률·답변 정확도가 아니다. 브라우저 종료·분석 전송 실패로 누락될 수 있는 best-effort 지표라는 한계를 유지한다.
- 실제 proposal은 `intake`/`plan`/`weight`/`measurement`/`strategy`다. 잘못된 `meal` 비교를 바로잡고 전략과 계획은 측정 확정 이벤트로 보내지 않는다. 전환율 자체는 클라이언트 확정 이벤트를 신뢰하지 않고 DB 기록을 사용한다.
- 이벤트 properties는 금지 키 목록 대신 고정 키·고정 값 allowlist로 제한해 임의 문자열에 건강 정보를 담는 경로를 차단한다. 관리자 컴포넌트 테스트를 계정 설정 테스트에서 분리해 `act` 경고를 제거했다.
- 공개 합성 사용자 검증에서 최초 저장 201, 동일 ID 재전송 200, 재전송 후 1행, 공개 계정 삭제 후 0행을 확인했다. 집계 쿼리는 실제 Supabase에 연결해 실행했고 주간 활성 사용자와 cohort 비율 범위를 검증했다. 원문·토큰·계정 ID 없이 `backend/artifacts/product-analytics-lifecycle-v2.json`에 결과를 저장한다.
- 첫 실행은 검증 스크립트의 Windows ProactorEventLoop 때문에 psycopg 비동기 연결이 실패했다. 공식 https://www.psycopg.org/psycopg3/docs/advanced/async.html 지침에 따라 SelectorEventLoop 정책을 설정하고 재실행해 통과했다. 합성 계정은 실패 경로에서도 정리한다.
- 관리자 이메일 allowlist 등록 및 관리자 화면의 인증된 공개 조회는 별도 확인 항목이다. LangSmith 실제 trace 연결은 이 변경에서 완료됐다고 주장하지 않는다.
