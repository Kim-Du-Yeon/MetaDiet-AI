# Work ledger — implementation, measured comparisons, operating boundaries

Started2026-10-21; completed evidence collected across2026-10-22 KST. Baseb5021845; isolated native worktree `codex/prompt-control-cache`; stacked PR#4 on PR#3. Existing changes and prior evaluation spend preserved.

## Implemented and publicly verified

Eight private immutable template repositories plus one signed atomic manifest. Full child commits/hashes/required variables/output contracts are validated without remote Runnable/model deserialization. ContextVar request pins and complete generic HITL checkpoint pins preserve a release through confirmation. Refresh60seconds plus administrator force, last-good persistence, localv1 first boot fallback. Mutable environment tags select a signed release; independently moving child tags cannot introduce untested combinations.

Actual LangSmith UI: private8repositories; child translation edit/commit remains unapproved draft; signed v1 staging/production → identical-content control drill → rollbackv1. Public administrator readbacks show actual8commits. Native same-conversation traces confirm the pending proposal's old drill release survives rollback/reload/cancel; next ordinary request usesv1. Real browser ordinary coaching, followup and natural RAG source panel verified. Test10g proposal was cancelled without saving or touching actual meals. Render API/static build71975d71, remote prompt switchON; actual A/B and explicit/private cachingOFF. Specific-commit deployment changes Render autodeploy toOFF; recorded, no subscription/plan change.

## Prompt experiment

100actual DietTeam synthetic generations per v1/v2, independent Pro100paired grades, fixed model/data/order/settings. Both100/100 pass source-fact/freshness/no-write rubric. v2 misses preregistered target-error-reduction gate (ceiling effect), so retainv1. No live-userA/B. HMAC allocation1000synthetic identities A482/B518; consistency/isolation/config pin/disable/rollback tests.

Saved200results were imported to two LangSmith experiments without regeneration. Original measured_ms/usage are metadata; native import latency/cost are NOT original model latency/cost. Public browser native traces and new cache experiment native traces are separate. New metadata/evidence excludes account/thread identifiers, personal records and credentials.

## Cache correction and actual followup

Initial applicability incorrectly borrowed the implicit4096token table. Explicit admission probes returned model-specific1024minimum for tested Flash/Pro/Lite. Initial artifact preserved and superseded; official implicit/explicit distinction documented. Corrected natural RAG100prefixes all eligible with40reused exact contexts; real100paired boundary comparison follows. Bounded synthetic history100prefixes allunique: no reuse economics, no paid private-cache generation comparison. No padding/history expansion. Raw results, independent grades, first/reuse/TTFT/failure/cost summary retained under cache-rag.

Two explicit requests timed out with anomalous elapsed1264/352seconds despite65second asyncio timeout; root cause not established (host/event-loop pause only a possibility). Failure remains in denominator, elapsed retained, unknown cost retains reservation, no duplicate generation. This limits causal latency conclusions. Windows WinError5 interrupted write-ahead snapshot before the next API call; completed keys reused after bounded atomic-file replacement retry was tested. Expired cache deletion404 is successful cleanup. Interim usage cannot refund an interrupted stream. Review also separated successful-counterpart grading from failed generation; saved completed answer is judged independently without regeneration.

## Remaining boundaries

No personal explicit cache production call site, mutation/account-deletion hooks, distributed creation lease or durable deletion queue. Single-process library and100synthetic dynamic-input/isolation checks do not claim deployed private lifecycle coverage. Provider TTL300seconds is crash cleanup backstop. Public cache performance is a grouped-prefix synthetic generation experiment, not actual traffic/service-wide latency or clinical outcome. Final metrics/costs are linked from README and JSON; invoice not verified. Existing budget ledger and incremental12USD ceiling remain intact.
