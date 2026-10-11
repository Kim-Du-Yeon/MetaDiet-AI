# MetaDiet upgrade — execution ledger

Approved scope: seven-day Gemini multi-agent upgrade; autonomous tool selection
with explicit user constraints; feedback budgets and HITL; separate plans/intake;
versioned strategies; PyPDF/Docling/OCR/Markdown/table/image parsing experiments;
chunking/embedding/retrieval comparison; 120 reviewed evaluation examples plus
24 parser pages; Ragas, AgentEvals and deterministic evaluation; LangSmith;
streaming; weekly Deep Agent; read-only MCP; container/kind recovery demo.
After backend functionality and evaluation, implement Cue-inspired streaming UI:
https://seo.tbwakorea.com/blog/what-is-naver-cue/
Show actual execution progress, verified answer/meal cards, citations, follow-up
actions and confirmation controls. Full UI design comes after the functionality.

## 2026-10-11 account deletion propagation

- Added explicit-confirmation deletion across application rows, durable execution state and Supabase Auth.
- Added account-level shared/exclusive advisory locking so active Agent runs finish before deletion and waiting runs cannot recreate checkpoints afterward.
- Verified the real Supabase path with isolated synthetic target/control data: target Auth/user/chat/checkpoint all removed; control rows preserved.
- Full backend regression: 339 passed, 1 skipped. Reproduction and failure analysis are in `EVALUATION.md` section 35.
- Added the settings deletion flow with password reauthentication, literal confirmation, retryable Auth-only cleanup, and local session removal.
- Sensitive deletion now checks a password AMR timestamp within five minutes and validates the JWT session against `auth.sessions`; refreshed token `iat` is not accepted as reauthentication.
- Real synthetic Supabase verification and frontend tests/build passed; details and the separated Admin/user-client failure analysis are in `EVALUATION.md` section 36.
- Added a hashed deletion tombstone plus lifecycle advisory lock so partial Auth deletion or a concurrent onboarding request cannot recreate application state.
- Applied RLS hardening to existing public domain/checkpoint tables after Supabase Advisor exposed disabled RLS and broad anon/authenticated grants; post-check has zero Advisor ERROR findings.
- Final verification for this stage: backend 348 passed / 1 skipped, frontend 22 passed, production build successful.

## Tasks
- [x] 1. Baseline, Gemini/Vision adapter, environment setup and tracing
- [x] 2. Plans/intake, OCR confirmation, strategy transactions, state lifecycle
- [x] 3. Autonomous agent delegation/tools, feedback and global execution budgets
- [x] 4. Document ingestion and controlled RAG experiment harness
- [x] 4a. Acquire and review ~10 Korean/English primary documents before comparisons
- [x] 4b. PyPDF/PDFPlumber/Docling on identical pages, then page/parent-child/section recipes
- [x] 4c. Latest-edition and claim-conflict policy, conflict gold and write-block integration
- [x] 5. Reviewed gold datasets, Ragas/AgentEvals, LangSmith experiments
- [x] 6. Actual streaming and client framing/reconnection
- [x] 7. Deep Agent, MCP, container/kind integration and recovery verification
- [x] 8. Cue-inspired UI after functional verification

## Decisions and evidence
- Ruling: full corpus migration uses an explicit recursive-cap provisional
  baseline (`--chunking recursive`) because the 1,953-page semantic baseline
  performs per-sentence sequential embedding and made no timely progress.
  Original semantic option is preserved; parser/chunking quality comparisons
  still decide the final recipe. Metadata/build IDs distinguish the baseline.
  Gemini document embeddings use four bounded workers and model/dimension/input
  hashed vector caches for restart reuse; health queries are not cached.
- Durable execution budgets now reserve model/tool/validation/replan/delegation
  usage before effects, restore counters independently of graph checkpoints,
  exclude normal HITL waiting and conservatively count hard-crash intervals.
  Applied `20261009090000_execution_budgets.sql`; real DB restart/concurrent-limit
  checks passed and synthetic execution rows were deleted. Fresh review found
  storage-outage, delegation recovery and proposal timeout issues; fixed them.
- Ragas 0.2.15 failed on removed `langchain_community.chat_models.vertexai`.
  Installed community 0.4.1 without dependencies into artifacts/ragas-runtime,
  leaving the API packages unchanged. Gemini Pro synthetic smoke evaluation
  succeeded (faithfulness/context recall 1.0/1.0); this is connectivity evidence,
  NOT a corpus or service quality score. Evaluation failures are no longer
  silently converted to zero. Reviewed final gold and full comparisons remain.
- 2026-10-09 connection follow-up: Supabase Session/DB connection succeeded
  using the required Windows Selector event loop. Applied additive migration
  `20261008233749_agent_proposals.sql` in one transaction. Real remote transaction
  checks passed plan/intake separation, idempotency, stale versions, ownership,
  intake/strategy rollback and replacement/deletion cases. Synthetic test data
  was rolled back; the separately committed migration remains installed.
- Pinecone project access and configured index existence verified. LangSmith
  project listing and synthetic trace write/read verified; no health data was
  sent. Docker engine 29.4.3 is running. These checks remove the earlier remote
  connection prerequisite; they do not establish full deployment success.
- Full Gemini corpus rebuild remains running (exec session 99939); no activation
  or final retrieval/Ragas quality score claimed. Crash-durable per-call budgets,
  reviewed gold and later streaming/Deep Agent/MCP/kind/UI work remain required.
- Existing untracked AGENTS.md is user material and will not be overwritten.
- Work branch: codex/metadiet-agent-upgrade. Current checkout reused to preserve
  the configured venv and private local settings. No changes committed or pushed.
- Baseline: 76 tests passed before source migration. Final expanded regression
  suite: 101 passed (3 pre-existing deprecation warnings). Frontend: 4 SSE tests
  passed and production build succeeded. Python compileall and git diff --check
  passed. Test temporary directory was explicitly placed inside this workspace
  because the default Windows temporary directory denied access.
- Gemini adapter installation: langchain-google-genai 4.4.0 requires
  langchain-core >=1.6.1; installed 1.6.8; pip check passed.
- Existing OpenAI vectors must remain usable until the Gemini corpus is rebuilt.
  Do not silently point a new embedding model at old vectors.
- No live keys or user data are copied into this document.
- Gemini model ID verified against https://ai.google.dev/gemini-api/docs/models
  on 2026-10-09. Native capability probe uses synthetic text only.
- Independent review findings addressed: stale vectors after corpus changes,
  malformed tool call success, ablation context mismatch, and unverified printed
  page labels. Actual Pinecone corpus rebuild has not been executed.

## Implemented and verified so far
- Shared lazy Gemini chat/Vision adapter, append-only environment setup. Existing
  local settings preserved. Native tool calling + result continuation, structured
  output and native streaming passed a synthetic live Gemini probe.
- Vision MIME handling; no import-time OpenAI OCR clients. Legacy evaluation judge
  migrated to Gemini. Existing OpenAI embeddings are intentionally still active.
- Validator failure/exhaustion now blocks proposals instead of force-passing;
  parent LangGraph does not interrupt at confirm for blocked proposals. Invalid
  confirmation classifications no longer default to approval. New runs reset
  validation counters and retrieval caches.
- Generic model-selected tool loop with schemas, restricted allowlists, shared
  delegation budget, timeout and structured failure feedback. This runtime is
  unit-tested and now wired as the production supervisor (stage 2 below).
- Ragas answers now consume exactly the retrieval results being evaluated;
  a native Gemini BaseChatModel is provided to the Ragas wrapper.
- Numeric/short table pages preserved; each corpus/recipe gets a content-addressed
  namespace plus its own BM25 cache and activation manifest. Active retrieval is
  unchanged until explicitly switched after verification. Removed/changed documents
  cannot silently survive inside the new corpus. Stable IDs allow retrying a build.
- Local PyPDF/Docling parser interfaces export provenance JSON and review Markdown;
  Docling additionally exports table HTML. PyPDF fixture verified. Docling runtime,
  OCR, image extraction and comparative quality measurements remain unverified.
- Shared frontend SSE decoder handles split UTF-8/JSON frames and reports errors.
  Existing backend chat output is still buffered; this is not full end-to-end
  token streaming or durable replay yet.

## Still required for the approved complete scope
Remote activation of proposal tables; full OCR-to-strategy follow-up; crash-durable
per-call budgets; six-source corpus refresh; parser/OCR/table/image review; controlled
chunking/embedding/retrieval experiments; reviewed 120-case gold set plus 24 parser
pages; agent evaluation + LangSmith dataset/experiment integration; replayable
streaming; Deep Agent/MCP/container/kind recovery tests; final Cue-inspired UI.
Do not interpret passing regression tests as completion of these milestones.

## Completion rules
Do not claim corpus comparison, human gold review, external traces, deployment,
or live model capability checks have passed unless actually executed. Record
blocked and unverified checks explicitly. Keep existing data/index recoverable.

## Stage 2 — model-led workflow and durable approval (2026-10-09)

Implemented:
- Production LangGraph now invokes a model-led Supervisor with Meal, Goal and
  Evidence delegation tools. Specialists select their own tools. Legacy graph is
  retained explicitly for baseline tests, not the default production path.
- Shared model/tool/time budgets, structured error feedback, validation limits,
  restricted tool policies and a narrow record-only mode. CSV quote IDs bind meal
  proposals to server-calculated nutrition. Prior dialogue and profile constraints
  are available to the model. Pending proposals survive unrelated questions.
- Durable, versioned proposals for intake, plans, OCR measurements, strategy
  updates and meal replacement/deletion. Explicit approval uses ID/version;
  transactions enforce ownership, stale-state rejection and idempotency.
  Adopting a plan never inserts actual intake. OCR values remain editable before
  confirmation. Strategy activation and evidence/version storage commit together.
- Pooled PostgreSQL checkpointer and cross-process conversation advisory locks.
  Rollback cannot reactivate a resolved proposal or refund consumed call counts.
- Existing UI has minimal review/confirm/cancel and OCR correction controls.
  This is not the deferred Cue redesign or end-to-end token streaming.

Verification:
- Backend regression: 115 passed, 3 deprecation warnings. Frontend: 6 passed;
  production build succeeded.
- Live Gemini synthetic delegation/food lookup/proposal probe passed using a
  memory repository, with no health data or production writes.
- Disposable PostgreSQL 17: plan/intake separation, duplicate approval,
  ownership, stale proposals, partial-write rollback, atomic strategy rollback,
  meal replacement and stale deletion passed. Four simultaneous confirmations
  produced one intake row. Pooled checkpointer initialization/read passed.
- Independent review led to regressions for pending-proposal preservation,
  actual dashboard totals, rollback serialization and profile constraints.

Deployment prerequisite / limits:
- The configured remote SUPABASE_DB_URL timed out. No remote migration was
  applied. Restore connectivity, then apply the additive migration
  `supabase/migrations/20261008233749_agent_proposals.sql` using the deployment
  migration workflow before enabling this backend against the remote database.
  Existing meal_logs must already have the sodium_mg/source columns used by the
  previous application. Local fixtures explicitly supply these legacy columns.
- Live remote full-stack confirmation remains unverified. The local SQL probes
  use synthetic data and roll back/remove their test databases.
- Strategy proposals currently support immediate (today) activation only;
  scheduled activation, automatic post-OCR strategy review, durable per-call
  crash recovery and full event replay remain pending.
- Do not bypass approval to compensate for missing tables. Do not replace the
  existing vector index before the controlled RAG migration and evaluation.

Next approved milestone: parser/OCR/table/image evidence and controlled RAG
chunking/embedding/retrieval comparisons, reviewed gold data, Ragas and agent
evaluation with LangSmith experiments. Deep Agent/MCP/kind and the final
Cue-inspired streaming UI remain in their original later order.

## Stage 3 — corpus-first comparison and evidence policy (2026-10-09)

