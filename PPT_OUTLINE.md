# MetaDiet AI PPT 구성안

대상 포지션: **AI Agent Engineer / LLM Engineer / AI Engineer**

목표: 기능 소개가 아니라, **문제를 어떻게 AI Agent 구조로 쪼개고, RAG/Tool/LangGraph/평가/관측성으로 안정화했는지**를 보여주는 포트폴리오용 발표 자료.

---

## Slide 1. Title

**MetaDiet AI**  
인바디와 식단 기록을 기반으로 목표를 자동 조정하는 Multi-Agent 식단 코칭 시스템

**Subtitle**
- LangGraph Multi-Agent Orchestration
- Hybrid RAG + Reranking + Grounded Generation
- Human-in-the-loop Diet Logging
- InBody OCR/Vision 기반 전략 재설정

**발표 메시지**
> MetaDiet AI는 단순 칼로리 기록 앱이 아니라, 사용자의 식단 기록과 인바디 변화를 기반으로 목표를 조정하고 근거 기반 조언을 제공하는 개인 맞춤형 AI Agent 시스템입니다.

---

## Slide 2. Problem: 왜 필요한가?

**기존 식단 관리의 문제**

| 문제 | 사용자 경험 |
|---|---|
| 기록 피로도 | 매번 음식명, g, 끼니를 직접 입력해야 함 |
| 수치 중심 | 칼로리는 보여주지만 "오늘 어떻게 먹어야 하는지"는 약함 |
| 목표 고정 | 체중/골격근/체지방 변화가 생겨도 목표가 자동 조정되지 않음 |
| 근거 부족 | 조언이 왜 맞는지, 어떤 문서 근거인지 알기 어려움 |
| 오류 수정 불편 | 잘못 기록한 식단을 자연어로 수정하기 어려움 |

**발표 메시지**
> 기존 앱은 기록 도구에 가깝고, 사용자의 몸 상태 변화에 따라 전략을 바꾸는 코치 역할은 약합니다. 그래서 저는 기록, 조언, 계획, 리포트, 인바디 분석을 역할별 Agent로 분리했습니다.

---

## Slide 3. 기존 칼로리 앱의 한계 vs MetaDiet AI

| 기존 앱 | MetaDiet AI |
|---|---|
| 사용자가 직접 입력 | 자연어/사진 입력 후 Agent가 후보 생성 |
| 칼로리 계산 중심 | 기록 + 조언 + 식단 계획 + 리포트 |
| 목표 수동 설정 | 인바디 갱신 시 전략 자동 재설정 |
| 근거 없는 조언 | RAG 기반 출처 표시 |
| 단일 흐름 | Supervisor + 역할별 Agent |
| 잘못 입력 시 수동 수정 | 자연어 edit Agent |
| 대화 상태 복구 어려움 | Checkpointer + time travel |

**차별점 한 줄**
> MetaDiet AI는 "기록 앱"이 아니라 **체성분 변화와 식단 데이터를 함께 보는 Agentic Diet Coach**입니다.

---

## Slide 4. 전체 아키텍처

**그림 추천**

```text
React
  ├─ Chat / Food Photo / InBody Photo
  ↓
FastAPI
  ↓
LangGraph Parent Graph
  ├─ supervisor
  ├─ diet_logger
  ├─ strategy
  ├─ meal_planner subgraph
  ├─ inbody
  ├─ reporter
  ├─ edit
  └─ confirm(HITL)

Data / Infra
  ├─ Supabase Postgres
  ├─ LangGraph Checkpoints
  ├─ Pinecone
  ├─ CSV Nutrition DB
  └─ LangSmith
```

**핵심**
- 프론트: React
- API: FastAPI
- Agent orchestration: LangGraph
- DB: Supabase
- Vector DB: Pinecone
- RAG eval/tracing: LangSmith + local eval report

---

## Slide 5. Agent Orchestration: Supervisor가 하는 일

