# General prompt release approval — implementation plan

Goal: choose immutable private prompt commits, bind/reuse matching evaluations, approve/sign/publish without promoting untested releases.

Design: extend the existing CLI, not the serving graph. Candidate JSON carries the trusted signed baseline and all eight validated immutable children. Evidence is recomputed from saved raw100+100 answers/judges, with frozen cases/rubric/settings, per-row prompt identity and hashes checked. A receipt binds candidate/evidence hashes. Signing revalidates the receipt and evidence; publication re-reads immutable children and never moves environment tags. Existing v1 evaluation is reused with no model calls. A modified template or unexercised route cannot borrow old evidence. The current paid adapter covers compact followup; other semantic changes fail closed pending a suitable suite. Production remains v1; A/B/cache flags stayOFF.

- [ ] Add failing offline tests for arbitrary release names, immutable selection, evidence reuse/mismatch/tampering, incomplete/duplicate rows and failed candidates.
- [ ] Implement pure candidate/evidence/receipt checks and CLI prepare/evaluate/publish; parameterize existing comparison generation/judging for new folders/candidates without overwriting old results.
- [ ] Reuse saved v1 evidence; reject the existing unapproved translation draft without publishing it. No paid generation needed for workflow validation.
- [ ] Run regression/frontend checks, independent review, publish no-op approved-v1 bundle, deploy code, verify public browser signed-v1 and unapproved isolation.
- [ ] Update operation cookbook/README/portfolio, preserve raw evidence, commit/push and PR.