The corpus acquisition dependency was missing from the short milestone list.
It is restored before parser/chunking comparisons in `docs/rag_experiments/PLAN.md`.
Ruling: use PDFPlumber as the third parser, and page / parent-child / section as
the three new chunk recipes; retain the earlier semantic baseline separately.
PDFPlumber adds inspectable native tables/layout without a second large ML stack.
This choice may need revision if scanned-document quality dominates evaluation.

Acquired and PDF-validated eight new documents from official downloads: corrected
KDRIs 2025 volumes 1–3 and WHO carbohydrate/total fat/saturated-trans fat 2023,
sugars 2015, sodium 2012. The folder now preserves 15 PDFs; the explicit experiment
manifest selects 10 (4 Korean, 6 English) and excludes superseded/legacy files.
Inventory records source URLs, editions/errata, SHA256, population, usage notes,
and actual PDF page counts. Public download is not declared commercial permission.

Implemented common page/block artifacts for PyPDF/PDFPlumber/Docling, native
Docling JSON, table HTML, picture PNG, review Markdown and selected-page configs.
Parses have immutable run directories with parser version/config; chunk contexts
retain complete per-block citations and multi-page table provenance.
The comparator isolates parser dependencies/processes, records failures/timeouts,
expands parent contexts and exports exact retrieval contexts for later Ragas input.
It refuses final retrieval scores from unreviewed gold. Existing vector/DB data is
not modified. Legacy build_rag now obeys the corpus manifest and language/edition
metadata rather than silently mixing all 15 PDFs.

Latest-edition selection applies within the same family/population/conditions,
including same-year errata revision dates. Reviewed normalized numeric claim
policy uses applicability, regional official guidance and authority. Equal-priority
disagreement or incompatible units yields no selected target. Full raw-claim
extraction, recommendation-strength review and production write-block integration
remain pending; the selector is not yet an autonomous clinical adjudicator.

Pilot runs use the same 10 documents and 24 PDF pages, with page/parent-child/
section bundles. PyPDF/PDFPlumber completed all documents. Initial Docling native
backend failed on KDRI minerals; a diagnostic retry emitted an access-violation
stack even with exit zero, so such output is never promoted as valid. PDFium is
an explicit separate Docling configuration, not a silent per-document fallback.
Original errors and the alternative-backend comparison are retained in artifacts.

The API venv remains unchanged: optional parser packages are installed only in
`backend/artifacts/parser-runtime`. No broken API dependencies found. Tesseract
kor/eng is not installed, so scanned OCR was not executed. Two source page
renders were inspected; all 24 pages have NOT received final human review.
Do not label block/character/table counts as semantic quality or optimality.

Independent review identified and fixed provenance loss and artifact overwrites,
with failing regressions before the fixes. Reviewed gold/Ragas/embedding comparison,
LangSmith experiments and the rest of the original plan remain required.

Stage 3 final verification: main backend 130 passed, 1 optional-ingestion test
skipped, 3 deprecation warnings; PDFPlumber test passed separately in the isolated
runtime. Compileall, API pip check and git diff --check passed. Full 3×3 execution
pilot completed for all 10 documents/24 pages with explicit Docling PDFium backend.
Metadata-only results are in `docs/rag_experiments/PILOT_REPORT.md` and
`pilot_summary.json`. Native-backend failure logs are preserved. No retrieval/Ragas
quality score or optimal recipe is claimed from this execution pilot.

Evaluation role separation restored to the RAG plan: production generation/Vision/
online validation uses 3.8 Flash by default; 3.1 Pro Preview is a judge candidate,
not an automatically superior or already verified evaluator. Current service and
eval configuration defaults remain the same Flash model. Calibrate the candidate
on reviewed anchors, pin judge/model/library versions, retain deterministic agent
checks and record judge failures rather than mixing silent fallback scores.
Only documentation changed for this decision; no private environment was modified.
## 최신 검증 상태 — 2026-10-09 (아래 과거 단계 기록보다 우선)

외부 설정 입력은 완료됐다. 이번 실행에서 Gemini, Supabase DB, Pinecone,
LangSmith 접근을 확인했다. 네트워크·쿼터·외부 API 오류가 발생하지 않는다는
보장은 없으며, 이를 승인 대기나 성공으로 숨기지 않는다.

- Supabase 제안/실행 예산의 additive migration 두 개를 적용했다.
  계획/실제 섭취 분리, 중복 확정, 권한, 전략 원자적 롤백을 실제 DB에서
  합성 데이터로 검증했다. 실행 예산은 행 잠금으로 예약하며 새 인스턴스가
  기존 사용량을 복구한다. DB 장애 시 진행을 차단한다. 정상 HITL 대기 시간은
  제외하고 비정상 종료의 미종료 구간은 보수적으로 계산한다.
- Gemini Embedding 2 / 3072차원으로 선정 10문서, 1953페이지를 재색인했다.
  4139개 벡터의 개수와 PDF 1-based 인용 페이지를 확인한 namespace
  `metadiet-gemini-1157903c493dbb5d759f`를 활성화했다. 이전 벡터는 보존한다.
  전체 semantic 재색인은 문장별 원격 호출 비용/지연으로 중지했고,
  recursive 1200자/150자 overlap을 **임시 이전 기준선**으로 사용했다.
  최적 청킹으로 선정한 것이 아니다.
- 실제 Gemini Supervisor 위임 → 전문 Agent 도구 선택 → CSV 계산 →
  확인 대기 제안 흐름을 합성 요청으로 확인했다. 실제 사용자 섭취는 저장하지 않았다.
- 원문 대조 RAG 골드 40문항/20개 사실 그룹/4개 출처와 judge 보정
  20문항을 작성했다. Codex의 원문 대조이며 임상 정책 승인 또는 최종
  사람 검토 120문항 완료를 의미하지 않는다. Judge 보정은 20/20 일치했다.
- PyPDF/PDFPlumber/Docling PDFium × page/parent-child/section의 9조합에
  20문항 BM25/Ragas 파일럿을 실행했다. 원본 실행 8조합 완료, 한 조합은
  `GoogleAPIError`로 실패했다. 별도 실행에서 해당 조합은 완료했지만
  실패 기록과 새 프롬프트 버전 결과를 하나의 실험으로 합치지 않는다.
  개별 채점 20개씩 유효 여부도 확인했다. 질문 절반의 답변 보류와
  context recall 약 0.45–0.55 때문에 높은 faithfulness만으로 승자를 정하지 않는다.
- 현재 인덱스의 Dense/Hybrid/Full 검색을 40문항으로 비교했다. 초기
  지정 정답 페이지 적중률은 0.75/0.70/0.275였다. 같은 주장을 다른 페이지에서
  찾은 경우는 이 단일 정답 페이지 지표에서 불리하므로 답변 정확도로
  해석하지 않는다. BM25/리랭커를 필수로 검사하고 번역 결과를 고정·보존하는
  엄격한 후속 실행을 추가했다. 순위 지표는 중복 제거된 **페이지** 기준이다.
  엄격한 재검증은 3방식 모두 40/40 완료했고, 페이지 적중률은
  Dense 0.75 / Hybrid 0.725 / Full 0.30이었다. 40개 번역과 실제 문맥을
  보존했다. LangSmith에 공개 골드 데이터셋과 3개 측정 결과 replay 실험을
  연결했다. replay 실행 시간은 API 지연이 아니며 실제 지연은 outputs.seconds다.
- Docker OCR(Tesseract 5.3.0, kor/eng)에서 공개 PDF 두 페이지를 150dpi
  이미지로 변환해 처리했다. 숫자/권고 용어 smoke는 통과했으나 한글 단위
  오인식이 있다. 실제 스캔 CER/표 셀 평가와 Docling OCR 통합 완료는 아니다.

발생 오류와 처리:

1. 메인 환경 Ragas 0.2.15와 새 langchain-community의 VertexAI import 충돌:
   community 0.4.1을 별도 artifact runtime에 설치했다. 서비스 환경은 유지했다.
2. Windows Tesseract 설치가 `0x800704c7`로 취소됨: 호스트 설치를 반복하지
   않고 Docker에서 OCR을 검증했다. 자동 승인 검토 거절로 보고하지 않는다.
3. Ragas 한 조합 Google API 오류: 원인 HTTP 상태는 원본에서 확보하지 못했다.
   실패를 보존하고 별도 실행이 완료됐다. 이벤트 루프를 확정 원인으로 단정하지 않는다.
4. Docling 기본 네이티브 backend의 access violation: 과거 오류를 보존하고
   명시적 PDFium 대안으로 비교했다. 성공한 문서만 조용히 섞지 않았다.
5. 구판 이름이 남은 지역 프롬프트와 PDF 0-based 인용: 최신 적용 가능 판본
   안내 및 1-based 인용으로 수정하고 새 namespace를 검증해 활성화했다.

**아직 전체 계획 완료가 아니다.** 최종 120문항(Agent 포함) 검토·통합 평가,
동일 조건의 임베딩 차원/검색 레시피 비교, 검토 주장 레지스트리와 근거 충돌의
실제 전략 쓰기 차단, 실제 진행/토큰 스트리밍·재연결/재시작 재생,
Weekly Deep Agent·MCP·API/worker 컨테이너·kind 복구 데모가 남아 있다.
기능·평가 검증 후 Cue 참고 UI를 적용하는 기존 순서를 유지한다.

이번 최종 검증: 백엔드 145 passed / 1 skipped / 3 deprecation warnings,
프론트 승인 카드·SSE 프레임 테스트 6 passed, 프론트 production build 통과.
Python compileall / pip check / git diff --check 통과. 선택적 ingestion 테스트의
건너뜀과 실제 스캔/Pod 재시작/전체 Agent 골드 평가 미완료는 성공으로 세지 않는다.


## Jev 연결 및 호출 검증 — 2026-10-09

- 사용자 입력 TypeSafe 키로 jev-1.13.0 실제 호출 성공. 키는 산출물에 저장하지 않았다.
- 공개 합성 요청 3종 × 선택지 순서 회전 3회 = 9회: 예상 선택 9/9, API 오류/fallback 0건, 호출 지연 0.48~0.69초.
- 결과: backend/artifacts/jev-capability/report.json. 이는 연결·순서 안정성 smoke test이며 Gemini 대비 성능 개선이나 운영 채택의 근거는 아니다.
- Jev 호출을 공통 모델 예산에 포함하고 전체 요청 deadline, 응답 컨테이너 검증, 첫 결정 이후 도구 바인딩 복원 회귀 오류를 수정했다.
- Supervisor 또는 전문 Agent 도구 선택에 선택적으로 주입 가능하며 기본 운영 경로는 변경하지 않았다. RAG Jev 리랭킹 비교는 아직 남아 있다.
- 대체 근거 페이지를 인정하는 평가 함수를 추가했다. 실제 골드의 대체 페이지 검토는 별도 진행해야 한다.
- 전체 백엔드 회귀: 157 passed, 1 skipped, 3 기존 deprecation warnings. 연결 테스트와 성능 평가를 구분한다.
- 다음 순서 유지: 골드 120/근거 검토 → 검색 원인 분석 및 동일 조건 최적화 → Jev 위치별 Gemini 비교 → 통합 평가 → 스트리밍/Deep Agent/MCP/kind → UI.

## 성능 원인 분석 및 제한된 리랭킹 실험 — 2026-10-09

