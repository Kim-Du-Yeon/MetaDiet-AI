# Budget storage experiment — 2026-10-14

Spec: subdivide existing2.46s storage, change largest bottleneck, compare at least100 per condition including speed/quality/freshness, deploy only if improved, publish evidence.
Ruling: reuse authorized main checkout; unrelated tmp files untouched. One candidate only: pooled transaction pipeline; keep durable reservation SQL, row locks, limits and commit-before-external-effect intact.
Existing public100: SQL1053.371ms, connection/setup1046.88ms, commit353.755ms median. These are request aggregates, not single SQL latency. Queue/setup will get separate timings. Pipeline queues are not server execution timings.
Acceptance before runs:100 alternating pairs using real Gemini and real isolated PostgreSQL budget table, identical synthetic latest intake/history; storage median>=20% reduction, total median>=5% reduction, p95<=110% baseline, completion/freshness/no-write/automated quality nonregression. All failed attempts retained. No production user records touched. Concurrency/cap/rollback tests required beyond performance sample.
Docs: psycopg pipeline mode batches small statements over high latency links; errors can surface at synchronization. Pool transaction remains outside pipeline and commits only after sync. Supabase changelog read: current TLS HTTP change does not change psycopg transaction semantics.
Network sandbox DNS failure fetching changelog resolved with authorized network execution; Markdown web fetch unsupported, direct HTTPS read succeeded. Missing guessed file paths corrected via rg; no application failure.
- [x] red/green pipeline boundaries:3 failed before implementation, then9 related checks passed
- [x] isolated real DB safety and paired200 eval:200 completed/fresh, schema cleaned
- [x] blind quality200: primary97/98 completed; failed5 retried separately and all pass; source hash/index checked
- [x] whole-backend checks and review; docs ready for push; activation/deployment withheld because total speed gate failed

Review: fresh read-only reviewer found no demonstrated runtime regression; found missing timing-coverage and judge-success adoption gates. Both reproduced with failing tests then fixed (3 decision tests pass). Standalone summary now also validates asserted live safety outcomes. Cancellation recovery gets a separate real-DB check after timing runs to avoid additional DB load during measurement. Forced termination/network loss can prevent finally cleanup; generated schema identifier retained in ignored tmp for recovery.

Final backend suite967 passed/1 existing skipped, exit0. Cancellation/rollback/pool reuse passed baseline and pipeline in separate real-DB check, schema cleaned. Storage380.64→275.47ms (-27.6%), total3966.23→3940.20ms (-0.7%); total5% gate fails so do not activate candidate. Previous public2455ms is different location/route/sample and must not be compared against local275ms as an improvement.

Judge failure: one batch of5 returned GoogleAPIError code504 (indices53,139,7,185,16). Original primary records preserved; wait until primary200 completes then retry failed indices once into paired_quality_retry.json. Official Gemini troubleshooting recommends bounded delayed retries for transient5xx; API errors documents504 as deadline exceeded. Exact provider-side cause is unavailable. RuntimeWarning ClientResponse.json unawaited followed the504; no assertion that this warning caused the504. Do not change production timeouts on the basis of an evaluation-judge incident.

Retry completed5/5, all rubric fields true; hash and failed-index matching verified. No production candidate activation; publishing instrumented baseline and disabled candidate only. User's conditional deploy requirement is not met by overall speed result, so no claim of improved public deployment.