**Supervisor Agent**
- 사용자 메시지와 대화 맥락을 보고 intent 분류
- 분류 결과에 따라 각 Agent로 routing
- 기본은 LLM 기반 intent classification
- 단, 오류 비용이 큰 케이스는 heuristic guardrail 적용

**Intent 종류**

| Intent | 담당 Agent |
|---|---|
| `diet_logger` | 먹은 음식 기록 |
| `strategy` | 식단 조언 |
| `meal_plan` | 하루 식단 생성 |
| `confirm` | 확정/수정/취소 |
| `edit` | 저장된 식단 수정/삭제 |
| `inbody` | 인바디 분석 |
| `reporter` | 주간/월간 리포트 |

**강조 포인트**
> 100% rule-based가 아니라, LLM이 판단하되 dead interrupt 같은 치명 오류를 막기 위해 guardrail을 섞은 hybrid routing입니다.

---

## Slide 6. LangGraph: Node와 Edge 설계

**Parent graph**

```text
load_state
  → supervisor
  → route_to_agent
      ├─ diet_logger → confirm
      ├─ strategy → save_chat
      ├─ meal_planner(subgraph) → confirm
      ├─ inbody → save_chat
      ├─ reporter → save_chat
      └─ edit → save_chat
  → save_chat
  → END
```

**Node**
- 하나의 책임을 가진 실행 단위
- 예: `diet_logger`, `confirm`, `strategy`, `validator`

**Edge**
- node 간 이동 경로
- 조건부 edge로 intent별 agent routing

**발표 메시지**
> LangGraph를 사용한 이유는 대화형 Agent에서 "지금 어떤 상태이고, 다음에 어떤 노드로 가야 하는지"를 명시적으로 제어하기 위해서입니다.

---

## Slide 7. Subgraph: meal_plan-validator 피드백 루프

**구조**

```text
meal_plan
  → validator
      ├─ passed=True  → confirm
      └─ passed=False → meal_plan 재생성
```

**구현 의도**
- meal_plan이 생성한 식단이 목표 칼로리/단백질과 맞는지 검증
- validator가 피드백을 만들고 meal_plan이 재생성
- 최대 3회 루프로 무한 반복 방지

**상호 검증 및 피드백 루프**

| 구성 | 역할 |
|---|---|
| `meal_plan` | 식단 후보 생성 |
| `validator` | 목표 대비 적합성 검증 |
| `validation_feedback` | 재생성 시 반영되는 피드백 |
| `validation_attempts` | 반복 횟수 제한 |

**포트폴리오 포인트**
> 단일 LLM 응답을 그대로 쓰지 않고, 생성 Agent와 검증 Agent를 분리해 self-correction 구조를 만들었습니다.

---

## Slide 8. Human-in-the-loop: 식단 저장 전 확인

**문제**
- 음식 사진/자연어 파싱은 틀릴 수 있음
- 식단 기록은 DB에 저장되는 행동이므로 사용자의 최종 확인이 필요

**해결**
- `diet_logger`는 바로 저장하지 않고 `pending_meals` 생성
- `confirm` node 진입 전 `interrupt_before=["confirm"]`
- 사용자가 확정/수정/취소를 말하면 저장 또는 취소

**흐름**

```text
"아침에 현미밥 200g 먹었어"
→ diet_logger가 영양성분 계산
→ "이대로 기록할까요?"
→ 사용자 확인
→ confirm node가 DB 저장
```

**발표 메시지**
> Agent가 사용자의 생활 데이터를 마음대로 저장하지 않도록, 중요한 write 작업 앞에는 HITL 확인을 넣었습니다.

---

## Slide 9. Tool 분리

**Tool을 분리한 이유**
- DB write/read, RAG 검색, CSV 영양성분 조회 같은 외부 작업을 명확히 분리
- Agent node는 판단과 orchestration에 집중
- 테스트와 유지보수 쉬움

**주요 Tool**

