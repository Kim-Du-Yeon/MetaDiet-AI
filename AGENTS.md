# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Performance verification policy

For new speed or accuracy comparisons, run at least 100 attempts per condition on the same frozen cases. Keep failures/timeouts in the denominator and distinguish synthetic evaluations from actual user outcomes. Smaller smoke tests verify functionality only; they are not performance evidence.

## Project

MetaDiet AI — a LangGraph multi-agent diet coaching system. FastAPI backend, React frontend, Supabase Postgres, Pinecone for hybrid RAG. Full architecture is documented in [ARCHITECTURE.md](ARCHITECTURE.md) (with mermaid diagrams per subsystem) and evaluation methodology in [EVALUATION.md](EVALUATION.md) — read those before making non-trivial changes to the graph, RAG pipeline, or eval scripts.

**기능 완성도: ~95%** — 남은 작업은 선택적 개선("남은 선택 작업") + 상용화 인프라("다음 단계") 뿐.

## 완료된 작업

| 커밋 | 내용 |
|---|---|
| `d0e0d4e` | 멀티유저 인증(JWT, Supabase Auth) + 회귀 버그 3개 수정(user_goal 하드코딩, edit 날짜범위, RAG 가드레일 inbody/reporter) |
| `e533f67` | meal 소유권 검증(403/404) + edit CSV lookup + source 컬럼 영속화 |
| `cc430e8` | RAG 가드레일 전면 통일(rag_nutrition_tool까지 grounded 게이팅 적용) |
| `2cd47ad` | Goal Manager Agent 구현(채팅 intent + inbody 자동 체이닝) |
| `a4722c1` | 온보딩 목표 입력 UI(target_weight/date/goal_priority) |
| `4ee901f` | 한국어 RAG 개선(query translation + dual query expansion + text-embedding-3-large) |
| `897adc2` | 한국어 RAG 개선 eval 리포트(KO faithfulness 0.20→0.85, context_recall 0.30→0.95) |
| `74be150` | pytest 테스트 스위트 구축(**52** tests: unit/security/rag/integration) + goal_manager 계산 로직 순수 함수 분리 |
| `e9fc4f0` | source 표기 통일(csv/llm_estimated) + 죽은 `AgentState.source` 필드 제거 + AGENTS.md/EVALUATION.md 갱신 |
| `2cd2460` | `nutrition_db.py` 죽은 source 필드 제거 + EVALUATION.md 7장 본문 재작성 |
| `51f0277` | goal_manager 과민 분류 회귀 수정(gym/운동 발화→strategy) + 평가 데이터셋 보강(routing +5/edge +6) + Tool 호출 검증 테스트 추가(→ pytest **57**개) |
| `8c4c348` | 멀티턴/루프 평가 구현(`run_multiturn_eval.py`, 3시나리오) + LangSmith `thread_id` metadata 명시적 전파 |
| `296ee1f` | region 온보딩 UI + RAG KR/INTL 프롬프트 분기(`qa.py`) + `build_rag.py` lang 메타데이터 태깅 |
| `b20fa2c` | region 기반 KR/INTL RAG 프롬프트 분기 8개 노드 적용(`region_guidance.py` 공유) + 한국어 코퍼스 추가(KDRIs 2개+비만진료지침, 3396청크 재인덱싱) + `guideline2022_vol8.pdf` lang 오태깅 수정 + pytest 65개 |
| `8832a71` | 멀티턴 평가 시나리오 D 구현(validator 피드백 루프 품질 추적, trend: improving) + LLM judge GPT-4o mini(eval 전용) + meal_plan JSON 파싱 재시도 버그 수정 + pytest 67개 |
| `5d6a8a3` | kiwipiepy BM25 형태소 분석기 적용(`retriever.py: kiwi_tokenize()` 모듈 싱글턴, 실패 시 공백분리 폴백) + pytest 71개 + ragas 재측정(EN faithfulness/context_recall 0.95/0.90, KO 0.85/0.95 — EN recall 0.70→0.90 회복) |
| `2f17025` | off-topic 리다이렉트 구현(9번째 intent, LLM 분류, off_topic 노드는 LLM 호출 없음) + routing eval 26/26=1.0 + pytest 73개 |
| `8111eeb`~`2d279aa` | 로컬 실행 정비: 백엔드 포트 8000→8080, 프론트 `dietApi.js` BASE_URL을 `REACT_APP_API_URL` 환경변수 참조로 전환(Setup.jsx 잔존 하드코딩 포함), CORS `allow_origins`에 8080/127.0.0.1 추가, JWT 검증 ES256/RS256(JWKS) 우선 시도+HS256 레거시 폴백 |
| `1484b7f` | mixed intent(과거 식사 기록+오늘 식단 계획 동시 요청) 처리: supervisor 휴리스틱이 diet_logger 우선 라우팅 + 응답에 "기록 후 식단 계획을 세워드릴까요?" 안내 |
| `1233f24` | edge_dataset `empty_or_irrelevant` 골드 라벨 갱신(strategy→off_topic, off_topic intent 도입 후 stale했던 라벨 수정) → routing 26/26, edge 24/24, pytest 73 전체 1.0 |
| `6be33b6` | confirm 노드 `unrelated` 분류 추가 — pending 중 식단과 무관한 발화(날씨 등)를 confirm으로 오분류해 임의 저장하던 버그 수정, "확정하시겠어요?" 안내로 pending 유지 + pytest 75개 |
| `8773f23` | meal_plan 프롬프트에 목표 칼로리 90% 하한 + 오늘 섭취량 차감 지시 추가(칼로리 심각 미달 버그 수정), 전날 섭취 비교 문구의 부호 모순 수정(재계산 금지, 기존 계산값 그대로 사용), diet_logger mixed-intent 안내문을 "식단 짜줘" 직접 요청 유도로 변경 + pytest 76개 |