- 개발 골드 40개에 검토한 대체 근거를 반영하고, 미사용 최종 평가용 사실 문항 20개를 추가했다. RAG 사실 60개이며 전체 Agent/안전 포함 120개 완성은 아니다.
- RRF 페이지 타입/내용 식별 결함과 4번째 문맥 누락을 수정했다. 동일 원시 순위에서 페이지 적중률 75→80%, 구절 적중률 80→87.5%; MRR은 0.617→0.560으로 낮아졌다.
- 동일 최초 후보의 없음/MiniLM/MultiBERT/Jev 4방식을 비교했다. Jev 800회 실제 호출 성공, 평균 리랭킹 7.09초. 구절 적중률 80→92.5%, Ragas context recall 0.713→0.842, faithfulness 0.963→0.969지만 그룹 신뢰구간은 0을 포함한다.
- 수정된 RRF 후보의 MiniLM 및 400자 child 진단은 리랭킹 없음보다 낮아 추가 탐색을 중단했다. Jev 운영 적용이나 최종 레시피 선정은 하지 않았다.
- Ragas API 504/timeout과 초기 실패 산출물을 보존하고 사례별 점수 저장으로 각 구성 40/40 평가를 확보했다. LangSmith 색인 지연을 재조회로 처리하고 오프라인 replay 4개×40 root runs를 확인했다.
- 공유 예산 부족 시 Jev 무호출 fallback, 후보/모델/코드 해시 캐시 보호, 독립 골드 provenance 검증을 추가했다. 읽기 전용 리뷰의 중요 지적을 수정하고 재확인했다.
- 최종 백엔드 168 passed / 1 skipped / 기존 warnings 3개. 프론트 변경은 없다.
- 상세 수치·한계·재현 진입점은 EVALUATION.md 10장. 다음 단계는 상위 파서/청킹 전체 비교 → 임베딩 차원 비교 → Agent/안전 골드 및 독립 평가. 추가 모델 탐색·새 VectorDB·GraphRAG는 범위 밖이다.

## 전체 파서·청킹 두 후보 비교 — 2026-10-10 (완료·기존 구성 유지)

- Ruling: 기존 BM25/Ragas 파일럿에서 Docling/page와 PDFPlumber/section을 선정했다. 첫 후보는 검색 점수 0.55로 가장 높았고, 두 번째는 0.50 동점 후보 중 짧은 문맥(평균 4188자), 표 구조 보존 및 Ragas faithfulness 0.973을 고려했다. 두 출처/20문항 파일럿만으로 최적이라고 주장하지 않는다. PDFPlumber/page도 동점이며 이번 두 후보 제한으로 제외한다.
- Ruling: 실험 벡터는 로컬 exact cosine 인덱스로 분리한다. 운영 Pinecone/BM25는 변경하지 않고 Gemini 3072차원·고정 번역·후보20/반환4/문맥6000을 사용한다. 측정 지연은 Pinecone 네트워크 지연을 포함하지 않는다.
- 배치 파싱의 원문 SHA·페이지 완전성·중복·파서 버전 검증을 추가했다. 최종 평가용 20문항은 사용하지 않는다.
- 리뷰에서 발견한 query/document 모델 캐시 확인 누락과 다중 페이지 section의 MRR 편향을 red→green 테스트로 수정했다. MRR은 이번 비교에서는 반환 문맥 항목 순위 기준이며 이전 페이지 단위 MRR과 직접 비교하지 않는다.
- Ruling: 메모리 여유(약 40GiB)를 확인해 파서 병렬도를 2→4로 변경했다. 이번 실행의 프로세스만 식별해 재시작했고 완료 배치는 보존했다. 초기 parse identity와 로그도 보존한다. 의존성은 변경하지 않았으며 재개 시 버전/원문/선택 페이지를 검증한다.
- 발생 오류: 한국어 출력 cp949 UnicodeEncodeError는 UTF-8로 해결. 리소스 확인용 psutil은 미설치여서 설치하지 않고 Windows 기본 메모리 조회를 사용했다. 서비스 장애나 API 오류로 세지 않는다.
- 실제 전체 실행에서 Docling 내부 120초 timeout 후 일부 페이지만 반환하는 것을 발견했다. `status=success` 및 실제 변환 페이지 완전성 검사로 차단했다. 이전 24페이지 파일럿의 10문서 canonical 페이지는 모두 완전함을 재확인했다.
- 24→8페이지 배치, 문서별 모델 재사용으로 제한된 복구를 시도했으나 KDRI에서 table thread 종료 실패/Output queue closed가 반복됐다. 산출물과 로그를 보존하고 Docling 전체 후보를 제외했다. 실패를 정상 완료 문서로 대체해 점수에 섞지 않는다.
- Ruling: 전체 처리가 가능한 PDFPlumber/page를 대체 후보로 추가하여 PDFPlumber/section과 비교한다. 파일럿 검색 0.50 동점 후보이고 추가 파서 설치/모델 탐색 없이 동일 전체 parse를 재사용할 수 있다. 이는 파서 2종의 성공적인 전체 비교가 아니라 안정성으로 Docling을 제외한 뒤 두 청킹을 비교하는 것이다.
- 표 8의 대상자 수 `9`가 Docling 연령 열로 이동하는 사례를 원본 렌더링과 대조했다. 작은 구조 점검 골드는 6개 수치/단위/조건 앵커와 5개 표 행이며 전체 표 정확도로 일반화하지 않는다. 숫자 `9`/`19`, `+20`/`+200`을 혼동하지 않도록 숫자 경계 검사도 추가했다.
- 재시작 캐시에서 과거 partial artifact가 재사용되지 않도록 실제 canonical 페이지 검사를 추가했다. 현재 파서/평가 관련 13개 focused 테스트 통과. 최종 전체 회귀와 실험 결과는 완료 후 기록한다.
- PDFPlumber 기본 표 추출이 가장자리 셀을 놓치는데 표 bbox의 원문까지 제거하던 문제를 발견했다. 원문 좌표로 빈 셀만 복구하고, 부호·수치·출현 횟수가 보존된 경우에만 중복 원문을 제거한다. 복구가 불완전하면 원문을 유지하고 해당 파생 표는 검색 청크에서 제외한다. PDF 밖으로 벗어난 bbox는 실제 페이지 경계로 제한한다.
- 전체 PDFPlumber 실행 v4는 10개/1,953페이지를 처리했다. page 1,932청크, section 3,729청크이며 21페이지는 색인 가능한 텍스트가 없다. OCR/그림 내용 해석을 완료했다고 주장하지 않는다.
- 원문 대조 구조 점검: 수치·조건 앵커 6/6, 표 행 5/5, 개발 골드 사실 그룹 핵심 구절 20/20 보존. 전체 표 정확도나 임상 정책 승인 결과가 아니다.
- 기존 운영 pypdf/recursive 4,139벡터를 캐시에서 API 호출 0회로 가져와 비교 control로 추가했다. 신규 후보 확대가 아니라 기존 구성 대비 개선 여부 확인 목적이다.
- Gemini 임베딩 중 503 UNAVAILABLE가 발생했다. 첫 실패 로그를 보존하고 동일 설정·성공 캐시를 이용해 제한 재시도한다. 벡터 행 수로 실제 API 호출 수/비용을 추정하지 않는다.
- 전체 회귀: 183 passed / 1 skipped / 기존 deprecation warnings 3개. 구문 검사 및 git diff --check 통과. 운영 인덱스·검색 기본값은 변경하지 않았다.
- 완료: 임베딩 stage 재개 1회로 503을 복구했고 두 후보 및 기준선의 Dense/Hybrid 6구성을 평가했다. 기존 recursive/Hybrid 페이지 80%·구절 75%, PDFPlumber section/Hybrid 65%·60%, page/Hybrid 60%·57.5%다. page 문맥은 33/40 요청에서 잘렸고 section/recursive는 0/40이다. 이번 프로토콜의 지표를 과거 87.5%와 직접 증감 비교하지 않는다.
- Ruling: 기존 PyPDF/recursive를 유지하고 Hybrid를 다음 차원 비교의 잠정 기준으로 사용한다. 운영 설정은 유지한다. 신규 후보가 좋아졌다고 포장하지 않고 Docling 안정성 실패 및 표 보존 수정·검색 회귀를 EVALUATION.md 11장과 full_recipe_summary_v1.json에 기록했다.
- 사실 그룹 20개 기준 paired bootstrap 및 한·영/문맥 잘림 오류 목록을 저장했다. 개발 평가일 뿐 최종 독립 평가·Ragas 답변 품질·전체 서비스 안전 완료가 아니다. 추가 파서 탐색은 종료하고 원래 5단계의 임베딩 차원 비교로 진행한다.

## Docling 복구 재검증 — 2026-10-10 (완료·운영 유지)

