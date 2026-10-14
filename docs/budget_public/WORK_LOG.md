# Public durable-budget pipeline comparison

## Predeclared protocol (2026-10-14)

- Same public API, deployed application commit `f60c040bb1a973db4e8ecc18196ecf52920d73c8`.
- Baseline: `BUDGET_PIPELINE` absent/default false. Candidate: true via Render environment, same code.
- 100 serial requests per condition, same ordered 4 follow-up questions × 5 synthetic database states × 5 repetitions.
- A disposable synthetic account only. Database state is seeded outside the timed request. This is not real-user traffic or an end-to-end test of the record-edit UI.
- Check current intake and target via public session restore before every request. Supply deliberately stale conversation history (300 kcal / 2200 kcal). Verify the answer against current database values.
- Compare meal and strategy rows before/after every coaching request: no implicit writes allowed.
- The prior-day-only case verifies date filtering; it does not simulate a real midnight transition.
- All attempts are retained, including errors. A different build or missing/mismatched pipeline timing stops collection and preserves the evidence.
- Serial baseline then candidate is susceptible to time/provider load drift. Warm running service; these results do not measure cold starts or concurrent load.
- Quality: same blind five-part model rubric on all 100 answers per condition. Judge failures remain in the primary denominator; bounded retries are supplementary evidence.

## Adoption gates

Budget-storage median improves at least 20%; total-response median improves at least 5%; total p95 does not worsen more than 10%. Both conditions require 100 complete timings and quality reviews, 100 completed/fresh/no-write requests, no unexpected proposals, and no quality-rubric regression. Otherwise restore false and report the result without claiming deployment improvement.

Existing transaction concurrency, restart-cap and rollback evidence is in `../budget_pipeline/`. No runtime code change is needed for this experiment. The flag changes transport batching only; reservation commit precedes a model call.

## Execution

- Confirmed Render API is Live on the specified commit; no BUDGET_PIPELINE variable was present.
- Created an isolated synthetic application account; credentials are stored in a git-ignored env file.
- Started baseline public requests. No source push or deployment during baseline collection.
- Evaluator review found inherited environment identity could be stale. Credentials now load explicitly from the fixture file and the auth response must match that fixture before any mutation. The already-running baseline identity was separately verified against Supabase Auth; it matched the disposable account.
- Review also strengthened same-judge, complete timing, finite timing and failed-attempt handling. Baseline process began before these evaluator-only guards changed; its request payloads, measured code and ordering remain identical. No failed baseline request has been observed at this checkpoint.
- Initial whole-backend regression: 972 passed, 1 pre-existing skipped, 3 deprecation warnings. Review guard tests subsequently passed 9/9; final verification follows the last edit.

## Official references

