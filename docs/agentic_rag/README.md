# Bounded Agentic RAG (experimental)

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