- Ruling: 사용자가 시간·페이지 격리·스레드·표 처리·backend/환경을 모두 시도한 뒤에만 포기하도록 요청했다. 기존 안정성 탈락을 잠정으로 되돌리고 실패 로그 → 원인 가설 → 공식 자료 → 한 가지 설정 변경 → 결과를 매번 기록한다. 운영 인덱스는 유지한다.
- 기존 로그: `full-recipes-v2/persistent-jobs/docling-KDRI_2025_vol1.log`에서 120초 timeout 이후 table thread 15초 종료 실패와 PDFium page NoneType 오류가 이어졌다. 종료 후 오류와 최초 느린 단계를 구분하기 위해 stage profiling을 켠 격리 worker를 추가했다.
- 복구 설정을 immutable DoclingConfig로 분리해 timeout/CPU threads/batch/queue/table mode/backend의 산출물 identity를 보존한다. 입력·캐시 격리 테스트 red 2건 → green 9건 관측. timeout은 1..1800초의 유한값으로 제한한다.
- 진단 준비 오류 1: PowerShell 중첩 페이지 배열이 펼쳐져 `int not subscriptable`. Microsoft 배열 문서의 unary comma로 수정하고 별도 로그를 보존했다. https://learn.microsoft.com/powershell/module/microsoft.powershell.core/about/about_arrays
- 진단 준비 오류 2: HF_HUB_OFFLINE 상태에서 기본 캐시에 모델이 없어 LocalEntryNotFoundError. 기존 `artifacts/model-cache`를 HF_HOME으로 명시해 해결을 시도한다. https://huggingface.co/docs/huggingface_hub/en/guides/manage-cache
- 공식 설정 근거: https://docling-project.github.io/docling/reference/pipeline_options/ . 현재 runtime은 Docling 2.135.0, torch 2.14.1+cpu, CUDA 사용 불가, 논리 CPU 16개다. GPU 작업을 실행했다고 주장하지 않는다.
- 원인 실험: vol1 p9 단독은 표 단계 9.282초/변환 15.15초로 성공. 동일 p9–16 묶음은 table p10–13 처리 107.676초 중 120초 제한에 도달해 partial_success가 났다. p10 표 off는 성공했지만 구조 품질 결과로 인정하지 않는다. 같은 설정에서 제한만 300초로 변경하니 8/8페이지가 변환 181.32초(전체 worker 195.48초)에 완료됐다. 이 구간의 최초 원인은 표를 포함한 배치 전체 소요 시간에 비해 짧은 timeout이었다. 기존 종료 후 NoneType 오류가 최초 원인이라고 단정하지 않는다.
- 관련 공식 이슈를 검색해 기록: https://github.com/docling-project/docling/issues/4255 (ACCURATE 장기 decode/행 누락 사례), https://github.com/docling-project/docling-ibm-models/issues/161 (table decode overhead). 동일 원인이라고 가정하지 않고 FAST·단일 스레드·backend를 직접 비교한다. 실패 시 process를 폐기해 timed-out thread를 재사용하지 않는다.
- 구조 오류 추가 확인: 원본 p10은 14열 표 두 개지만 PDFium/ACCURATE 결과는 49행·6열 표 하나이며 한 셀에 연령과 여러 영양소 값이 섞였다. 원본 `source-p10.png`와 canonical table JSON을 보존한다. 단순 Markdown 표시 손실이 아니라 JSON grid도 6열이다. backend의 word cells 차이를 근거로 native backend를 비교한다. https://github.com/docling-project/docling/blob/main/docling/backend/pypdfium2_backend.py 와 https://arxiv.org/abs/2408.09869
- 1스레드는 표 단계 p9 20.505초(4스레드 12.457초), p10–13 220.261초(4스레드 108.402초)로 오히려 느렸고 300초 제한에 실패했다. 종료 로그와 partial_success를 보존하고 4스레드로 복귀한다. 공식 accelerator 설정을 참고했다.
- native backend/ACCURATE의 p10·64·65 변환은 완료됐다(전체 worker 69.38초). p10 grid가 14열로 복구됐으며 기존 원문 수치 앵커 6/6, 표 행 5/5 통과했다. 일부 p10 행 병합이 남으므로 전체 표 정확도라고 주장하지 않는다. FAST 모드와 대조한다.
- 사용자 GPU 요청으로 실제 하드웨어를 확인했다. RTX 3070 Laptop 8GB, driver 576.02, 약 6.7GB free. CPU torch가 CUDA를 지원하지 않았던 것이며 GPU 자체가 없는 것은 아니었다. 공식 cu128 torch 2.11.0/torchvision 0.26.0을 별도 `artifacts/gpu-runtime`에 설치한다. 기존 venv/CPU runtime 및 드라이버는 변경하지 않는다. https://pytorch.org/get-started/previous-versions/ , https://github.com/docling-project/docling/blob/main/docs/getting_started/rtx.md
- GPU 설치 최초 실패: C 임시 저장 공간 부족(Errno 28). D 여유 약 579GB 확인 후 설치 child process의 TEMP/TMP/TMPDIR만 workspace D 임시 디렉터리로 제한해 재시도한다. 삭제/전역 환경 변경은 하지 않았다. https://docs.python.org/3/library/tempfile.html , https://pip.pypa.io/en/stable/topics/caching/
- FAST/native는 대표 페이지 처리 46.16초로 빨랐으나 표 행 4/5만 보존했고 아동 행(+20)을 놓쳤다. ACCURATE는 5/5여서 FAST를 채택하지 않는다. 누락 셀/모드 교환 사례를 공식 이슈 https://github.com/docling-project/docling/issues/3921 와 대조했다. 같은 버그라고 단정하지 않는다.
- D 임시 디렉터리 재시도로 CUDA runtime 설치 성공. CUDA 실제 행렬 연산과 RTX 3070 인식을 확인했다. 같은 torch 2.11.0+cu128/native/ACCURATE/4threads/300초/대표 p10·64·65를 순차 실행해 CPU 전체 worker 73.665초, GPU 34.847초(약 2.11배)를 관측했다. 단일 측정이며 전체 코퍼스 처리량이나 모든 환경으로 일반화하지 않는다. 두 실행 모두 수치 앵커 6/6·표 행 5/5; GPU도 p10 일부 행 병합은 남는다.
- GPU 전체 확대는 문서당 worker 1개, 4페이지 배치, 배치당 300초로 제한한다. 각 배치의 실제 canonical 페이지를 검증하며 재개 때도 marker만 신뢰하지 않는다. 원문 10개/1,953페이지, 운영 인덱스 변경 없음. `backend/artifacts/docling-recovery-v1/full-gpu/`에 설정·버전·로그·결과를 보존한다.
- 점검 helper 첫 실행은 저장된 상대 경로를 repo root에서 읽어 FileNotFoundError가 났다. backend cwd에서 재실행해 성공했다. Docling 변환 실패가 아닌 audit 진입 경로 오류로 분리한다.
- 전체 GPU 초기 helper에서 `range`의 step=4 누락으로 [1..4], [2..5]처럼 범위가 겹치는 것을 조기 발견했다. Python 공식 range 설명을 확인하고 step=4와 실행 전 validate_batches를 추가했다. 해당 실험 PID만 종료했으며 초기 로그는 full-gpu에 남기고 정상 실험은 full-gpu-v2로 분리한다. https://docs.python.org/3/library/stdtypes.html#range
- Fresh-context review의 P2 두 건을 수정했다. 손상 marker/실제 페이지 누락 cache는 miss로 취급하고 재처리한다(새 테스트 ImportError red→11 focused green). dump는 같은 디렉터리 임시 파일 후 Path.replace로 교체한다. 전체 집계는 현재 job identity만 인정한다. https://docs.python.org/3/library/pathlib.html#pathlib.Path.replace
- 최종 코드 회귀: 187 passed, 1 skipped, 기존 warnings 3개; compileall과 diff --check 통과. 최초 sandbox 전체 테스트는 CSV 테스트에서 정체되어 해당 PID만 종료했고 동일 테스트 elevated 단독 1/1 및 전체 회귀 187/187이 통과했다. 서비스 오류나 Docling 품질 실패로 합산하지 않는다.
- GPU 전체 1권 393/393페이지 완료(559.834초), 실제 페이지 누락/중복 없음; 앵커 6/6·표 행 5/5 보존. 2권은 360페이지 이후 native process exit 3221226356(0xC0000374)로 종료됐다. 표/assemble 로그는 완료됐으며 timeout으로 기록하지 않는다. 특정 DLL/경쟁 상태는 아직 확정할 수 없다.
- 종료 코드를 검색하고 공식 프로젝트 이슈 https://github.com/docling-project/docling/issues/4147 , https://github.com/docling-project/docling/issues/2559 를 대조했다(다른 플랫폼/버전이므로 동일 결함 단정 금지). 실패한 p361–364를 새 프로세스·같은 설정으로 재실행해 parse/export 20.469초, worker 24.843초에 성공했다. 누적 native 자원/비결정적 오류 가설을 지지하지만 원인을 입증하지 않는다.
- Ruling: 완료 배치를 재사용하면서 새 프로세스로 재개한다. 이미 진단한 native exit에만 문서당 최대 3회 재시도를 적용하고 새 오류는 중단해 별도 로그/검색 진단한다. 재개 시 기존 로그/설정/실행 시간은 history UUID 디렉터리에 보존한다. faulthandler 활성화와 90초 watchdog으로 추가 crash/hang 위치를 기록한다. https://docs.python.org/3/library/faulthandler.html
- 2권은 native heap/access violation 3회 이후 재개하여 569/569페이지를 완료했다. 3권은 access violation 3회 이후 520/535페이지에서 한도에 도달했다. 진행 업데이트 중 완료 marker 증가만 보고 3권 오류가 없다고 말했던 내용을 상위 실행 로그 확인 직후 정정했다. 실제 오류는 모든 history/execution.json 기준으로 집계한다.
- 3권 마지막 15페이지에 `parser_threads=1`을 추가해 native parser pool과 모델 계산 스레드(4)를 분리했다. 공식 backend_options.py를 확인했다. 테스트 TypeError red→12 focused green. 8페이지 완료 후 access violation 재발(187.214초): 내부 파서 병렬도 감소가 근본 해결이라고 주장하지 않는다. 실패 스택과 https://github.com/docling-project/docling-ibm-models/issues/170 를 대조했다(동일 버그 단정 금지).
- 공식 native crash 이슈 #4147의 PDFium 우회 후보를 적용했다. 마지막 미완료 7페이지는 PDFium/GPU/ACCURATE에서 worker 76.417초에 성공했다. Ruling: 3권의 성공 배치들은 native 기본/단일 parser thread/PDFium의 복구 산출물로 명시하며 나머지 7종은 PDFium GPU로 처리한다. 전체 파싱 복구 완료를 단일 설정의 순수 파서 성능 비교로 포장하지 않는다. 운영 index는 유지한다.
- 추가 리뷰 P2 수정: collector도 artifact manifest의 원문 SHA·code SHA·Docling 버전·backend·선택 페이지·config를 직접 대조한다. 다른 원문 artifact라도 페이지가 같으면 통과하던 테스트 assertion red→green. 기타 runtime 버전은 job/log에 기록되며 기존 artifact가 모든 dependency 버전을 직접 보증한다고 주장하지 않는다. supplemental 실패 이력도 전체 시도 시간에 포함한다.
- 최종 복구 검증 완료: 10문서/1,953 실제 페이지, Docling page 산출물 1,925청크. 앵커 6/6·표 행 5/5·개발 사실 그룹 구절 20/20 보존. 신규 임베딩/운영 색인은 실행하지 않았다. canonical 페이지 및 manifest 원문/code/parser/backend/config를 직접 검증했다.
- GPU 전체 확대/보충 실행에서 실제 native 종료 8회(2권3·3권4·WHO 탄수화물1), 실패 포함 시도 시간 합계 2,843.081초. 설치·대기·별도 p361 진단은 이 합계에 포함하지 않는다. 설정/backend가 섞인 복구이며 uniform_config=false; 3권 primary report의 failed를 덮어쓰지 않는다. PDFium에서도 native access violation이 발생해 특정 backend 하나의 결함이라고 확정하지 않는다. native/C 계층 상세 root cause는 미확정이고 process 격리·검증된 checkpoint·제한 재시도로 우회한 상태다.
- Ruling: 사용자 요청의 Docling 합리적 복구 시도는 완료하고 더 이상 무작정 재시도/의존성 교체를 확대하지 않는다. 운영 PyPDF/recursive 유지. 다음은 동일 페이지·동일 청킹의 파서 효과 분리 후 임베딩 768/1536/3072 비교이며, 전체 복구 성공을 검색·답변 정확도 향상으로 주장하지 않는다.
- 최종 전체 회귀 188 passed/1 skipped/기존 warnings3. 추가 artifact 출처 검사까지 포함해 재실행했다. compileall 통과. diff --check에서 EVALUATION.md EOF 빈 줄을 발견해 제거한 뒤 exit0을 확인했다. EVALUATION.md12장 및 docling_recovery_summary_v1.json에 성과/실패/한계를 기록했다.

### Docling 종료 원인 정정 — 2026-10-10

8회 종료를 모두 Docling 자체 오류로 해석하면 안 된다. Windows 오류 기록과 공식 Python 3.13.3 PDB로 반복된 Python 종료 위치가 `dump_frame / traceback.c:907`임을 확인했다. Docling 없이 PyTorch+주기적 스택 출력만으로 ON 3/3 종료, OFF 3/3 성공을 재현해 복구 runner의 반복 덤프를 제거했다. 별도로 모델/GPU/진단 덤프 없는 PDF 파싱 실험에서도 `docling-parse` C++ 확장(`pdf_parsers.cp313-win_amd64.pyd + 0x7e5a97`)의 접근 오류를 확인했다. 두 경로를 구분하며, native 내부의 최초 메모리 오염 함수는 아직 미확정이다. 상세 근거·대조 결과·남은 한계는 EVALUATION.md 13장 및 artifacts의 원본 로그에 기록했다. 운영 색인은 유지했다.
### 동일 페이지 파서·청킹 재검증 — 2026-10-10

- 진단 watchdog 제거 후 고정 native/GPU 설정 Docling 10/10 문서의 선정 페이지 성공. 3개 파서 × 4개 청킹, 26페이지·40개 개발 질문·문맥 6k/12k 비교 완료. 전체 문서 검색/답변 평가는 아니다.
- 숫자 범위 dash 차이를 구절 누락으로 판정한 평가 오류를 수정했다. 파서 모두 수치 앵커 6/6·구절 20/20, 구조화 표 행은 PyPDF 0/5·PDFPlumber/Docling 5/5. Docling의 장기 native 접근 오류 근본 해결은 아직 주장하지 않는다.
- PyPDF/parent-child 개발 구절 적중 75%, MRR 0.571. 독립 평가 없이 운영 전환하지 않는다. 운영 PyPDF/recursive 유지, Docling은 실험 후보 복귀. 상세 12조합 결과·해석은 EVALUATION.md 14장과 controlled_parser_summary_v1.json.
- 실패 캐시·donor dependency 검증, 비연속 페이지 병합 방지, 불완전 행렬 실패 종료를 회귀 검증했다. 백엔드 196 passed/1 skipped/기존 warnings3. 정적 재리뷰 P1/P2 없음.
- D process temp/model/pip cache 적용, 이번 작업 crash dump 9개 약5GB를 D로 이동(C 약5.7GB 여유). 테스트 임시 경로 생성 오류는 D basetemp 부모 생성 후 해결. raw dump 공개 금지.
- 다음 순서: 전체 코퍼스 후보 확인·768/1536/3072 임베딩 → 리랭커/Jev → Agent/안전/근거 충돌 → 독립 Ragas/LangSmith → 스트리밍/Deep Agent/MCP/배포 → 기능 검증 후 Cue UI.

