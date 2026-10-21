# Prompt control and cache implementation plan

Goal: remotely controlled immutable prompt bundles, safe experiments and measured Gemini caching.
Spec: ../specs/2026-10-21-prompt-control-cache-design.md
Architecture: existing get_prompt facade plus atomic release manager/ContextVar pin,private raw-manifest adapter,code-owned contracts; optional cache adapter leaves writes and graph routing intact.
Execution: inline, as delegated by user. No subagents. Worktree from b5021845; existing analysis branch unchanged.

- [ ]1 Contract/signed-bundle/request pin modules and failure-first tests. Preserve existing local loader interface.
- [ ]2 Raw LangSmith adapter/publisher,LKG manager/config/admin refresh; mock outage/rollback/partial bundle/invalid signature/restart/concurrency tests.
- [ ]3 Integrate request/HITL checkpoints and all8 dynamic template callers; actual per-invocation trace metadata; no stale provider release. Test owner/approval loop invariants and existing regressions.
- [ ]4 Deterministic disabled A/B policy,1000synthetic user allocation/experiment isolation/rollback tests and audit.
- [ ]5 Cache eligibility/cost/key/TTL/coalescing/cleanup/fallback framework and private invalidation,implicit usage telemetry. Mock failure and privacy tests before provider calls.
- [ ]6 Private LangSmith publish/freeze v1/v2,quota/minimum-token probe and frozen100pair prompt experiment; grade saved answers only; sign only passing releases.
- [ ]7 Freeze winner;RAG and multiturn cache experiments separately>=100/condition where eligible,record first/reuse/TTFT/storage/quality/latest synthetic records. Never pad to meet minimum.
- [ ]8 Full backend/frontend required checks,whole-change review,limited deployment,real browser/LangSmith UI staging/production/rollback verification. Actual-user A/B stays off.
- [ ]9 Evidence/status matrix,runbooks,portfolio links,commit/push/PR. Mark blocked/inapplicable accurately and preserve resumes.

Review focus: lost per-request ContextVar across detached streaming tasks; persisted HITL snapshot tampering or missing archived release; remote LC object deserialization; stale provider metadata; deletion racing cache create; cache ref fallback duplicating billed model call; comparison overclaims when cache never eligible.
