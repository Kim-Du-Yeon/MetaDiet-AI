# Evidence preservation follow-up

User authorized recovery, fix and matched100/condition revalidation. Preserve old valid negative and positive Pro grades after checking input/file hashes; retry only missing/invalid grades. No regeneration of historical answers.

Root cause: each retrieval replaced result.docs; final source evidence came only from rewritten query. Fix: keep score-qualified initial documents, deduplicate new score-qualified hits, original first; cap8 documents and6000 characters shared between assessor and answer. Never import low-score documents. Same controller prompt,2 rounds/35sec/shared call budgets; defaultOFF.

Frozen validation: copy exact prior100 attempts/40 development questions. Compare frozen safety-tested v1 and v2,100 each; same dense recipe, namespace, models/QA prompt; pair order alternates. Keep serving failures/timeouts denominator. Pro joint blinded A/B rubric100 requests grades200 outputs to conserve250-RPD quota, with order balanced. Report judge method separately from old single-answer rubric and do not claim independent human evaluation. Costs with missing embedding usage remain incomplete. Existing rollout gate unchanged; no automatic adoption for page support alone.

Steps: failing regression; minimal retention fix; recover old judging in parallel with new serving comparison; joint judge; full regression/review; only deploy on passed gate; publish truthful outcomes and limits.