**현재 로컬 실행 가능/정상 확인 완료** — 위 정비로 백엔드/프론트 포트 불일치, CORS 차단, JWT 검증 실패 이슈 해소.

## 남은 선택 작업

- **AsyncPostgresSaver 커넥션 풀링**: 상용화 안정성(현재는 단일 커넥션, 알려진 한계 참고).
- **소셜 로그인(카카오/구글)**: 한국 시장 대응.
- **푸시 알림**: 식사 리마인더.

## 다음 단계: 상용화 인프라

- 서버 배포(Render/Railway/AWS)
- React Native 전환
- 앱스토어 등록(iOS/Android)
- 결제 시스템(구독/인앱결제)
- 개인정보처리방침/이용약관

## 핵심 설계 결정

- **JWT 2-tier**: `auth_id`(Supabase `auth.uid()`, JWT의 `sub`) vs `users.id`(내부 PK, `meal_logs`/`diet_strategies` 등의 FK) — `get_current_auth_id`/`get_current_user`로 분리(`app/core/auth.py`).
- **`goal_priority`**: `"speed"`(감량속도 우선) / `"muscle"`(근손실 방지 우선) / `"balance"`(균형) 3값.
- **`source` 표기**: `"csv"` / `"llm_estimated"`로 영문 통일(이전엔 diet_logger가 한글 "국가표준식품성분표"/"LLM 추정"을 따로 썼음).
- **RAG 지역 우선순위**: `region="KR"`이면 KDRIs를 최우선 적용하고 없는 내용은 WHO 등으로 보완(충돌 시 KDRIs 채택). `region="INTL"`이면 WHO 우선, 한국 특이 식품/식문화는 KDRIs 참고. 항상 출처 명시. 가드레일 문구는 `app/rag/region_guidance.py: get_region_guidance()`로 단일화돼 `qa.py` + 실채팅 8개 노드(diet_logger/meal_plan/strategy/inbody/reporter/goal_manager/validator/rag_nutrition_tool)가 공유.
- **임베딩**: `gemini-embedding-2`, 3072차원. 파서·청킹·차원·검색 실험 뒤 활성 namespace를 분리했으며 OpenAI 벡터와 혼합하지 않는다.
- **BM25**: 형태소 분석기 `kiwipiepy` 적용 완료(`retriever.py: kiwi_tokenize()`, 모듈 레벨 `Kiwi()` 싱글턴, 분석 실패 시 공백분리로 폴백) — `BM25Retriever.from_documents(..., preprocess_func=kiwi_tokenize)`.
- **평가 LLM judge**: 운영과 평가는 Gemini만 사용하되 역할을 분리한다. 독립 RAG 최종 평가는 `gemini-3.8-flash` 생성과 `gemini-3.1-pro-preview` Ragas judge로 수행했다.
- **LangSmith `thread_id`**: `{user_id}_{thread_id}` 합성값을 `config["metadata"]["thread_id"]`로 명시 전파(`main.py`의 `graph.ainvoke()` 호출부 5곳) — `configurable.thread_id`만으로는 trace에 안 묻어서 별도로 넣어야 함.
- **모니터링 구조 (개발 vs 운영)**: 개발 시엔 `run_ragas_eval.py` 등 수동 eval 스크립트로 회귀 검증. 운영 시엔 LangSmith 실시간 트레이싱(`thread_id` 전파로 요청 단위 추적) + 주기적 샘플링 평가(ragas/routing eval 재실행)로 운영 품질을 모니터링하는 구조.
- **서비스 날짜**: 상대 날짜·오늘 집계·전략 적용일은 `SERVICE_TIMEZONE`(기본 `Asia/Seoul`)의 `service_today()`를 사용한다.