### 전체 공정 비교 SSH 사전 점검 — 2026-10-10

- 사용자 지정 SSH 경로를 우선한다. 현재 사용자 SSH config의 A5000-4 대상으로 BatchMode/ConnectTimeout=10 읽기 전용 pwd 연결을 시도했다. sandbox 밖 재확인에서도 TCP connection timed out이므로 키 인증 단계에 도달하지 않았다. 인증키가 틀렸다고 단정하지 않는다.
- 공식 OpenSSH ssh_config/ssh 문서를 확인했다. IdentityFile 또는 ssh-agent가 키 선택을 담당하지만 현재 TCP 연결 실패를 키 변경으로 해결할 수 있다고 가정하지 않는다. 사용자에게 사용할 host alias/key path 및 서버/VPN 상태 확인을 요청했다. 개인키 내용은 요구하지 않는다. https://man.openbsd.org/ssh_config
- 독립 준비 완료: 원문 10개/1,953페이지 및 SHA 확인, D의 artifacts/full-controlled-preflight-v1/all-pages.json과 preflight.json에 전체 페이지·고정 비교 조건을 저장했다. 원격실행/임베딩 호출은 시작하지 않았다. .env/개인키/crash dump 원격 업로드 금지.
- Ruling: SSH 요청을 로컬 GPU 실행으로 임의 대체하지 않는다. 원격 연결 확인 후 OS/GPU/runtime/기존 작업 디렉터리를 조사하고 환경이 확인된 다음 유한 배치·같은 설정의 전체 비교를 실행한다. 이전 혼합 설정 복구 결과를 새 uniform 비교로 재사용하지 않는다.

### 전체 공정 비교 로컬 재개 — 2026-10-10

- 사용자 정정: SSH는 다른 프로젝트의 요청이었다. 원격 실행·업로드는 수행하지 않았고, 본 작업은 로컬 RTX3070/D temp로 재개한다. 이전 SSH pending 요구는 철회된다.
- 승인된 계획: 전체 동일 원문 10개/1,953페이지, 3파서×4청킹, 동일 개발 40문항, 후보20/반환4/문맥6k·12k. 파싱 결과 재사용으로 파서/청킹 효과를 분리한 뒤 선정 후보에서 임베딩768/1536/3072 비교.
- 균일 Docling 설정: native backend/parser pool1/model threads4/CUDA/ACCURATE/OCR off, 배치24페이지, 배치timeout300/문서wall1800. 반복 faulthandler watchdog 없음. 실패 시 자동 설정 변경·fallback 하지 않고 로그 진단 후에만 명시 재개한다.
- 혼합 이전 복구 산출물 재사용 금지. 새 run_uniform_full_comparison runner는 페이지 누락·중복과 다른 identity를 거절하며 파싱·평가 identity를 분리한다. 테스트 RED import failure → GREEN3.

- 추가 진단/수정: 실험 준비 중 상대 경로를 backend 기준으로 중복 지정해 테스트가 다른 폴더에 생성됐다. 이번 파일만 절대 경로로 이동/병합해 정상 위치에서 RED/GREEN을 확인했다. Windows의 backslash가 code identity 키에 들어가 조회 KeyError도 발생했다. Python pathlib 공식 as_posix 문서를 확인하고 차원 runner에서 기존 키를 slash로 정규화해 읽는다. https://docs.python.org/3/library/pathlib.html
- API 사전 점검: 공개·합성 문서/질의 2개×3차원 호출6개 성공, API768/1536과 3072 prefix 정규화 cosine1.0(최소0.99999988). 공식 Embedding2 MRL 명세에 따라 기본 벡터 재사용·축소를 검증했다. 이는 별도 임베딩 모델3종 비교가 아니라 동일 모델 차원 ablation이다. https://ai.google.dev/gemini-api/docs/embeddings
- 원문 표 경고: MatchingPostProcessor가 예측 row/column band에 속하지 않는 pdf cell을 dropped 경고로 보고했다. 설치 소스 matching_post_processor.py:1228–1236 및 공식 이슈3921/4255를 대조했다. 단순 Markdown 표시 문제가 아닌 모델/후처리의 잠재 셀 누락이다. 비교 중 설정을 섞지 않고 경고·canonical JSON을 보존해 한계로 기록한다. https://github.com/docling-project/docling/issues/3921
- 리뷰 P2: 완료 marker에 artifact가 붙기 전에 저장되던 창을 수정(불완전 completed receipt 거절), 임베딩 runner가 과거 혼합 backend 결과를 받아들이던 gate를 전체3×4/10문서/page/config/버전/영수증 검증으로 강화했다. 회귀 RED→GREEN9. 실행 중 v1 runner는 이미 로드된 원본으로 계속되며 원래 source snapshot/hash를 보존했다. 후속 고친 runner의 hash로 v1 실행을 포장하지 않는다.
- 독립20문항/10사실그룹은 개발20그룹과 disjoint 확인 후 번역만 미리 고정했다. 아직 retrieval/answer 평가에 사용하지 않았다.
- 독립 평가 준비에서 개발셋 전용 validate_gold가 heldout을 거절하는 경계를 발견했다. 차원 runner에 명시적 --split과 검토/중복 검증을 추가했다. RED ImportError → GREEN5. 기존 개발 평가 함수의 봉인은 유지한다.
- 새 진단: vol3 배치385–408 로그에 접근 오류2회, Windows Event1000/PID49072 및 dump1개 확인. 문서 worker는 이후 처리/exit0, canonical535페이지 확인이므로 native 종료0과 접근 오류0을 혼동하지 않는다. 공식 Python3.13.3 PDB로 terminal address python313.dll+0x2b0b98=dump_frame/traceback.c:907, read0x71 확인. raw stack에는 faulthandler_exc_handler와 pdf_parsers 주소 후보가 있으나 unwind된 causal stack이 아니므로 최초 native 오염 원인을 단정하지 않는다. CPython faulthandler Windows first-chance 처리 소스/공식 이슈74311·75882를 대조했으며 해당24페이지를 동일 설정으로 별도 재검증한다. https://github.com/python/cpython/issues/74311 https://github.com/python/cpython/issues/75882
- 전체 완료: 3파서 각각10문서/1,953페이지, 30 receipts 검증, 3×4×2문맥 BM25 비교 완료. 파싱시간PyPDF50.4초/PDFPlumber147.8초/Docling2352.7초, 표관계0/5·5/5·5/5. 범위한계는 공개요약/EVALUATION15장에 기록했다.
- native 재검증: vol3 해당24페이지 동일 설정 재실행exit0/fatal메시지0, 원래174블록과 페이지·종류·텍스트 multiset완전일치. 최초메모리오염함수/근본수정은 미확정. 원본dump1개706,654,630bytes를 정확한 경로 확인 후 D private archive로 이동했다. 표셀누락경고28개를 별도 감사결과에 남겼다.
- 차원실험 실패1: sandbox getaddrinfo11001/ConnectError, HTTPX공식 오류분류 확인 후 동일identity의 네트워크 승인 실행으로 성공. 최초실패로그 보존. API키 원문/사용자 건강정보 전송·노출 없음.
- 개발선정(PyPDFrecursive768) 고정 후 독립20문항 평가까지 완료. 개발구절70%vs3072의67.5%, 독립70%vs75%로5%p저하. 저장75%감소/로컬검색시간개선만으로 운영전환하지 않는다. 운영3072유지,1536후속후보. Ragas/실서비스지연으로 오해하지 않도록 scope 명시.
- 최종검증206passed/1skipped/기존warnings3, 이번4개파일py_compile통과. 원본소스snapshot과공개요약2개/재현명령/EVALUATION15장완료. SSH/운영env/DB/Pinecone 변경없음.
### Docling fatal 진단 경로 완화 재검증 — 2026-10-10

사용자 요청으로 dump_frame 오류의 진단 경로를 추가 조사했다. 공식 CPython faulthandler 문서와 이슈116008/128400은 스레드 traceback 출력의 위험 사례를 설명하지만 현재 GIL-enabled Windows 사례의 동일 원인을 증명하지 않는다. recovery worker의 fatal traceback을 all_threads=False로 제한했다(전체 thread를 순회하지 않고 현재 thread 정보만 유지, 부모timeout 유지). 해당24페이지를 서로 다른 새 프로세스에서2회 처리해 exit0/접근오류메시지0/174블록이 원래 결과와 완전일치했다. 관련 회귀1passed/기존warning1, py_compile/diff-check통과. 기존 all_threads=True 짧은 재실행도 성공했으므로 인과적 성능 개선이나 최초 native 오류의 근본 해결을 주장하지 않는다. 장시간 누적 상태 재현/최초 native 예외의 native debugger stack은 아직 미확보다. 비교v1결과는 변경하지 않았다. 원본검증 artifacts/uniform-fatal-current-thread-v1/verified-summary.json.
### 검색 방식·Ragas·Jev 단계 시작 — 2026-10-10

계획 실행: 고정 Gemini3072와 전체원문10개/1953페이지, 두 후보에서 Dense/BM25/Hybrid 비교 → Hybrid답변/Ragas → 고정 검색구성에서 none/Jev 비교. 운영색인/env/DB 변경없음. Ruling: 6조합 검색은 전부 측정하고 유료 답변 평가는 두 후보 Hybrid와 이후Jev에 제한한다. 페이지·문자 literal 적중이 답변품질을 대변한다고 주장하지 않는다.
TDD 후보통합 RED2→GREEN2. 리뷰 P2의 vector identity 대조 누락을 현재캐시 일치확인 후 fail-closed 검사로 수정, RED→GREEN3. 수정코드의 새 v2출력에서 전체비교 재실행. 원질문/번역이 각검색채널을 거친 뒤 query별 및 최종 RRF60, 후보20/반환4/실제6k전달문맥을 고정. local exact cosine이며 Pinecone/전체요청지연 아님.
현재 모델 생성gemini-3.8-flash, 별도Ragasjudge gemini-3.1-pro-preview, ragas0.2.15, Jevjev-1.13.0. 키는존재여부만확인. LangSmithtrace는공개근거·평가질문만포함. 답변생성은 사례별캐시로 중단시성공사례를보존한다.
추가검증: frozen Jev candidate의 bundle SHA/ID/text/metadata 일치를 강제하는 parity gate와 회귀1개를 추가했다. 기존 baseline과 다른 bundle로 재생하는 오류를 사전에 차단했다. 백엔드210passed/1skipped/기존warnings3(4.92초), 두 runner py_compile통과.
실행: 6검색구성/Hybrid답변80개/Ragas160metric 모두완료실패0. Jev는PyPDFHybrid동일20후보40문항800호출/fallback0, 구절75→80%,MRR0.5604→0.650,평균7.55초추가/p95 8.04초. 구절차이의20사실그룹 bootstrap95% CI -5~15%p로 확실한개선을주장하지않는다. Jev답변40개완료,동일judge채점진행.
보조작업실패: 요약script read_text 기본CP949로 UTF8JSON UnicodeDecodeError 발생. Python공식 pathlib/PEP597 확인 후 UTF8명시,재실행성공. LangSmith검증조회 limit500은HTTP400 'Limit exceeds maximum allowed value of 100',공식query명세/응답을확인해100으로수정,조회성공. 조회100건(진행중judge80/Jev20)오류0이며전체trace수라고주장하지않는다. 공식자료 https://docs.python.org/3.13/library/pathlib.html https://peps.python.org/pep-0597/ https://reference.langchain.com/python/langsmith/_openapi_client/resources/traces/TracesResource/query
최종완료: Jev40답변/Ragas80metric완료(실패0/채점불가0),faithfulness0.96875/context_recall0.8125/보류2건. 전체120답변/240metric완료. PyPDFHybridnone0.996875/0.775/보류4,DoclingHybrid0.964286/0.600/보류11. Jev는추가7.55초/800호출,구절CI -5~15%p로채택기준미확보: 운영비활성유지. 파서3072운영유지,Hybrid독립검증우선후보. 한 번개발실험을3회반복/최종평가처럼기록하지않는다. 공개요약/EVALUATION16장 및 원본hash/재현command완료. 다음Agent골드/Supervisor·tool결정분리실험,이후독립최종평가/streaming·배포/UI.
보조rg검색에서Windows glob을경로로전달해os123이발생했다. rg의 -g필터로교정해검색성공. 프로그램/실험결과영향없음. 기존venv의real-location진단문구는실행exit0와실제pytest210통과를확인했다.