| Tool | 역할 |
|---|---|
| `nutrition_db_tool` | CSV 기반 영양성분 조회 |
| `search_food_tool` | CSV 음식명 후보 검색 |
| `save_meal_tool` | 식단 DB 저장 |
| `update_meal_tool` | 식단 수정 |
| `delete_meal_tool` | 식단 삭제 |
| `get_today_meals_tool` | 오늘 식단 조회 |
| `rag_nutrition_tool` | RAG 영양지식 검색 |
| `get_active_strategy_tool` | 현재 전략 조회 |
| `update_strategy_tool` | 새 식단 전략 저장 |
| `get_inbody_history_tool` | 인바디 이력 조회 |

**주의해서 말할 점**
> 모든 외부 작업을 100% tool-only로 강제한 구조는 아니지만, 주요 DB/RAG/CSV 기능은 tool 또는 독립 모듈로 분리했습니다.

---

## Slide 10. 영양성분과 RAG의 역할 분리

**핵심 설계**

| 영역 | 방식 | 이유 |
|---|---|---|
| 칼로리/탄단지/나트륨 계산 | CSV lookup | 정량 수치는 구조화 DB가 정확하고 재현 가능 |
| 영양학 조언 | RAG | 설명형 지식은 문서 근거와 출처가 필요 |
| 음식 사진 | Vision | 음식명 후보만 추출 |
| 양(g) | 사용자 입력 | Vision의 양 추정 오류 방지 |

**발표 메시지**
> 영양성분까지 RAG로 처리하면 hallucination 위험이 커집니다. 그래서 수치는 CSV로 deterministic하게 계산하고, 조언만 RAG로 grounded하게 만들었습니다.

---

## Slide 11. RAG Pipeline

**RAG 구조**

```text
User query
  → Dense retrieval(Pinecone, text-embedding-3-small)
  → Sparse retrieval(BM25, chunks.pkl)
  → RRF fusion
  → FlashRank reranking
  → grounded threshold check
  → answer with source/page
```

**구현 요소**

| 요소 | 구현 |
|---|---|
| Vector DB | Pinecone `diet-agent-rag` |
| Embedding | `text-embedding-3-small` |
| Sparse search | BM25 |
| Fusion | RRF |
| Reranker | FlashRank `ms-marco-MiniLM-L-12-v2` |
| Grounded flag | rerank score 또는 dense score threshold |
| Citation | source_file + page metadata |

---

## Slide 12. Chunking 전략: 어떻게 했고 왜?

**구현**
- PDF를 `PyPDFLoader`로 페이지 단위 로드
- page metadata 보존
- 목차/참고문헌/초단문 페이지 필터링
- `SemanticChunker`로 의미 경계 기반 분할
- 너무 큰 청크는 `RecursiveCharacterTextSplitter`로 cap
- `MAX_CHUNK_CHARS = 1200`
- `CHUNK_OVERLAP = 150`
- metadata: `source_file`, `title`, `page`

**왜 이렇게 했나?**

| 결정 | 이유 |
|---|---|
| 페이지 단위 로드 | 출처 표시와 page hit 평가를 위해 page metadata 보존 |
| semantic chunking | 고정 길이로 문장을 자르면 영양학 설명 근거가 끊길 수 있음 |
| 1200 char cap | 너무 긴 청크는 검색 정밀도를 낮추므로 최대 크기 제한 |
| 150 overlap | 경계에 걸친 문맥 손실 완화 |
| 정크 페이지 제거 | 목차/참고문헌 등 검색 노이즈 감소 |

**발표 메시지**
> 청킹에서 가장 중요하게 본 것은 "출처 페이지를 잃지 않으면서, 한 chunk가 하나의 의미 단위를 담도록 하는 것"이었습니다.

---

## Slide 13. Threshold와 Grounded Generation

**Threshold 설정**

| 값 | 현재 설정 | 용도 |
|---|---:|---|
| `rag_score_threshold` | 0.35 | dense-only fallback 시 grounded 판정 |
| `rag_candidate_k` | 20 | reranking 전 후보 수 |
| `rag_rerank_threshold` | 0.15 | FlashRank rerank top score grounded 판정 |
| retrieve `k` | 4 | 최종 검색 문서 수 |
| `max_docs` | 3 | 응답 context에 넣을 문서 수 |