## 알려진 한계/주의사항

- **`AsyncPostgresSaver` 연결 풀 적용**: `AsyncConnectionPool(min_size=1, max_size=10, timeout=15)`을 사용한다. 실제 배포 DB의 연결 상한·pool timeout·장애 복구 알림 임계값은 운영 부하 테스트에서 확정해야 한다.
- **Supabase SQL 미실행**: `backend/scripts/migrations/add_region_column.sql` — 실행 전까지 `region`은 항상 기본값 `"KR"`로 폴백(try/except로 감싸져 있어 에러는 안 남).
- **대화 thread migration 적용 완료**: `20261011120000_chat_history_thread_id.sql`을 실제 Supabase에 적용했다. 기존 행은 `legacy`, 신규 행은 실제 thread ID를 사용한다.
- **ragas는 별도 venv 필수**: `venv_ragas`에 `ragas==0.2.15` + `langchain-community==0.4.1`(정확히 이 버전 — `langchain-experimental`은 설치하지 말 것, `>=0.4.2`를 요구해서 충돌남). 메인 `requirements.txt`엔 안 들어감.
- **Windows: `SelectorEventLoop` 필수**: `backend/main.py` 상단의 `WindowsSelectorEventLoopPolicy` 설정을 건드리지 말 것 — 빼면 체크포인터(`psycopg` 비동기 드라이버)가 깨짐.
- **RAG 최종 한계**: 동결한 독립 20문항에서 Ragas faithfulness 1.00/context recall 0.95, source-reviewed correctness 95%다. 유일한 실제 근거 누락은 영어 질의가 WHO 아동 외삽 문장을 검색하지 못한 사례이며 안전하게 답변을 보류했다. 영어 query expansion은 이 최종셋이 아닌 별도 개발셋에서만 실험한다.

## 다음 세션 시작 방법

```
AGENTS.md 읽고 현재 상태 파악한 후 [작업명] 이어서 진행해줘.
```

## Commands

**Always use the project venv at `backend/venv`** — the system/Windows-Store `python` is a stub and will fail (exit 49). There is no other interpreter to use.

Backend (from `backend/`, **관리자 권한 터미널**에서 실행):
```
venv\Scripts\activate
python main.py                       # runs on :8080, reload via UVICORN_RELOAD=true
```
Or without activating: `backend\venv\Scripts\python.exe <script>`.

Frontend (from `frontend/`):
```
npm start     # dev server, :3000
npm run build
npm test
```
`frontend/.env` 필요: `REACT_APP_SUPABASE_URL`, `REACT_APP_SUPABASE_ANON_KEY`, `REACT_APP_API_URL=http://localhost:8080`.