### Agent 의사결정·안전 평가 단계 — 2026-10-10
Ruling: 다음단계는30결정(Agent/도구),10멀티턴흐름,20결정적안전 gold로RAG60과전체120구성을완성한다. 개발44/heldout16,그룹분할; 한영번역쌍은그룹동일분할. 검토는합성행동계약/스키마이며임상승인아님. 결정실험3회반복 Gemini vs위치별Jev enforce, 실제흐름은동일합성IO로Gemini/SupervisorJev/ToolJev 1회pilot, 안전은malicious scripted model replay. 각결과scope를분리하고 운영전환하지않는다. 재시도는실패진단후최대1회, 원실패포함분모. 운영DB/Pinecone/env/SSH변경없음. 벤치마크와실서비스end-to-end지연을혼동하지않는다.
평가기TDD: 누락module RED→GREEN4. 여러유효다음행동을허용,잘못된인자/금지도구를실패로판정,실패를분모에남기고fallback노출,그룹누출/검토누락차단.
AgentEvals 공식 trajectory subset/superset를추가평가한다. agentevals0.0.9/openevals0.2.0를D의artifacts/agentevals-runtime에 --no-deps격리설치, Gemini전용원칙유지(메시지schema표현의OpenAI형식은API호출아님). 경로평가는인자ignore로순서유연성만검사하고인자/최종상태/HITL은자체결정적계약으로별도검사한다. https://github.com/langchain-ai/agentevals
개발gold수정2건: route_plan의Goal조회선행 및tool_delete의소유기록조회선행은유효경로임을원본toolcalls로확인,공식LangChain multi-agent/trajectory문서를대조해v2오라클에허용. 원본v1/점수/생성결과는보존하고v2재채점만진행,heldout동일유지.
평가기자체버그: empty_model_response로blocked인데finish기대label로goal_ok=True가될수있음을추가테스트로재현. 먼저테스트message필드누락KeyError를정정한뒤Assertion RED확인→runtime_status=='completed'를합쳐GREEN6. 기존실행은이미로드된v1이며run snapshot/hash를보존하고후속분석에서blocked상태검사를적용한다.
안전replay20/20통과:권한/identity/스키마/재시도피드백/동일오류2회/공유예산/시간/악성save/HITL경계(쓰기제공하지만허용policy로차단)검증. scripted모델이므로실제LLM의안전일반화나DB원자성검증으로주장하지않는다.
보조snapshot SHA검증실패: LF직렬화를Windows원본CRLF와비교한원인확인. 공식pathlib newline문서대조후CRLF원본bytes복원,기존dataset SHA와완전일치확인. 결정실험시작후safety oracle만추가된v1전체파일은별도snapshot보존,decision문항은불변. 보조importprobe의cwd기준경로로ModuleNotFound 발생해__file__기준절대경로로정정,공식AgentEvals probe성공. 로그조회backend/backend상대경로도backend기준artifacts로정정,실험영향없음.
리뷰P2 tool binding: CapturedModel이self.bound를변경해Jev finish시기존tool schemas가남던평가래퍼오류를테스트RED로재현했다. 공식BaseChatModel.bind_tools의별도Runnable 반환규칙대조후copy.copy binding/shared counter/collector로수정,GREEN7. v1두실험은새코드로재채점해도binding영향이복구되지않으므로채택근거에서제외하고v2전체재실행. 원실패/원자료보존.
리뷰추가P2: 양확인응답단어포함검사를명시적질문/요청검사로수정(단순'양을모른다'·영어Logging거절),Validatorwith_structured_output이usage수집을우회하던문제를include_raw=True로수정(rawusage/parsed/parsing_error저장). 공식SDK문서대조,RED2→GREEN9. 독립재리뷰에추가P1/P2없음. dataset/runner바이트snapshot및SHAgate추가. https://reference.langchain.com/python/langchain-google-genai/chat_models/ChatGoogleGenerativeAI/with_structured_output
Jev성공률을fallbackGemini성공으로오해하지않도록rawargmax선택정확도/enforced수/confidence구간오류를별도보고한다. .9threshold고정,운영전환/임계값튜닝없음. v2개발완료후같은고정설정으로미사용heldout을평가한다.

완료 결과: 고정결정 개발120행+미사용heldout60행, Gemini 계약전부통과. Jev 자체 Supervisor 개발30%/heldout60%, 전부fallback. 도구 자체선택100%이나미사용p95 Gemini4.82/Jev5.16초,호출15→30. 운영채택 gate 미충족, Gemini기본유지.
흐름개발v2는3구성8/8,heldoutv2 Gemini/JevSupervisor1/2/JevTools2/2. 실패원인은Validator가source=csv 식품 DB값에 RAG근거를요구한것. 정책수치와식품수치를구분하는지시를보강,RED→전체220pass1skip. 수정후v3는Gemini개발8/8+추가2/2,Supervisor8/8+2/2,Tools7/8+1/2. v3는heldout노출후회귀이며독립최종평가아님.
JevTools개발실패원인:search_foods주입장애→재검색성공→Gemini의미제공get_user_profile요청차단→추가Jev호출포함예산소진. 예산확대하지않고Jev운영미채택으로종료. 실제API504는LangSmithchild로그DEADLINE_EXCEEDED확인,Google공식오류문서검토후1회재확인성공,첫실패보존. 개발JevSupervisor invalid_response는fallback성공;최초raw미저장으로세부원인미확정. 공식Choice문서대조및raw보존별도1회probe정상confidence.97. 동일재현이아니므로해결단정안함. 진단후미실행행만SHA확인continuation으로완료,원실패행유지.
LangSmith실제trace5개확인(당시4완료1실행중,오류0). 최종py_compile/diffcheck통과. 기록:docs/agent_experiments/README.md,summary_v1.json,EVALUATION17장. 다음:판본·충돌근거정책의Validator/HITL/쓰기차단통합+새평가시나리오,그후streaming/DeepAgent/MCP/kind/UI.

### 근거 정책 강제 연결 — 2026-10-10
Ruling: 미확정Docling/Jev오류는현재PyPDF/Gemini운영경로를막지않아추가실험하지않음. 현재차단요인은근거충돌정책이실제쓰기와연결되지않았던것으로,기존resolve_claims를제안/Validator/HITL/승인직전트랜잭션에연결함. 운영검토claim없음은승인으로간주하지않으며빈catalog로자동숫자전략변경보류,기존식사/추천/확정목표유지.
TDD10RED→GREEN10; Agent충돌차단/Validator에receipt전달/정책변경승인차단3추가. 리뷰P2적용대상누락추정은RED1→명시적population/conditions필수로수정. HITL충돌설명RED→선택/제외근거strategy_note전달. 구형update_strategy_tool/재setup직접전략저장2RED→제안승인필수/기존전략보존. 공식LangChainguardrails/HITL문서대조,기존아키텍처유지. fresh최종리뷰추가P1/P2없음.
운영DB/API/key/env변경없음. 신규가입초기계산은이번범위미수정이며수치정책/적용대상등록과함께후속필수작업. 검토catalog와profile적용대상정보없이는자동전략변경활성화불가. 상세docs/agent_experiments/EVIDENCE_INTEGRATION.md. 전체회귀결과는backend/artifacts/evidence-release-tests.log,구문/diffcheck검증. 다음은실제자료의정책식·적용조건원문대조및초기계산정비,실제DB/HITL검증후streaming으로진행.

### 유지 에너지 계산 기반 — 2026-10-10
KDRI2025 PDF58/59/8 원문·표 대조, EER 순수계산 및 인증 read-only /users/energy-preview 구현. 활동·일반성인 자기보고 필수, 19<=age<65. 공식예시4개 ±1kcal 재현. 기본배분55/20/25는 서비스정책으로 구분, 감량고정차감 없음. 리뷰 숫자bool/확인1 허용3RED→strict+actualTrue→전체253pass1skip3warnings. Poppler 렌더링으로 pypdfium2 누락 우회, 신규의존성 없음. 상세 docs/agent_experiments/ENERGY_POLICY.md. 초기setup/DB/claim/HITL연결은 아직 미전환이며 다음필수단계; 운영활성화완료로 주장하지 않음.

### 초기 유지 기준선 온보딩/HITL — 2026-10-10
Ruling: 유지 기준선 승인과 목표별 처방을 분리. 2022감량지침의개별화/전문가조건을일괄차감으로바꾸지않음. 목표별최신근거검토미완료는명시. POST /users/onboarding 프로필+pending 동일트랜잭션, GET현재전략/유효pending복구, 기존전략보존. 계산입력JSON장기프로필/additive migration실제적용. KDRI2025 유지식/비율4claims 등록 및 receipt계산context/goal/catalog 재확인. 구형setup직접저장·오류후profile변경 제거. UI기능입력/확정/취소/재생성 연결, Cue전면디자인은후속.
실제DB synthetic 검증: 승인전0전략,취소재시도,확정,중복1건,기존보존,status복구,profile변경차단,proposal실패profile rollback;전체합성데이터rollback. UI8tests통과/build성공, backend최종로그 artifacts/onboard-final.log. npxoffline ENOTCACHED→공식CLI확인후온라인npx성공;UI중복query/Jestresetmock→로그/공식문서대조수정. 리뷰material3건RED/수정후재리뷰clean. 상세 docs/agent_experiments/ONBOARDING_HITL.md.

### 목표별 적용/보류 정책 — 2026-10-10
Ruling: 최신 식사치료원문/증량적용대상 검토가미완료인 상황에서숫자조정을활성화하지않음. 유지ready/감량latest_source_unverified/증량population_unverified 구조화,0조정. 목표방향/date/finite값검증, 요청주간변화는산술이며추천아님. 이번요청target값으로profile구성수정,receipt 목표체중/date재계산 및 오래된승인차단. Agent의유지기준선→완료된감량처방오표기1RED→서버설명교정. 전체272pass1skip3warnings,realDB 합성목표변경차단/원자성성공·전체rollback. 추가DB스키마/외부의존성/UI변경없음. PMC recaptcha·학회/DOI web InternalError는대체공개원저검색 확인했지만fulltext완료라고주장안함. 상세docs/agent_experiments/GOAL_POLICY.md. 자동조정여전히미완료;보류계약을포함한독립통합평가→streaming이후계획유지.

### 현재 운영 Gemini Agent 통합 평가 — 2026-10-10

Ruling: 과거 heldout은 이미 이전 Agent 실험에서 열어봤으므로 이번 실행을 새로운 독립 최종 평가로 재명명하지 않고 현재 코드의 통합 회귀로 기록한다. 운영 기본 Gemini만 분리 실행하는 `--variants gemini`와 최소 경로 대비 추가 전문도구 호출 지표를 추가했다. 첫 실행 56/60은 runner 기본gold가v1, analyzer가v2인 평가 인프라 불일치였고 원본v4를 보존한 채 parser default 계약 RED→GREEN 후 v5 60/60을 확인했다. heldout결정30/30, flow개발8/8·heldout2/2, 안전replay20/20, 근거정책/HITL42/42다. flow 추가 전문조회는개발4·heldout2이며 delegate는제외; 모두해롭다고단정하지않는다. LangSmith root metadata누락은 `langsmith_extra`로수정하고 smoke10trace/case10/error0을 실제조회했다. 안전runner정지는faulthandler로Python socketpair accept를확인했고 sandbox loopback제약에서재현,승인로컬실행3.59초20/20. WindowsSelector loop factory도서버규칙과통일했다. 최종리뷰의 provenance2건은 datasetSHA/snapshot/domain/split/variant fail-closed검증으로RED→GREEN수정. 전체277passed1skipped3warnings. 상세 docs/agent_experiments/AGENT_INTEGRATION_V2.md. 다음은새로운봉인RAG+Agent사례의Ragas/LangSmith독립최종평가.
### 독립 사실 그룹 RAG 최종 평가 — 2026-10-10

