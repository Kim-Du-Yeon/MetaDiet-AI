## 최신: 동일 조건 Hybrid vs Hybrid+Agentic100시도씩 비교

[통제 비교 전체 결과·오류·비용·채택 판단](20261021-controlled-hybrid-v14/README.md). 같은 최종 프롬프트·Flash 모델·Hybrid 설정·환경에서 새200답변과Pro200판정을 완료했다. 정답89%→80%,이진 근거 충실성100%→99%,중앙값6.435→9.709초,p95 10.663→15.477초,모델+임베딩 추정/100시도$0.293046→$0.399767. Agentic이 기존 오답1건을 회복했지만 정답10건을 놓쳤다. **기존 Hybrid/no-reranker 유지·Agentic 운영 미채택**으로 판단했다. 구현·비교 실험 완료와 운영 적용X를 구분한다.

40질문/20사실그룹 반복 개발셋이며 독립100문항·사용자 성공률이 아니다. 같은 정적 답변 지침을 양쪽에 적용하고 Agentic의 동적 답변 지침은 제거했다. 충실성은 Pro 이진 판정으로 Ragas와 혼용하지 않는다. 모든 보류를 분모에 남겼고,요청 실패·출력 잘림은0건이었다. 아래 과거 dense 비교와 독립20문항 평가 기록은 서로 다른 평가 범위의 보존 자료다.

## 이전 dense 비교: 개별 실패 포함100시도씩 완료

[일반 RAG 대 Agentic v14 전체 결과](20261021-rag-vs-agentic-v14-complete100/README.md): Pro 내용 정답85%/88%, 정상 종료 확인 Agentic 정답84/100. 운영 미채택·기존 Hybrid/no-reranker 유지. [기존 RAG 조합 실험과 통합 판단](../rag_experiments/RAG_RECIPE_DECISIONS.md). 아래 조기 중단 이력은 과거 원본이며 최종 결과를 대신하지 않는다.

# Bounded Agentic RAG (experimental)

[ag-022 직접 정의 재검색 단일 실측 통과](20261021-ag022-definition-live/README.md): 직접 정의 부족 판정 → 실제 재검색 1회 → 정의 회수 → 답변 → Pro Batch 정확성·충실성 통과. 새 버전 전체 100건 품질 검증·배포는 아직 수행하지 않았다.

[질문 대상의 직접 정의 구분 — 오프라인 개발](20261021-definition-evidence-offline/README.md): controller-v12와 직접 정의 재검색 게이트. 별도 가상 개발셋·저장 판정 재생만 수행, 신규 유료 호출 없음. 실제 모델 분류 정확도는 미검증.

[ag-022 공백 검증 실측](20261021-ag022-whitespace-live/README.md): 평가·원문 span 검증은 통과했지만 후속 QA가 보류해 추가 호출을 중단했다. 관련 개념의 언급과 질문 자체의 정의를 구분하는 충분성 검토가 남아 있다.

[공백 차이 원문 검증 오프라인 보강](20261021-ag022-recheck/WHITESPACE_OFFLINE.md): 저장된 ag-022 판정을 원문 위치로 연결해 재생 통과. 수치·단위·문장 변경은 차단하며 신규 유료 호출은 없다.

[ag-022 수정 후 단일 재검증](20261021-ag022-recheck/README.md): 길이 제한 파싱은 통과했지만 공백 배치 차이로 엄격한 발췌 일치 게이트가 실패했다. 유료 1회 뒤 추가 호출 중단. 후속 답변 생성·품질 평가·배포 없음.

[ag-022 단일 진단 및 오프라인 수정](20261021-ag022-diagnostic/README.md): STOP·출력 103토큰, 240자 발췌 스키마 위반 확인. 유료 1회 후 추가 호출 없음. 수정 후 실제 모델 성공 여부는 아직 미검증.

[부분 답변·필수 조건 보존 오프라인 개발 검증](20261021-partial-answer-development/README.md): controller-v10 후보. 유료 호출·배포 없음. 기존 품질 게이트 실패 상태는 유지하며, mock 통과를 실제 품질 향상으로 주장하지 않는다.

The active LangGraph coaching team can optionally call a read-only evidence loop: retrieve → assess against the original question → rewrite → retrieve → assess. This is a bounded tool-internal workflow, not a replacement of the supervisor graph or HITL write gate.

- `AGENTIC_RAG_ENABLED=false` by default. Rollback by disabling it and restarting.
- `AGENTIC_RAG_MAX_ROUNDS=2` (hard range1–2): initial search plus at most one rewritten search.
- `AGENTIC_RAG_TIMEOUT_SECONDS=35` (hard maximum60): total local loop deadline, also subject to the request deadline.
- At most two Lite controller calls,512 output tokens each; controller input capped at6000 evidence characters. Korean query translation is also reserved in the shared model budget. Every additional retrieval reserves a shared tool call.
- Existing dense similarity gating remains mandatory. A controller cannot promote low-score evidence. Rejected, timed-out, failed or unassessed passages cannot become answer evidence. Source/page/document hashes survive excerpt clipping.
- No retries on transport/controller errors in this request; subsequent distinct queries are suppressed after operational failure. No user record writes or automatic confirmation.
- Progress events report actual retrieval, evaluation, rewrite and research phases. Sources still require explicit answer citations; retrieved-but-unused documents do not become citations.
- Controller prompt has its own version/hash. Existing prompt release v1 is unchanged. Prompt versioning does not eliminate model nondeterminism.