**왜 threshold가 필요한가?**
- RAG 검색 결과가 약할 때 LLM이 추측하는 것을 방지
- 문서 근거가 부족하면 "근거 부족"으로 처리
- 출처 없는 RAG 조언을 제한

**Grounded generation**

```text
if grounded == False:
    context = ""
    "현재 문서 기반 근거는 부족합니다"
    출처 기반 조언 생성 금지
```

**발표 메시지**
> threshold는 정답을 보장하는 숫자가 아니라, 근거가 부족한 상태에서 LLM이 그럴듯하게 말하는 것을 막기 위한 안전장치입니다.

---

## Slide 14. 할루시네이션 방지 방법

| 위험 | 방지 방법 |
|---|---|
| 영양성분 수치 hallucination | CSV lookup으로 수치 계산 |
| 음식 사진 양 추정 오류 | Vision은 음식명만 추출, g은 사용자 입력 |
| 문서 근거 없는 조언 | grounded flag 확인 |
| 출처 누락 | source/page metadata를 context에 포함 |
| 잘못된 식단 저장 | HITL confirm interrupt |
| meal_plan 부적합 | validator feedback loop |
| 잘못된 routing | Supervisor heuristic guardrail |

**발표 메시지**
> 저는 LLM의 자유도를 높이는 것보다, 사용자의 건강/기록 데이터가 잘못 저장되거나 근거 없는 조언이 나가는 것을 막는 것을 더 중요하게 봤습니다.

---

## Slide 15. 사용 모델과 설정값

| 영역 | 모델/설정 | 이유 |
|---|---|---|
| Supervisor / Agent reasoning | `gpt-4o` | 한국어 의도 분류와 복합 reasoning |
| OCR / Vision | `gpt-4o` | 인바디/음식 사진 이해 |
| RAG answerer | `gpt-4o-mini` | 근거 기반 QA 비용 절감 |
| Eval judge | `gpt-4o-mini` | 평가 자동화 비용 절감 |
| Synthetic eval dataset 생성 | `gpt-4o-mini` | 평가 문항 생성 |
| Embedding | `text-embedding-3-small` | 비용 대비 검색 성능 |
| Reranker | `ms-marco-MiniLM-L-12-v2` | 로컬 cross-encoder reranking |
| Agent temperature | 0~0.3 | 수치/분류는 낮게, 식단 생성은 약간 유연하게 |

**ms-marco-MiniLM-L-12-v2는 무엇인가?**
- MS MARCO 검색 데이터셋 계열로 학습된 MiniLM 기반 cross-encoder reranking 모델
- query와 passage를 함께 보고 관련도 score를 계산
- Pinecone/BM25가 가져온 후보 문서 중 **정말 질문과 맞는 문서**를 다시 정렬하는 데 사용
- LLM 호출이 아니라 로컬 reranker이므로 토큰 비용이 들지 않음

---

## Slide 16. 성능 검증: Routing Evaluation

**목적**
- Supervisor가 올바른 Agent로 routing하는지 확인

**결과**

| 지표 | 결과 |
|---|---:|
| 평가 케이스 수 | 18 |
| Intent accuracy | 1.00 |
| Route accuracy | 1.00 |
| Confusion | 없음 |

**케이스 예시**
- "닭가슴살 200g 먹었어" → `diet_logger`
- "내일 하루 식단 좀 짜줘" → `meal_plan`
- "응 확정해줘" → `confirm`
- "인바디 결과 분석해서 전략 업데이트 해줘" → `inbody`

**주의**
> synthetic case 기준이므로 실제 사용자 오타/구어체는 smoke test로 보완했습니다.

---

## Slide 17. 성능 검증: RAG Evaluation