Env setup: `cp backend/.env.example backend/.env` and fill in `GEMINI_API_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `SUPABASE_JWT_SECRET`, `SUPABASE_DB_URL`, `PINECONE_API_KEY`, and `LANGSMITH_API_KEY` when tracing. OpenAI credentials are not used.

RAG index build (from `backend/`, after changing chunking/config or adding PDFs to `docs/nutrition`):
```
python scripts/build_rag.py
```

Evaluation scripts (from `backend/`, see "Evaluation datasets" below for which dataset goes with which script):
```
python scripts/eval/run_routing_eval.py --dataset routing_dataset.json   # or edge_dataset.json
python scripts/eval/run_eval.py --mode dense|hybrid|full --dataset qa_dataset.json --k 4
python scripts/eval/run_ragas_eval.py --dataset gold_dataset.json --mode full --k 4 [--limit N]
python scripts/eval/run_multiturn_eval.py   # 멀티턴/HITL/루프 시나리오, MemorySaver+mock DB로 in-process 실행
```
`run_ragas_eval.py` depends on `ragas==0.2.15`, which is **not** in `requirements.txt` — install it in a separate venv (e.g. `venv_ragas`). In that env, pin `langchain-community==0.4.1` and do **not** install `langchain-experimental`: ragas 0.2.15 imports `langchain_community.chat_models.vertexai`, which `langchain-community` removed starting 0.4.2, and `langchain-experimental` would force `langchain-community>=0.4.2` right back, recreating the conflict.

Tests (from `backend/`):
```
pytest                                # tests/{unit,security,rag,integration}/ 전체 회귀
```
External Gemini/Pinecone/Supabase calls are mocked in ordinary unit/integration tests; live evaluation scripts are separate and require configured credentials. `pytest.ini` sets `asyncio_mode = auto`.

Demo data: `python scripts/seed_data.py` (3 months synthetic) / `python scripts/seed_male_demo_data.py` (presentation demo data). Graph visualization: `python scripts/visualize_graph.py` → `graph.png`.

## Architecture

### Multi-agent graph

`backend/app/agents/graph.py` builds the LangGraph `StateGraph`. Every request: `load_state` (loads today's intake/targets/latest inbody/goal/region fields from DB) → `supervisor` (LLM intent classification into one of 8 intents, with heuristic guardrails in `supervisor/node.py: _heuristic_intent()` for high-cost-of-error cases like confirm/edit/inbody/reporter/goal_manager) → routed agent → `save_chat` → END.

Key routing invariant (`route_to_agent` in `supervisor/node.py`): if `awaiting_confirmation=True` and intent isn't one of `[confirm, edit, diet_logger, strategy]`, force-route to `confirm` so a pending meal proposal can't be abandoned mid-flow.

Agents live one per directory under `backend/app/agents/<name>/node.py`: `diet_logger`, `confirm` (HITL gate), `strategy`, `meal_plan`, `validator`, `inbody`, `goal_manager`, `reporter`, `edit`, `supervisor`. `confirm` is wired with `interrupt_before=["confirm"]` — the graph pauses there until the user responds via `/chat/resume`.

`inbody` auto-chains into `goal_manager` (`graph.py`: `inbody → goal_manager → save_chat`) so every InBody upload also gets a goal-progress check, in addition to `goal_manager` being directly reachable via its own chat intent. `goal_manager_node` appends to `state["response"]` rather than overwriting it (`_append()` helper) specifically so the chained case doesn't clobber `inbody`'s own analysis text. Its progress/rate math is split into pure functions (`_calc_goal_progress`/`_calc_weekly_rate`/`_calc_needed_weekly_rate`) for unit testability.

### meal_planner subgraph

`build_meal_planner_subgraph()` in `graph.py` encapsulates a `meal_plan ↔ validator` feedback loop as a single parent node so the HITL/checkpointer behavior outside it is unaffected. `validator` scores the generated plan against nutrition targets; on failure with `validation_attempts < 3` it loops back to `meal_plan` with feedback, otherwise force-passes (`validator/node.py:26`) and hands off to the parent's `confirm`.

### State and reducers

`AgentState` (TypedDict) in `backend/app/schemas/models.py` is the shared state channel set. Each field has an explicit reducer because LangGraph errors on multi-write without one within a step:
- `keep_latest` — overwrite (most scalar fields, including `message` for `/chat/resume` injection)
- `add_messages` — append (`messages`)
- `merge_pending_meals` — `None` clears the pending proposal, otherwise replace
- `keep_max` — monotonic counter (`validation_attempts`, survives the subgraph loop)

`forced_meal_type` lets the frontend's meal-type buttons override `diet_logger`'s LLM-guessed meal type (falls back to LLM guess if absent). `rag_context`/`rag_grounded` are populated once per graph run (by `meal_plan` or whichever agent searches first) and reused by `validator` to avoid duplicate retrieval and token spend. `target_weight_kg`/`target_date`/`goal_priority`/`user_region` are loaded once by `load_state` from `users` and otherwise treated as read-mostly config for the rest of the run.

### RAG pipeline

`backend/app/rag/retriever.py` exposes `retrieve(query, k, use_hybrid, use_rerank)`. Korean queries use translation plus original-query expansion, then Pinecone dense search and Kiwi BM25 are fused by RRF. The selected production recipe is PyPDF + recursive chunks + `gemini-embedding-2` 3072 dimensions + Hybrid + no reranker. FlashRank remains an ablation option but defaults off because it reduced measured quality and contributed to exceeding the 1GiB Pod memory budget. `answer_from_knowledge()` and live Agent prompts use the same grounded gate and KR/INTL source priority. Changing the embedding model or dimension requires a new namespace and reindex.

Index is built by `backend/scripts/build_rag.py`: `PyPDFLoader` (keeps page metadata) → junk-page filter → `SemanticChunker` → hard size cap (max 1200 chars / 150 overlap) → Pinecone upsert + local `chunks.pkl` for BM25. Each chunk also gets a `lang` metadata tag: `_FILENAME_LANG_OVERRIDES` dict checked first (for English-named-but-Korean-content PDFs, e.g. `guideline2022_vol8.pdf`), otherwise falls back to Hangul-in-filename detection. Source PDFs live in `docs/nutrition/`.

Nutrition *values* (calories/macros) are deliberately **not** RAG — they're deterministic CSV lookups against `docs/nutrition/식품성분표_10개정판.csv` via `app/tools/nutrition_db.py`, to avoid hallucinated numbers. RAG is reserved for explanatory nutrition knowledge/strategy advice that needs document grounding.

### Checkpointing / time travel

`AsyncPostgresSaver` (Supabase Postgres) persists a state snapshot per node per `thread_id`. `/chat/history/{thread}` lists checkpoints, `/chat/rollback` restores one and lets the conversation resume from that point — used e.g. to fix a previously-confirmed meal without duplicating DB rows (`overwrite_on_confirm` flag tells `confirm` to replace rather than append). The actual `thread_id` passed to `graph.ainvoke()`/`.aget_state()` is always `f"{user_id}_{thread_id}"`; `main.py` also passes the same composite string as `config["metadata"]["thread_id"]` so it's discoverable in LangSmith traces (verified live via `Client().list_runs()` in `run_multiturn_eval.py`).

**Windows-specific**: `psycopg`'s async driver requires `SelectorEventLoop`, not the default `ProactorEventLoop`. `backend/main.py` sets `WindowsSelectorEventLoopPolicy`; don't replace it with a default loop. `AsyncPostgresSaver` receives an `AsyncConnectionPool(min_size=1,max_size=10,timeout=15)`; tune the maximum against the deployed Supabase connection limit.

### Authentication

Every endpoint except `/health` and `/nutrition/lookup` requires `Authorization: Bearer <supabase_jwt>`. `app/core/auth.py` has two FastAPI dependencies, and they return **different UUIDs** — don't mix them up:
- `get_current_auth_id` — just decodes the JWT and returns `sub` (Supabase `auth.uid()`). Doesn't require a `users` row to exist, so it's the one `/users/setup` uses (a brand-new signup has no `users` row yet; that endpoint upserts one).
- `get_current_user` — wraps the above, then looks up `users.id` from `auth_id`. *This* is the value the rest of the app calls `user_id` and what `meal_logs.user_id`/`diet_strategies.user_id` etc. actually reference as their FK.

### Vision / OCR

Vision is used only for *parsing*, never for deciding grams or whether to save — that's always a user-confirmed step through `/chat` (`diet_logger`). `app/ocr/food_vision.py` (food photo → food names only) and `app/ocr/inbody_ocr.py` (InBody photo → measurements, with prompt guardrails against misreading body-water/protein/mineral rows as body weight, corrected against history). `app/ocr/image_classifier.py: classify_image_type` lets a single camera button on the frontend dispatch to either path via `POST /image/upload`.

## Evaluation datasets

Each evaluation domain has its own dataset + script; don't conflate them (see [EVALUATION.md](EVALUATION.md) section 8 for the full table):

| Dataset | Used by | Gold field | Measures |
|---|---|---|---|
| `routing_dataset.json` | `run_routing_eval.py` | `expected` (agent label) | baseline routing accuracy, now 23 cases / 8 intents |
| `edge_dataset.json` | `run_routing_eval.py` | `expected` + `edge_type` | routing robustness on typos/mixed intent/etc, now 24 cases / 6 edge types |
| `qa_dataset.json` | `run_eval.py` | `gold_source`/`gold_page`/`gold_excerpt` | dense vs hybrid vs full RAG retrieval ablation (custom metrics, no Ragas) |
| `gold_dataset.json` | `run_ragas_eval.py` | `gold_answer` + `language` | Ragas `faithfulness`/`context_recall`, EN/KO cross-lingual comparison |

`*_report*.json` files are reproducible outputs, not inputs. The independent post-selection RAG evaluation is documented in `docs/rag_experiments/RAG_FINAL_EVALUATION_V1.md`: 20/20 completed, strict source-page Recall@4 85%, adjudicated evidence support 95%, source-reviewed correctness 95%, Ragas faithfulness 1.00/context recall 0.95. The selected corpus has 10 PDFs and 4,139 active chunks.

## Imported Claude Cowork project instructions

이 프로젝트는 LangGraph 기반 Multi-Agent 식단 코칭 시스템이다.

목표는 기존 구조를 최대한 유지하면서, 현재 미흡한 항목들을 포트폴리오에 설명 가능한 수준으로 개선하는 것이다.

개선할 항목:
1. 골드 데이터셋 구축
2. ragas 또는 LlamaIndex 기반 RAG 평가
3. LangSmith 실질 활용
4. 청킹 파라미터 설정 확인 및 config화
5. RAG 유사도 임계값 확인 및 일관화
6. Edge case 체계적 테스트 구축

현재 이미 구현된 것으로 간주할 항목:
1. HITL / 루프 방지
2. State 장단기 분리
3. LangGraph 기반 Multi-Agent 구조
4. Hybrid RAG / reranking / grounded generation의 기본 구조
5. Routing evaluation과 RAG evaluation의 일부 결과

작업 원칙:
- 처음부터 전체 코드를 읽지 않는다.
- 먼저 project_files.txt, code_outline.txt, README.md, ARCHITECTURE.md, EVALUATION.md, PPT_OUTLINE.md만 기반으로 구조를 파악한다.
- 아직 파일을 수정하지 않는다.
- 전체 구조를 새로 갈아엎지 말고 기존 LangGraph, AgentState, RAG, HITL, checkpointer 구조를 유지한다.
- 이미 구현된 기능과 부족한 기능을 구분한다.
- 필요한 경우 다음 단계에서 읽을 핵심 파일만 추천한다.
- 각 개선 항목별 확인 파일 후보는 최대 3개로 제한한다.
- 이틀 안에 구현 가능한 우선순위를 제시한다.
- VSCode Claude에게 줄 수 있는 작은 작업 단위 명령어로 쪼갠다.
- 코드 전문을 길게 출력하지 말고 요약 중심으로 답한다.
