# Single-bottleneck experiment

User authorization: analyze existing100, improve one bottleneck, compare100 per condition speed/quality/freshness, deploy only if improved, publish evidence.

Ruling: use existing authorized main checkout; unrelated tmp files untouched. No runtime deployment until acceptance gate passes.
Existing after100 medians: model_meal4444ms(n96), budget_storage2455ms(n100), db_read490ms(n95), terminal_checkpoint217ms(n100). Nested timing values must not be added as independent stages.

Candidate: compact instruction only for fresh read-only follow-up coaching. Model, low reasoning, tools, history, latest-context reads, evidence validation and write boundaries unchanged. First recommendations and supervisor retain original prompts.
Official Gemini3.8 documentation rejects minimal thinking, so no unsupported reasoning experiment.

Acceptance fixed before evaluation: 100 alternating pairs; candidate median end-to-end team time at least10% lower, p95 no more than10% worse, completion/freshness/no-write counts no lower, blinded quality counts no lower (judge failures retained). No claim about public latency from local-model timings.
Frozen cases: same four follow-up questions × five fresh DB states × five repetitions used in previous native experiment. Actual Gemini model, synthetic DB; stale history300/2200. Both conditions rerun now rather than use historical timing as matched control.

- [x] final regression: backend961 passed/1 existing skipped, exit0
- [x] 100 paired real-model baseline/candidate, all200 completed
- [x] blinded quality of all200: each of5 rubrics100/100 per condition, no judge failures
- [x] decision and whole-change review: median4322.90→4412.73ms fails10% improvement gate; do not activate/deploy candidate behavior
- [x] GitHub/portfolio report prepared with raw evidence and failed hypothesis

Latest-context and no-write checks both100/100 per condition. No production DB migration or runtime activation is needed. Default flag remainsFalse; publishing the disabled experiment does not claim a public performance improvement.

Fresh-context review found no blocking safety issue. Limits retained:20 synthetic combinations repeated5 times, not100 distinct users; new_day is fake current DB state, not an observed date rollover. Production route and fresh-context loading unchanged.
The initial baseline call includes cold local provider initialization; retained rather than discarded. Alternating order reduces but does not eliminate provider/time confounds.
Official references: https://ai.google.dev/gemini-api/docs/latest-model (3.8 has low/medium/high, rejects minimal); https://ai.google.dev/gemini-api/docs/long-context (context/latency); https://ai.google.dev/gemini-api/docs/generate-content/thinking (avoid small output caps that truncate answers).
