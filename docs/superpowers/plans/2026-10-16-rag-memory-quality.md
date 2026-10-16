# Isolated RAG Memory and Quality Verification

**Goal:** Verify the small-memory retrieval fallback over two real hours and compare it with the selected hybrid recipe on the same ≥100 attempts, without operating on production user records.

**Architecture:** Standalone RAG evaluation processes, existing committed corpus and read-only Pinecone queries; no API server, graph, Supabase client, checkpoint or proposal repository. Allowlisted Gemini/Pinecone credentials only, in a git-ignored validation env file. Never deploy a test endpoint or change the active index.

**Tech stack:** Project Python venv, existing Gemini/Pinecone/LangChain libraries, stdlib process/memory APIs. No new dependency.

**Spec:** User's 2026-10-16 request for isolated long-duration memory verification and ≥100 paired quality attempts; AGENTS.md performance policy.

## Frozen protocol

- Existing reviewed development40 questions (20 fact groups, English/Korean), three repeats,120 attempts/condition. Repeated cases are not120 independent questions or real-user outcomes.
- Same active Gemini namespace, release corpus hash, frozen translations, k4/candidate20, no reranker, same grounding threshold and QA prompt.
- Conditions: `dense_fallback` (actual guard at512MiB) and `hybrid` (Kiwi one worker, larger independent process). Verify actual retrieval mode; never silently score hybrid fallback as hybrid.
- Alternating condition blocks/repeat order, concurrency2, retained per-attempt failures/timeouts. Freeze input identity before running. Independent Gemini Pro judge, same answer/reference/context contract; judge errors remain missing scores in full denominator.
- Metrics: acceptable source-page hit, excerpt support, MRR, grounded rate, answer correctness/support, citation/refusal coverage, failures/timeouts, completed-request p50/p95 and all-attempt duration. Not service latency or clinical accuracy.
- Operational quality gate: dense page-hit and supported-correct answer rates no more than5 percentage points below hybrid; failure delta≤2 points. This is a predeclared development screen, not a statistical non-inferiority claim. Do not tune on final20/heldout20.
- Soak:7200 wall seconds, every20s, two concurrent remote retrievals, current process RSS/private/peak and tokenizer/cache state samples. Freeze translations to isolate retrieval lifetime. Health/DB records never loaded.
- Memory screen: no MemoryError/crash, completed duration≥7200s, failure rate≤1%, no Kiwi/BM25 loaded, private commit<90%512MiB, warmed first/last15-minute median growth≤32MiB. This workload cannot prove absence of all leaks or full API/DB stability.

## Decisions and execution ledger

- [x] Inspect architecture, existing data/evaluation, release corpus and memory guard.
- [x] Read Docker, Linux cgroup, Pinecone and Windows Job Objects official documentation.
- Ruling: Docker CLI returned pipe permission error in sandbox; elevated daemon/version and image-list calls each timed out30s. Official `docker desktop start --timeout60` reported already running. Do not restart the engine or disturb other workloads. Use isolated Windows processes with an enforced Job Object private-commit limit if available, injecting the512MiB guard input only in the evaluator. Report this explicitly as a Windows surrogate, not a Linux/Render cgroup soak.
- [x] Test safety isolation, failure denominator, identity and memory gate before implementing evaluator. Nine new unit checks; RED→GREEN.
- [x] Run smoke first; preserve failures, diagnose with official sources, then run120+120 live paired retrieval attempts. The7200s soak remains running until its real deadline.
- Ruling: OpenBLAS initialization exceeded the Windows private-commit cap. Official NumPy/OpenBLAS docs support import-time thread limits; set all native BLAS thread variables to1 in the evaluator only. Production configuration unchanged.
- Ruling: Actual Gemini calls returned402 prepayment depletion even after inherited GOOGLE_API_KEY removal. User explicitly chose no top-up. Preserve the failed6-request/40s pilot and independent402 probe; use validated historical same-model query vectors for new live Pinecone retrieval. Do not score or claim new answer generation/judge quality.
- [x] Review differences/failures. Completed120+120 with all failures retained; dense page hit75%, hybrid80%, no query failures. Korean gap15pp documented; no claim of equivalent quality or production speed.
- [x] Fresh reviewer checked operational DB isolation and metric logic. Important: both-all-failed relative screen could pass; reproduce actual compare failure, require usable absolute completion coverage, RED→GREEN. Full suite1380 passed/1existing skipped after fix.
- Final: minor (deferred): analyzer does not bind corpus/run config automatically into input identity or validate soak identity; current six files, source hashes and settings manually verified in experiment_identity.json. Risk for future mixed experiments, no effect on this matched run.
- Ruling: Add a minimum600-request workload check to the final soak analysis so a2-hour idle process cannot pass. This strengthens the initial300-observation/two-request protocol; measurement process and recorded samples unchanged.
- [x] Review disagreements and failures, fix only evidence-backed problems, repeat affected conditions if changed. No production change or new search recipe adoption.
- [x] Complete7200.016s soak:720 requests/360 observations,0 failures/MemoryError, exit0, private median100.19→102.35MiB. Final workload gate passed, actual frozen identity matched. Temporary provider env deleted.
- [x] Run regression:1380 passed/1existing skipped. Publish raw non-user evidence and limitations; README/portfolio links prepared for GitHub.