- 이전 heldout20은 임베딩 차원 선정에 이미 사용되어 새 최종셋으로 재사용하지 않았다. 기존 사실 그룹과 겹치지 않는 10개 사실 그룹·한영 20문항을 원문 대조하고 SHA를 봉인했다.
- 고정 운영 후보 PyPDF/recursive·Gemini 3072·Hybrid·reranker 없음으로 20/20 검색·답변 완료. strict 지정 페이지/구절 Recall@4 85%, 대체 유효 WHO 페이지를 원문 재검토한 evidence support 95%, Ragas faithfulness 1.00/context recall 0.95, 답변 p50 11.23초/p95 25.02초, 생성 58,151 tokens.
- 실제 누락은 영어 TFA 아동 외삽 1건이며 모델은 근거 부족으로 보류했다. 동일 한국어 질문은 성공해 영어 질의 확장 비대칭을 후속 개발 가설로 남겼다. 이 최종셋으로 튜닝 후 같은 점수를 재주장하지 않는다.
- Ragas FactualCorrectness는 기본 0.325, 공식 권고에 따른 한국어 prompt adaptation+검토 참조에서도 0.347이었다. 원문과 정확히 일치하는 답변도 0점인 사례가 있어 품질 지표로 채택하지 않고 evaluator diagnostic으로 보존한다. 비맹검 원문 answer review는 19/20이며 임상정책 승인으로 해석하지 않는다.
- 실패 진단: sandbox 네트워크 정체는 승인 네트워크 실행 20/20으로 환경 경계임을 분리했다. Ragas import 정체는 nest_asyncio의 Windows socketpair에서 확인해 heavy import를 실행 시점으로 이동했다. 호환 runtime 누락 import 실패와 중단된 trace replay도 별도 진단으로 보존한다.
- LangSmith `final-rag-trace-smoke-v1` root trace는 5초 색인 지연 후 success로 조회했다. 상세 보고서는 `docs/rag_experiments/RAG_FINAL_EVALUATION_V1.md`.
- 다음 단계는 최신 감량 지침과 증량 연구를 검토해 목표별 칼로리 조정 정책의 적용 대상·안전선·조정 상한을 확정하고 기존 HITL 전략 제안에 연결하는 것이다.
- 최종 리뷰 수정: 활성 RAG recipe와 모든 청크 metadata를 실제 설정에 대조하고, dataset/capture/answers/adjudication을 SHA와 identity로 연결했다. 실패 캡처는 누적3회까지만 재개하며 완료 캐시는 입력·출력 계약을 검증한다. 캐시 20건 재검증 후 수치는 동일했고 전체회귀285 passed/1 skipped/기존 warning3건이다. 미완료 metric의 nonzero 종료와 case_group 외 content fingerprint 중복 검사는 다음 평가 인프라 정비 항목으로 남긴다.

### 목표별 칼로리 정책 v2 — 2026-10-10

KDRI 유지식과 KSSO 2022 일반 성인 감량 정책을 연결했다. BMI 23 이상, 목표 체중·일자, 일반 성인 확인, 1,200/1,500 kcal 서비스 하한을 통과할 때 보수적 -500 kcal만 pending 제안하며 HITL 전 저장은 없다. 2024 개정은 진단·약물 범위라 식사치료 최신판 대체로 사용하지 않았다. 28~42일 체중감량 2.5% 미달은 생활습관 검토 신호만 내고 추가 자동 차감은 0이다. 증량은 제한된 연구 적용성 때문에 보류했다. canonical PDF page와 공백 정규화도 수정했다. 실제 Supabase 합성 HITL·중복·변경차단·롤백 검증 후 전체 데이터를 롤백했다. Backend 292 pass/1 skip/warning 3, frontend 8 pass/build 성공. 다음 단계는 실제 실행 이벤트·답변 SSE streaming과 재연결·중복 방지 검증이다.

### 실제 실행 스트리밍 — 2026-10-10

모델·도구 실행 경계에 request-scoped event sink를 연결해 `의도 분석 → 전문 Agent 위임 → 기록/영양/근거 조회 → 제안 검토`를 실제 수행 시점에 SSE로 보낸다. 답변은 `answer_delta`, 종료는 `completed`로 분리하고 모든 이벤트에 `run_id`와 `seq`를 추가했다. 프론트는 불완전 종료 시 같은 실행 ID와 마지막 순번으로 한 번 재접속하며 중복 이벤트를 무시한다. 연결 종료가 진행 중인 그래프·제안 트랜잭션을 취소하지 않고, 완료·실패 체크포인트 재접속은 실행을 반복하지 않는다. Backend 297 pass/1 skip/warning 3, frontend 11 pass/build 성공. 다음 단계는 Weekly Deep Agent와 읽기 전용 MCP다.

### Weekly Deep Agent·읽기 전용 MCP — 2026-10-10

명시적 weekly_review를 기존 production graph 안에서 WeeklyDeepTeam으로 분기했다. Supervisor는 최근7일·측정·목표추세 분석과 공식근거 검색의 두 전문 Agent를 각각 최대1회 호출한다. 두 Agent는 모델20/도구30/180초 durable budget을 공유한다. 근거 Agent는 MCP2.3.0 서버의 read-only search_evidence를 사용하며, MCP 공개목록은 음식검색·확정량 영양계산·근거검색3개뿐이다. 전략 변경은 기존근거정책/Validator/pending proposal/HITL을 그대로 통과하며 MCP에는 사용자DB·write도구가 없다. GET주간리포트는읽기전용policy+대화lock, 변경제안은chat의명시적weekly_review에서만허용한다. bare dict structured output 등록 InvalidSignature는 SDK 로그에 따라 dict[str,Any]로 수정하고 실제 call_tool을 검증했다. 신규11pass, 전체backend308pass1skip기존warning3. 실제 사용자 gold 품질·지연 평가는 아직이며 다음은 API/worker/MCP 컨테이너 분리와 kind 재시작·상태/예산/중복저장 검증이다.

### Agent 성능 최적화·화면 상태 복원 — 2026-10-11

동일 실행 안에서 동일 근거·음식·영양 조회를 재사용하고, 성공한 전문 Agent 답변을 Supervisor가 다시 요약하던 모델 호출을 제거했다. 개발 흐름 8개 목표 달성률 8/8·정책 위반 0을 유지하면서 p50 16.64→9.31초(-44.0%), p95 24.92→13.69초(-45.1%), 모델 호출 35→30(-14.3%)으로 줄었다. 이전 artifact에 총 도구 호출 수가 없어 도구 호출 감소율은 주장하지 않는다.

화면 복원 API는 체크포인트·유효 proposal·최근 대화·오늘 통계를 읽기만 하며 Agent를 재실행하지 않는다. 프론트는 최초 mount에서 한 번 복원하고 기존 proposal ID/version으로 승인 경계를 유지한다. 현재 대화 테이블은 thread ID가 없어 메시지는 사용자 최근 20건 범위라는 한계를 기록한다. 최종 회귀 backend 323 passed/1 skipped, frontend 16 passed, production build 성공.

FlashRank OOM은 Kubernetes 자체 결함이 아니다. API·4,139청크 BM25·Kiwi·FlashRank 런타임이 한 Pod의 1GiB 메모리 예산을 초과했고 Kubernetes가 OOMKilled로 격리했다. 리랭커 없는 Hybrid가 품질도 더 좋았으므로 운영에서 제거했다. 향후 리랭커가 품질을 유의미하게 높이는 경우에만 별도 서비스, 경량 모델 또는 메모리 증설을 같은 조건으로 재평가한다.

### Weekly Deep Agent·MCP 장애 통합 평가 — 2026-10-11

부분 기록, MCP 장애, 모델 예산 소진, 근거 충돌, MCP 쓰기 요청 5개를 fault injection으로 검증했다. 모두 목표 계약을 통과했고 승인 전 저장과 정책 위반은 0건이었다. Windows Python 3.13 asyncio 대기는 기존 호스트 런타임 이슈로 분리하고 Linux 이미지에 소스를 read-only mount해 집중 테스트 15 passed를 확인했다. scripted model 평가이므로 실제 Gemini 품질·지연·비용은 다음 독립 최종 평가에서 측정한다. 결과는 `backend/artifacts/weekly-deep-integration-v1/summary.json`에 보존했다.

저장소 전체 read-only mount로 배포 매니페스트 경로까지 포함한 최종 백엔드 회귀는 327 passed/1 skipped다. 첫 전체 실행의 5개 실패는 backend 디렉터리만 mount해 저장소 루트 파일이 보이지 않은 실행 환경 오류였고, 전체 저장소 mount 후 모두 통과했다.

### 독립 Agent 최종 평가·LangSmith — 2026-10-11

새 flow 8개를 실행 전 동결하고 Gemini 운영 경로를 각 1회 평가했다. 목표 달성 8/8, 정책 위반 0, 승인 전 domain write 0, p50 16.71초, p95 28.05초, 모델 28회, 도구 24회다. LangSmith에서 동일 experiment의 root trace 8개와 오류 0을 API로 확인했다. 추가 읽기 2회 중 1회는 선제 intake 조회, 1회는 의도적으로 주입한 일시 장애 복구 재시도다. RAG는 기존 독립 20문항의 Ragas faithfulness 1.00/context recall 0.95를 고정하고 재튜닝하지 않았다. 원본은 `backend/artifacts/agent-final-independent-v1`에 있다.

### 체크포인터 연결 풀 — 2026-10-11

현재 graph lifespan의 AsyncPostgresSaver는 `AsyncConnectionPool(min=1,max=10,timeout=15)`을 사용한다. pool open→schema setup→graph compile과 종료 시 pool/전역 graph 정리를 회귀 테스트로 고정했고, AGENTS.md의 단일 연결 한계를 갱신했다. 실제 Supabase 연결 상한과 부하 시 timeout/복구 시간은 배포 환경 시험 과제로 남긴다.

최종 Linux 컨테이너 전체 회귀는 328 passed/1 skipped다. 프론트는 화면 복원 구현 뒤 16 tests와 production build를 통과한 상태이며 이후 프론트 코드는 변경하지 않았다.

### 실제 DB pool·대화 분리·개인정보 로그 — 2026-10-11

실제 Supabase에 chat_history.thread_id migration을 적용했다. NOT NULL/default와 user+thread+created_at 인덱스, 빈 thread 0건을 확인했다. 기존 행은 legacy로 격리하고 신규 저장·복원은 thread별로 분리한다. 실제 DB read-only pool 시험에서 동시 20건 전부 성공, 취소 직후 복구 0.0314초, 종료 waiting 0이었다. 운영 stdout의 메시지·응답·OCR·질의·검증 본문을 제거하고 LangSmith input/output 기본 숨김 및 가명 thread ID를 적용했다. 최종 backend 333 passed/1 skipped. 상세 기준은 docs/OPERATIONS_PRIVACY.md, 측정 원본은 backend/artifacts/postgres-pool-recovery-v1.json이다.

### Container·kind recovery — 2026-10-10

API·scheduler worker·read-only MCP를 하나의 비루트 이미지와 세 실행 프로세스로 분리했다. Compose에서 API scheduler를 끄고 worker만 스케줄을 실행한다. kind에서는 API 2개, worker 1개, MCP 1개가 Ready가 됐으며 API rollout restart 뒤 두 새 Pod가 Supabase `AsyncPostgresSaver` 준비와 그래프 빌드를 다시 완료했다. Kubernetes가 이름 기반 `USER app`을 비루트로 정적으로 확인하지 못한 실패는 실제 UID/GID 999를 securityContext에 명시해 해결했다. 집중 회귀 18개와 Linux 컨테이너 전체 회귀 313 passed/1 skipped/기존 warning 3건을 확인했다. Windows 호스트 pytest는 Python `socket.socketpair()`의 localhost accept에서 멈춰 Linux 컨테이너를 검증 기준으로 사용했다.