- [Psycopg pipeline mode](https://www.psycopg.org/psycopg3/docs/advanced/pipeline.html): fewer network round trips for short queries; explicit synchronization/commit preserves transaction boundaries.
- [Render environment configuration](https://render.com/docs/configure-environment-variables): runtime configuration must be deployed before measurement.

## Baseline failure investigation

Request index 46 (47th attempt) returned an SSE error after 34.44 seconds. The original evaluator then asserted missing build metadata as a mismatch; this was an evaluator error, not evidence that a different build ran. The row was retained and collection resumed at index 47 with append-only validation.

Render application logs at 2026-10-14 09:32:57 show `GoogleAPIError`; health checks remained 200. The matching LangSmith trace in the deployed `metadiet-beta` project confirms `504 DEADLINE_EXCEEDED` in the Gemini call. `failure_trace.json` contains only exception/code markers and synthetic trace IDs, not raw prompts or secrets. The first lookup used the local project setting and found no matches; a successful public trace identified the correct deployed project.

[Google's troubleshooting guide](https://ai.google.dev/gemini-api/docs/troubleshooting) recommends bounded backoff for transient 5xx errors; [API errors](https://ai.google.dev/gemini-api/docs/api-errors) identifies 504 as deadline exceeded. Existing provider timeout/retry settings were kept identical for the comparison rather than changing a second variable mid-experiment. Subsequent requests resumed successfully. The exact provider-side reason for this deadline is not observable in the available logs; no DB/pipeline fault is claimed.

The primary failure remains in speed, completion, freshness and quality denominators. It is not silently replaced by a successful retry. The strict complete-evidence adoption gate therefore cannot pass for this primary run, even if completed-request speed improves.

After 61 attempts, a preparation-only session restore omitted stats; a subsequent restore returned HTTP 500. Render logs at 09:37:49 identify `httpx.ReadError: [Errno 11] Resource temporarily unavailable`. `_public_stats` can omit unavailable stats, so the evaluator must never treat absence as zero. The evaluator now retries only missing stats/transient 500/502/503/504 reads, at most three attempts with backoff; a wrong numeric value or 401 still stops immediately. Resuming preserved all 61 measured rows. The next timed request completed with the correct current values. This does not prove the underlying network/resource cause is permanently fixed.

[HTTPX exceptions](https://www.python-httpx.org/exceptions/) classifies ReadError as a network receive failure. [HTTPX transports](https://www.python-httpx.org/advanced/transports/) explains that transport connection retries do not cover read failures; those require separate bounded retry handling. The runtime code was not changed during the A/B comparison. `render-errors.png` records the observed error types.

## Candidate deployment

- Baseline completed 100 attempts (99 completed, 1 Gemini 504); all 99 completed answers reflected current values, all 100 left meal/strategy rows unchanged.
- Baseline quality review completed 100/100 without judge execution failures.
- Saved only `BUDGET_PIPELINE=true` through Render's Save and deploy option. The UI initially composed incorrect characters due to keyboard input method; values were corrected and verified as exact ASCII before saving. No malformed setting was deployed.
- Render deployment `dep-db7d1pq5b2lc73ffkkag` succeeded on the same `f60c040` commit.
- `after_probe.json` is a separate warm-up and mode verification, not part of the 100. It returned current values, no writes and `budget_setup_enqueue` timing. Candidate collection started only after baseline judging ended.
- Full backend verification after evaluator fixes: 977 passed, 1 pre-existing skipped, 3 deprecation warnings.
- [Render scheduled maintenance](https://status.render.com/incidents/bwd9ycdxqps4) overlaps the candidate window (2026-10-14 01:00–02:00 UTC / 10:00–11:00 KST). The official notice states deployed services/databases are uninterrupted, but Dashboard/Platform API/configuration/deployment may be unavailable. This is recorded as an operational limitation, not asserted as the cause of observed latency or earlier errors.

## Completion and rollback

- Candidate: 100/100 completed, fresh, and meal/strategy unchanged; no unexpected proposals. Baseline: 99/100 completed/fresh, 100/100 unchanged.
- Storage median 2497.04→1800.26ms; completed response median 8235.73→7806.99ms. The speed thresholds pass, but the baseline failure prevents the strict complete-evidence gate passing. Do not relabel this as a successful permanent rollout.
- `BUDGET_PIPELINE=false` restored through Render Save and deploy; deployment `dep-db7dcqbbc2fs73epg150` became Live. The management operation succeeded despite the scheduled-maintenance notice.
- `before_probe.json` is a separate post-rollback functional probe: completed, fresh, no writes, old `budget_setup` timing present and pipeline marker absent. It is excluded from the original baseline 100.
- The screenshot `render-restored.png` shows false; other environment values remain masked. The setting was read back before saving and verified again in the actual response.
- Disposable account cleanup completed through authenticated `/users/me`; users row absence confirmed, checkpoint/domain cleanup follows the application's account-deletion path. Ignored credential file removed. See `cleanup.json`.
- Both quality runs completed 100/100 with the same judge. All five rubric scores are baseline 99/100, candidate 100/100; the blank failed answer remains a failure. Summary validates source hashes, order, expected state, builds, flags and judge identity. Final `adopt=false` reflects the complete-evidence gate; speed/quality nonregression gates passed.

- Final review hardened evidence persistence: save each timed attempt before untimed postflight reads; read failures remain conservative unverified rows instead of disappearing on resume. Regression injected a read failure and verified the row survives. No observed row in this public dataset was affected. Final full regression: 977 passed, 1 pre-existing skipped.