## Evaluation

[Fixed100-per-condition read-only development comparison](20261020/README.md) records the conditional rollout decision and limits. Do not infer clinical accuracy or public browser p95 from a repeated development QA benchmark. The historical sealed final20 was not used to tune this loop.

## Official design references

- [LangGraph Agentic RAG](https://docs.langchain.com/oss/python/langgraph/agentic-rag): grade documents and route to generation or question rewriting. Our loop additionally has hard call/deadline limits and fail-closed evidence handling.
- [Gemini structured outputs](https://ai.google.dev/gemini-api/docs/structured-output): schema-constrained output; local validation and failure handling are still required.
- [Gemini thinking token limits](https://ai.google.dev/gemini-api/docs/thinking): output limits include reasoning; a512-token Pro judge can truncate before JSON completes.
- [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing): frozen token estimates are not invoices; embedding text input listed at$0.20/M tokens when checked2026-10-20.

## Reproduce

Run from repository root with the project venv and ignored backend/.env. Never commit credentials. The runner reads production vectors but never creates an index or touches user tables.

```powershell
backend/venv/Scripts/python.exe backend/scripts/eval/benchmark_agentic_rag.py --output docs/agentic_rag/20261020
backend/venv/Scripts/python.exe backend/scripts/eval/rejudge_agentic_rag.py --output docs/agentic_rag/20261020 --grades-name new-judges.jsonl
backend/venv/Scripts/python.exe backend/scripts/eval/analyze_agentic_rag.py docs/agentic_rag/20261020 --grades-name quality-status.jsonl
```

Runners refuse to overwrite existing attempts. Copy the frozen cases/protocol into a new result directory for a new experiment. Existing failure rows must remain in reports. Recovered judging never regenerates serving answers; original judge failures/cost remain separate.

## Evidence retention v2 (2026-10-21)

Qualified initial evidence is retained before deduplicated new evidence, capped at 8 documents / 6000 characters for both assessment and answer. Controller prompt v1 and hard loop limits are unchanged. [Completed quality judging and matched 100-per-condition revalidation](20261021/README.md): no correctness gain; default OFF, no rollout.

## Scoped table-aware policy (2026-10-21, not adopted)

Controller-v3/recipe-v4 clarifies sufficient as a supported scoped response and sends bounded answer guidance only with sufficient evidence. Hard limits and score gate remain. [Separate development and full100-pair comparison](20261021-v3/README.md): correctness89→89%, page support76→80%, p95 21.203→20.300s, model API cost+6.8% with complete raw embedding usage. Quality gate failed; keep OFF. Partial-response gains were offset by missing quantitative facts; do not equate page hits with answer coverage.


## Core numerical coverage and applicability follow-up (2026-10-21)

[Separate development12 and fresh100 attempts per condition](20261021-core-scope/README.md): candidate controller-v6/recipe core-scope-v7 adds required bounded `missing_core`, a code guard against early acceptance with missing primary facts, MAX_TOKENS rejection, and source-associated population metadata in the same6000-character context budget. Original-first qualified evidence retention and2 searches/2 assessments/8 documents/default35s limits remain. A supported negative scope answer is coverage, while an arbitrary extra prescription can remain unestablished. Generic non-nutrition logic examples were refined only on separate synthetic development data; no nutrition gold numbers were added.

Frozen controller-v3 baseline versus v6: Pro correctness89→95%, faithfulness100→100%, page support80→76%, p50 12.856→13.756s, p95 17.029→21.410s, serving model+embedding estimate$0.597061→$0.688828 per100. All200 serving attempts and200 Pro grades completed with complete serving token costs; final Pro Batch cost$0.589137 separate. Six answers recovered (four applicability, two table interpretation), no correctness regressions. Three English leucine attempts now detect missing quantities and research, but still fail to retrieve the needed excerpt and abstain; two Korean table answers still abstain. Five page-support losses and one gain yield the four-point decline. Frozen page labels were not loosened after seeing results.

The predeclared support-noninferiority gate failed despite the95% correctness threshold passing. Keep `AGENTIC_RAG_ENABLED=false`; no public candidate rollout or browser activation verification.1518 backend tests passed, one existing skip, three dependency deprecation warnings. These are repeated40 development questions, Dense-only RAG-boundary latency and automated Pro scoring; not100 independent users, public end-to-end performance, live-record freshness, Ragas or human review. See linked raw results, preserved development failures, hashes, per-case analysis and next-step limits.


## Adjacent chunks, Korean tables and provider-failure follow-up (2026-10-21)

[Implementation, separate20 fictional development probes, 100 attempted slots per condition, and funding-blocked decision](20261021-adjacent-table/README.md). Candidate-only adjacent excerpts use the exact selected local build, document SHA/source/page/full-text anchor identity, at most2 neighboring700-character excerpts, no extra embeddings/tokenizer, and shared8-document/6000-character/2-round limits. Cold cache initialization is serialized. Generic Korean table-header, inference-limit and population-scope guidance adds no nutrition gold values. Development Pro correctness16/20→20/20, faithfulness20/20 both; expected-round flow19/20 in the candidate leaves one unnecessary research call.

The fresh100+100 attempt cohort hit HTTP402 prepayment-credit depletion: request-completed53/54, request-failed47/46, operational failures52/100 each including fallback errors. Final Pro judging was not submitted; correctness/faithfulness and total cost remain unverified. Fast failures invalidate latency-improvement claims. Raw rows and all development failures remain. The baseline is a previous experimental v6 candidate, not deployed production. Keep OFF; no public rollout or candidate browser verification.

Post-cohort v11 error handling fixes missing max_score after retrieval exceptions and preserves sanitized provider causes. Generation/inline-judge credit, auth and daily-quota failures stop queued cases, record unstarted slots separately, and exit2; mocked100-pair integration tests verify at most3 calls after first402. Original v10 frozen sources and later v11 snapshots are separate; v11 has offline regression evidence only. Resume only after funding readiness and a per-experiment cost ceiling: probe failed cases, reuse stored answers for rejudging, and reserve a fresh100-pair run for the prepared final candidate. No claim about account-wide billed spend or production AI availability.
# 평가 비용 제한

[v14 생성·채점 재배분 후 동일100건 비교 시도](20261021-v14-final100/README.md): 앞선20쌍 후보 정답/충실성 통과, ag-013 실제 경로 통과. ag-022의 controller 충분 판단 후 QA 보류로23건에서 중단,77건 미실행. 전체 미통과·운영 미적용, 누적 사용·예약 $2.529382/$5.

[v14 최종100건 사전 검사](20261021-v14-final100-preflight/README.md): 비교 생성 잔여 $0.246213으로 고정 출력 상한의100건 계획을 확보하지 못해 신규 유료 호출 없이 중단. 누적 사용·예약 $2.270037/$5와 단계별 상한 유지.

[ag-013 문맥·중복 질의 종료 수정 및 한 건 재확인](20261021-ag013-repair/README.md): 저장된 검색 문맥 재사용, controller/답변/Batch 각1회로 정답·충실성 통과. 누적 사용·예약 $2.270037/$5. 전체100건 통과나 운영 적용 성과는 아니다.

[v13 최종100건 비교 시도 결과](20261021-v13-final100/README.md): 저장 답변 재사용 후15쌍 채점에서 ag-013 핵심 수치/조건 미답변으로 중단, 85건 미실행. 원문 연결 오류는 재발하지 않았지만 전체 기준 미통과·배포 보류. 누적 사용·예약 $2.256519/$5.

[문서 ID 선택으로 반복 원문 연결 실패 수정](20261021-document-id-smoke/README.md): v13 최소 실측 1건이 원문 exact 연결·답변 생성까지 완료. 100건 품질 비교와 운영 적용은 별도이며 누적 사용·예약 $2.084143/$5.

[승인된 단계별 예산 재배분 후 최종 확인](20261021-final-reallocated100/README.md): 전체 $5 유지, 첫 사례 원문 발췌 불일치로 즉시 종료. 99건 미실행, 누적 사용·예약 $2.078112.

[최종 오프라인 후보 고정·최종 비교에 남은 작업](20261021-final-candidate-offline/README.md): 추가 기능과 유료 호출 없이 코드·테스트·기존 결과의 해시를 고정했다. 실제 실패 해결·운영 적용은 아직 검증되지 않았다.

후속 [v9→v12 동일 100사례 비교 시도](20261021-v9-v12-matched100/README.md)는 기존 100답변·채점을 재사용했으나 새 버전 첫 사례의 원문 발췌 검증 실패로 즉시 중단했다. 99건 미실행, 비교 미완료·배포 보류다. 누적 사용·예약 $2.077268/$5.

[전체 $5·단계별 예산, 오프라인 기본값과 저장 답변 재사용](BUDGET_POLICY.md).
해당 평가 CLI의 유료 실행은 기본 차단되며, 새 유료 호출 없이 오프라인에서 검증했다.

후속 실제 실행은 [사용·예약 $0.099494에서 채점 한도로 중단](20261021-budgeted-validation/README.md).
조건별 7개 응답을 보존했으며 최종 비교 미완료·배포 미적용이다.

[분할 Batch와 실제 사용량 정산 구현·오프라인 확인](BATCH_SPLIT_SETTLEMENT.md).
최종 관련 테스트 91개 통과. 전체/단계별 예산 및 기존 중단 장부는 유지하며 새 유료 호출은 없다.

[후속 실제 분할·정산과100건씩 비교 결과](20261021-batch-live-validation/README.md):
누적 사용·예약 $2.001159, Pro $0.658710로 한도 내 완료. 분할 정산은 실제 성공했으나
정답률85%→83%로 품질 기준 미달, 배포 보류. 이후 추가 유료 재실험은 하지 않았다.
