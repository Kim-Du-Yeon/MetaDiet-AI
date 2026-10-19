# Prompt v1 routing availability and restart validation

Spec: user requests quota check, fixed-v1 >=100 attempts per condition, safe
rollback verification, and conditional limited production adoption.

- [x] Reuse existing feature branch; read architecture/evaluation and prior failures.
- [x] Minimal standard/simple/judge availability preflight; no real user data.
- [x] Pin benchmark v1 bundle and reject drift before any generation.
- [x] Verify separate-process v1 → synthetic v2 → v1 restart; invalid release blocked.
- [x] Regression, fresh review, GitHub/portfolio evidence.
- [ ] Live100+100 and judge, conditional deployment: blocked by preflight quota.

Ruling: do not send 200 predictably rejected requests after daily-limit preflight.
Preserve prior200 attempts separately; today's3 probes are availability checks,
not a new100-case speed/quality comparison. No hidden judge/model substitution.
Ruling: v2 is a temporary test fixture, never a packaged production release.
Production still has v1 only; no environment or production record changes.

Preflight: Flash429 daily FreeTier limit20, retry79412s; Lite200;
Pro429 FreeTier daily/minute/token metrics, retry79411s. Google docs confirm
project-level quota, not key-level. No billing/quota change attempted.
Initial local probe failed because relative dotenv was resolved from repository
root; explicit backend env loading fixed it. Do not persist exception input values.

v1 pin test: missing helper RED → fixed guard GREEN. Restart test: missing module
RED; first implementation's wrong BASE_PROMPT import failed, corrected to actual
BASE_INSTRUCTION; fresh-process fixture transition restored hashes, v999 rejected.
Focused restart/pin8 passed. Frozen100 cases exactly match prior case snapshot.
Fresh reviewer found no blocking defects; rollback scope excludes Render and
all composed runtime modifiers. No new100-pair performance or production claim.
Backend full regression1420 passed, pre-existing1 skipped,3 warnings. Credential
scan of14 staged files:0 real secret matches. GitHub evidence stays draft; no main
merge or deployment because the conditional quality/performance gate is not met.