| 모드 | n | Page hit | Source hit | Excerpt hit | Avg score | Citation rate | Faithfulness |
|---|---:|---:|---:|---:|---:|---:|---:|
| dense | 10 | 0.80 | 1.00 | 0.70 | 0.817 | 1.00 | 1.00 |
| hybrid | 10 | 1.00 | 1.00 | 0.90 | 0.817 | 1.00 | 1.00 |
| full | 10 | 1.00 | 1.00 | 0.90 | 0.978 | 1.00 | 1.00 |

**개선지표**

| 개선 | 결과 |
|---|---|
| dense → hybrid | Page hit 0.80 → 1.00, Excerpt hit 0.70 → 0.90 |
| hybrid → full | Avg score 0.817 → 0.978 |
| citation/faithfulness | 1.00 유지 |

**발표 메시지**
> dense만으로도 문서는 찾았지만, page와 근거 문단 정밀도는 hybrid/RRF와 reranking을 넣었을 때 개선됐습니다.

---

## Slide 18. LangSmith / Observability

**사용 목적**
- Agent 실행 trace 확인
- 어떤 node에서 시간이 걸리는지 확인
- LLM 호출 입력/출력 추적
- eval dataset 업로드 및 실험 비교

**설정**

```text
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=diet-agent
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
```

**보고서에서 말할 표현**
> LangSmith tracing을 통해 Agent 실행 과정을 관찰할 수 있게 구성했고, local eval 결과는 JSON으로 저장하여 routing/RAG 성능을 재현 가능하게 관리했습니다.

---

## Slide 19. 내가 무엇을 개선하려고 했는가?

**개발에서 중요하게 본 기준**

| 기준 | 실제 구현 |
|---|---|
| 정확한 수치 | 영양성분은 CSV lookup |
| 근거 있는 조언 | RAG + 출처 + page |
| 안전한 저장 | HITL confirm |
| Agent 역할 분리 | supervisor / logger / planner / validator / inbody / reporter / edit |
| 복구 가능성 | checkpointer + rollback |
| 검증 가능성 | routing eval + RAG eval |
| 오작동 방지 | grounded flag, threshold, heuristic guardrail |
| 사용자 현실성 | 사진은 음식명만, 양은 사용자 확인 |

**발표 메시지**
> 가장 중요하게 본 것은 "LLM이 신기하게 대답하는 것"이 아니라, 사용자의 건강 기록을 안전하고 설명 가능하게 다루는 것이었습니다.

---

## Slide 20. 개선 과정: Before / After

| 문제 | 개선 |
|---|---|
| 단순 dense RAG | BM25 + RRF + FlashRank reranking 추가 |
| 출처 없는 조언 가능성 | grounded flag와 guardrail 추가 |
| LLM이 끼니/양 추측 | 사용자 g 입력 + meal type 선택 |
| 식단 저장 전 오류 가능성 | confirm interrupt 추가 |
| meal_plan 품질 불안정 | validator subgraph 피드백 루프 |
| routing 오분류 | LLM supervisor + heuristic guardrail |
| 대화 상태 복구 어려움 | checkpoint history + rollback |

**한 줄**
> 기능을 많이 붙이는 것보다, Agent가 틀릴 수 있는 지점을 찾아 안전장치를 추가하는 방향으로 개선했습니다.

---

## Slide 21. Demo Scenario

**시나리오 1: 자연어 식단 기록**
```text
사용자: 아침에 현미밥 200g 닭가슴살 150g 먹었어
→ diet_logger
→ CSV 영양성분 계산
→ confirm 대기
→ 사용자 확정
→ meal_logs 저장
```

**시나리오 2: 저녁 치킨 약속**
```text
사용자: 오늘 저녁 치킨 약속 있는데 아침 점심 어떻게 먹을까?
→ strategy
→ 현재 목표/남은 칼로리 기반 조언
```

**시나리오 3: 인바디 갱신**
```text
인바디 사진 업로드
→ OCR/Vision
→ inbody_logs 저장
→ inbody Agent
→ diet_strategies 갱신
```

---

## Slide 22. 한계와 다음 개선