독립 보안 리뷰에서 MCP 프로세스에 공용 `.env`/Secret 전체가 주입되고 인증 없는 NodePort가 공개되는 문제를 발견했다. MCP에는 Gemini/Pinecone 키만 들어가는 전용 Secret을 사용하고, kind에서는 ClusterIP로만 노출하며, Compose 호스트 포트는 `127.0.0.1`에만 바인딩하도록 수정했다. 실제 배포 Secret의 키 이름과 MCP 재기동·내부 연결을 확인했다.
Pinecone 인덱스가 없을 때 일반 검색이 인덱스를 생성하던 동작도 제거했다. 생성은 build 경로에서만 허용하고 MCP 런타임은 오류로 종료해 외부 상태를 변경하지 않는다.

### Cue-inspired streaming UI — 2026-10-10

Cue의 의도 이해→검색·검토→답변→참고정보 흐름을 참고하되, 백엔드가 실제로 보낸 SSE 단계만 타임라인으로 표시한다. 완료 답변에는 접을 수 있는 검토 과정을 보존하고, 전략 변경 제안은 영양 목표·적용일·출처/페이지/판본/적용 대상과 HITL 버튼을 한 카드에서 확인하도록 구성했다. 연결 실패는 별도 오류 상태로 표시하고 모바일 390px 반응형을 적용했다. 임시 개발 프리뷰로 데스크톱·모바일을 Playwright 확인한 뒤 인증 우회 코드는 제거했다. 최종 프론트 **15 tests passed**, production build 성공, 브라우저 error/warning 0건이다.

### 실제 인증 E2E·RAG 런타임 수정 — 2026-10-11

실제 Supabase 합성 사용자로 온보딩/HITL/식사 기록/중복 확정/스트리밍을 확인했다. E2E에서 활성 Gemini build와 kind 설정 불일치, 최종 선정과 달리 FlashRank가 기본 활성화돼 1GiB Pod를 OOMKilled한 문제, 근거에 없는 끼니 비율 생성, 식단+근거 요청의 Evidence/Meal 중복 위임을 발견했다. 활성 4,139청크 경로·namespace와 `RAG_USE_RERANK=false`를 배포/런타임에 통일하고, 끼니별 수치 근거 가드와 명백한 식단 추천의 Meal Agent 단일 후보를 적용했다. 최종 실제 검색 grounded=true/max_score0.862, API2 Pod restart0, 실제 UI 요청 완료. model12/12·tool17/20·99.76초로 지연·예산 여유는 다음 성능 개선점이다. 최종 backend318passed/1skipped, frontend15passed, production build 성공. 세부 실패·수정·한계는 EVALUATION.md 28장.

### Agent 성능 최적화 — 2026-10-11

요청 실행 범위의 근거·음식 검색과 영양 quote 캐시, 런타임 동일 읽기 도구 재생, 전문 Agent 성공 뒤 Supervisor 재요약 LLM 호출 제거를 적용했다. 쓰기/proposal/delegate/실패 결과는 캐시하지 않고 모델 주도 최초 위임·전문 도구 선택·실패 피드백·HITL은 유지한다. 고정 개발 흐름8/8 목표달성·정책위반0, p50 16.64→9.31초, p95 24.92→13.69초, 모델35→30. 기존 heldout 회귀2/2, p9523.69초. 모든 개별 흐름 model≤8/tool≤12/60초 이내. 실제서비스 지연으로 일반화하지 않으며 변경 후 실제 인증 E2E는 다음 측정에서 수행한다. 원본 `backend/artifacts/agent-flow-optimized-{v1,heldout-v1}`, 상세 EVALUATION29장, 전체322passed/1skipped.

FlashRank OOM 포트폴리오 결론도 유지한다. Kubernetes가 OOM을 만든 것이 아니라 API·BM25 4,139청크·Kiwi·FlashRank 런타임의 합산 메모리가 Pod 1GiB 제한을 넘었고 Kubernetes가 격리 종료했다. FlashRank는 품질 개선도 입증하지 못했으므로 단순 증설 대신 최종 평가 우승 구성인 Hybrid+reranker 없음으로 운영을 통일했다. 리랭커 재도입 시에만 별도 서비스·경량 모델·메모리 증설을 같은 품질/지연/메모리 조건으로 재평가한다.

### 실제 브라우저 사용자 생명주기 E2E — 2026-10-11

실제 Chromium과 Supabase 합성 계정으로 로그인·온보딩·전략 HITL·식사 proposal·새로고침 복원·222 kcal 확정 저장·조회·회원 탈퇴를 완료했다. 삭제 전 JWT의 온보딩 재호출은 401이었다. E2E에서 과거 Docker 이미지의 restore 404, 신규 thread 404의 잘못된 오류 표시, `기록만 요약`의 record_only 오분류, 같은 시각 chat 행의 역순 복원을 발견했다. 현재 소스 이미지 재빌드, 빈 복원 처리, 조회 의도 분리와 meal 조회 도구 지침, UTC microsecond 및 role 보조 정렬로 각각 수정했다. 세부 결과는 EVALUATION.md 37장에 기록했다.

### Compose 운영 안정성 재검증 — 2026-10-11

- API·worker·MCP 모두 비루트 `app` 사용자와 개별 healthcheck로 재빌드·기동했다. 이미지에 writable 검증 artifact 디렉터리와 proposal migration을 명시적으로 포함했다.
- 실제 첫 실패 두 건을 로그로 분리했다: `/app/artifacts` 생성 권한 오류와 이미지 내부 migration 누락. 이를 고친 다음 나타난 `ProposalConflict`는 오래된 `policy_version=test` 합성 fixture가 현재 근거 정책에 의해 거절된 것이 원인이어서, 운영과 같은 baseline/evidence receipt 생성으로 교체했다.
- 실제 Supabase 풀 검증은 20개 동시 조회 전부 성공, 취소 후 복구 0.0182초였다. API 정상 재시작 뒤에도 20개 전부 성공, 복구 0.0212초였다. proposal 원자성 검증은 두 번 모두 통과하고 합성 데이터를 롤백했다.
- API 재시작 동안 worker/MCP는 유지됐고 최종 세 서비스는 healthy, OOM 없음이다. Compose 단일 API 검증이므로 무중단 replica 전환은 kind/실배포 환경의 별도 범위다.

### Cue 참고 UI 최종 마무리 — 2026-10-11

- 세션 복원 loading/error/retry, 빈 대화 prompt starter, 입력·아이콘 접근성 이름을 추가했다. 복원 재시도는 화면 상태만 조회하며 완료된 Agent 실행을 다시 호출하지 않는다.
- 인증·온보딩을 채팅과 같은 색상·타이포그래피·표면 체계로 통일하고 로그인 form/label/Enter 제출을 적용했다.
- 실제 합성 계정의 데스크톱·390px 빈 화면과 모바일 실제 스트리밍→완료 전환을 Chromium으로 확인했다. 계정 삭제 뒤 이미 제거된 Auth 사용자에 대한 logout 403도 진단해 targeted local session clear로 수정했다.
- 합성 계정과 임시 자격증명은 정리했다. 상세 캡처와 판정은 `design-qa.md`, 정량·오류 기록은 EVALUATION.md 39장에 있다.

### E2E 후속 결함·한국 서비스 날짜 통일 — 2026-10-11

실제 브라우저 흐름에서 HITL 중단 전에 대화 저장 노드가 실행되지 않아 proposal 설명 메시지만 새로고침 후 사라지는 결함을 찾았다. proposal 생성 턴을 먼저 저장한 뒤 confirm에서 중단하도록 그래프 순서를 바꿨고, 새 proposal의 메시지·카드 복원을 확인했다. 모델이 “오늘” 섭취를 과거 날짜로 제안한 사례는 상대 날짜를 LLM 출력에 맡긴 설계가 원인이어서 신뢰된 state/service 날짜로 덮어쓰도록 했다.

컨테이너 UTC와 한국 날짜가 자정 부근에 어긋나는 문제는 `SERVICE_TIMEZONE=Asia/Seoul`과 `service_today()`로 해결했다. 오늘 집계·편집·분석·계획·목표·전략 적용일·온보딩·스케줄러가 같은 시계를 사용하며 UTC 저녁→한국 다음날 경계와 proposal/HITL 회귀를 테스트한다. 독립 RAG 최종 20문항의 유일한 실제 근거 누락도 영어 WHO 아동 외삽 질의 확장 차이로 원인을 특정했으며, 안전 보류가 동작했으므로 운영 recipe는 유지하고 별도 개발셋 실험으로 분리했다. 상세는 EVALUATION.md 40장이다.

### kind 스테이징 무중단 rollout — 2026-10-11

API 2개 replica에 maxUnavailable 0/maxSurge 1, startup probe, 60초 종료 유예와 PDB(minAvailable 1)를 적용했다. 실제 rolling restart 중 health 400/400 성공, 실패 0, p50 3.97ms, p95 5.86ms였고 두 Pod가 restart 0으로 교체됐다. 새 Pod의 Supabase pool 동시 20건·취소 복구와 proposal 원자성 검증도 통과했다. 최초 tar import 경로 문제와 rollout 직후 exec exit 137은 각각 kind 노드 `/var` import와 cgroup/이벤트 진단 후 안정된 Ready Pod 재실행으로 해결했다. exit 137은 OOM이 아니었으며 proposal 검증 스크립트의 UTC 날짜 잔존도 서비스 날짜로 수정했다. 상세와 한계는 EVALUATION.md 41장, 원본은 `backend/artifacts/kind-rollout-health-v1.json`이다.

### 인증 SSE 교차 Pod 복구 — 2026-10-11

Pod 로컬 progress journal이 사라진 상태에서 durable checkpoint가 `running`이면 다른 API Pod가 같은 run ID로 LangGraph 실행을 Postgres checkpoint부터 재개하도록 보완했다. 실제 합성 사용자 SSE의 첫 progress event 뒤 담당 Pod를 강제 삭제하고 Service로 재접속한 결과 49개 후속 이벤트와 completed를 받았다. 승인 전 meal 0건, pending proposal 1건이었고 같은 제안을 두 번 승인한 뒤에도 meal은 1건이었다. 합성 Auth 사용자는 정리 후 0건이다. 이로써 로컬 kind 범위의 무중단 health뿐 아니라 LangGraph 실행 재개·HITL·중복 저장 방지까지 검증했다. 실제 클라우드 ingress와 동시 사용자 부하는 제한 베타 단계에서 남는다. 상세는 EVALUATION.md 42장, 원본은 `backend/artifacts/sse-pod-recovery-v1.json`이다.

### Render 무료 베타 배포 준비 — 2026-10-11

Render Blueprint에 무료 Docker API와 정적 React 사이트를 정의했다. 별도 무료 worker를 가정하지 않고 API에서 scheduler를 실행하며, Weekly Deep Agent의 읽기 전용 MCP는 기존 in-process 호출을 유지한다. 배포 URL은 `CORS_ORIGINS`와 `REACT_APP_API_URL`로 명시하고 비밀값은 모두 Dashboard 입력(`sync: false`)으로 남겼다. git-ignore된 실험 경로에만 있던 활성 4,139개 BM25 청크를 이미지에 포함되는 추적 경로로 승격했다. 실제 Docker build와 이미지 내부 4,139청크·메타데이터, React production build를 확인했다. 실제 공개 URL 생성과 외부 부하 시험은 GitHub/Render 계정 연결 뒤 진행한다. 절차와 무료 플랜 한계는 `deploy/RENDER_BETA.md`에 기록했다.