| 현재 한계 | 다음 개선 |
|---|---|
| RAG 문서 수가 많지 않음 | 영양지식 PDF corpus 확장 |
| 영양성분은 CSV lookup 중심 | 브랜드/외식 메뉴 DB 확장 |
| 실제 사용자 평가 부족 | 실제 시나리오 기반 eval set 확장 |
| 일부 DB/RAG 호출은 node 내부에 남음 | tool-only boundary 강화 |
| GraphRAG/Exa 미적용 | 과제 이후 외부 검색/GraphRAG 실험 |
| 인바디 OCR 품질은 실제 이미지 의존 | OCR confidence 및 수동 보정 UI 추가 |
| 목표가 방향성 중심임 | `target_weight_kg`, `target_date`, `goal_priority`를 장기 목표 state로 저장 |

**장기 목표 관리 확장**

현재 MVP는 목표 방향성(다이어트/증량/유지)과 인바디 기반 전략 조정을 구현했다. 향후 확장에서는 `target_weight_kg`, `target_date`, `goal_priority`를 장기 목표 state로 저장하고, `Goal Manager Agent`가 목표 달성률, 감량 속도, 근손실 여부를 평가해 전략을 재설정하도록 확장할 수 있다.

**향후 개선 시나리오 예시**

> 최근 한 달 동안 평균 섭취 칼로리는 목표보다 하루 180kcal 높았습니다. 체중은 0.5kg 감소했지만 목표 감량 속도보다 낮습니다. 골격근량은 유지되었으므로 근손실 위험은 낮습니다. 따라서 다음 2주 동안 단백질은 유지하고, 하루 평균 섭취 칼로리를 150kcal 낮추겠습니다.

**발표 메시지**
> MVP에서는 안정성과 설명 가능성을 우선했고, 이후에는 corpus 확장과 실제 사용자 평가셋 구축이 핵심 개선 방향입니다.

---

## Slide 23. 포트폴리오용 마무리

**제가 보여주고 싶은 역량**

| 직군 역량 | 프로젝트에서 보여준 것 |
|---|---|
| AI Agent Engineer | LangGraph orchestration, subgraph, HITL, checkpoint |
| LLM Engineer | prompt, guardrail, grounded generation, routing eval |
| AI Engineer | RAG pipeline, embedding, reranking, eval, tracing |
| Backend Engineer | FastAPI, Supabase, DB state, API 설계 |
| Product-minded Engineer | 기존 앱 한계 분석, 사용자 오류 방지 UX |

**마무리 문장**
> MetaDiet AI는 LLM을 단순 챗봇으로 쓰는 것이 아니라, 사용자의 건강 데이터를 다루는 Agent 시스템으로 구성하고, 검색 근거와 사용자 확인, 평가 지표를 통해 안정성을 높인 프로젝트입니다.

---

## 부록 A. PPT에 넣을 핵심 숫자

| 항목 | 값 |
|---|---|
| Routing eval cases | 18 |
| Intent accuracy | 1.00 |
| Route accuracy | 1.00 |
| RAG eval QA cases | 10 |
| Dense page hit | 0.80 |
| Full page hit | 1.00 |
| Dense excerpt hit | 0.70 |
| Full excerpt hit | 0.90 |
| Full avg score | 0.978 |
| Citation rate | 1.00 |
| Faithfulness | 1.00 |
| RAG candidate k | 20 |
| Final retrieve k | 4 |
| Max context docs | 3 |
| Max chunk chars | 1200 |
| Chunk overlap | 150 |
| Dense threshold | 0.35 |
| Rerank threshold | 0.15 |

---

## 부록 B. 추천 발표 흐름

1. 왜 필요한가: 기존 앱 한계
2. 그래서 어떤 구조를 만들었나: Multi-Agent + LangGraph
3. 핵심 기술: RAG, chunking, reranking, grounded generation
4. 안전장치: HITL, guardrail, threshold, validator
5. 검증: routing eval, RAG eval, LangSmith
6. 개선 과정: 무엇을 어떻게 고도화했나
7. 포트폴리오 메시지: AI Agent/LLM Engineer로서의 설계 역량
