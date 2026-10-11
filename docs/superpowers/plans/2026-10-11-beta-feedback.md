# In-App Beta Feedback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add authenticated, privacy-minimal, idempotent beta feedback submission to the account settings screen and delete feedback with the user's account.

**Architecture:** A focused `app/db/feedback.py` repository owns inserts and idempotency against a new RLS-enabled `beta_feedback` table. `POST /feedback` derives the internal user ID from the JWT and validates a small request model; a separate React card submits through the existing authenticated API client without attaching conversation or health data.

**Tech Stack:** FastAPI, Pydantic v2, psycopg/Supabase Postgres, React, Jest/Testing Library, pytest

**Spec:** `docs/superpowers/specs/2026-10-11-beta-feedback-design.md`

## Global Constraints

- Store only rating 1–5, fixed category, optional trimmed comment up to 1,000 characters, page=`settings`, client submission UUID, internal user ID and timestamps.
- Never accept `user_id` from the client or automatically attach email, conversation, meal, InBody, goal, IP, browser fingerprint or LangSmith content.
- Never log or trace the comment body; external failures return a generic structured error.
- The same `(user_id, client_submission_id)` must return one row and must not duplicate data.
- Account deletion must remove feedback through an `ON DELETE CASCADE` foreign key.
- Add no new runtime dependency.
- Preserve the current LangGraph, checkpointer, Agent, RAG and HITL paths.

## Review Focus

- A whitespace-only comment should be stored as null, while a 1,001-character comment should be rejected before DB access; Task 2 tests both.
- Two concurrent or repeated submissions with the same UUID should return one feedback ID; Tasks 1 and 2 test repository conflict behavior and endpoint status.
- A client-supplied `user_id`, page or arbitrary category should not enter the contract; Task 2 tests schema rejection/ignoring by absence from the model.
- A DB exception containing sensitive content should produce a generic 503 response and a redacted log; Task 2 tests response and captured logs.
- Account deletion after feedback creation should remove the row without adding manual deletion ordering; Tasks 1 and 5 verify the FK and live lifecycle.

---

## File Structure

- Create `backend/scripts/migrations/add_beta_feedback.sql`: table, checks, unique key, FK cascade, indexes and RLS with no browser write policy.
- Create `backend/app/db/feedback.py`: typed insert/idempotency repository and redacted storage exception.
- Modify `backend/app/api/routes/main.py`: request/response models and `POST /feedback` route only.
- Create `backend/tests/security/test_beta_feedback.py`: repository, authentication, validation, idempotency and log privacy tests.
- Modify `backend/scripts/audit_account_deletion_schema.py`: require feedback FK cascade/RLS in the schema audit.
- Modify `backend/tests/security/test_account_deletion.py`: pin deletion schema coverage without adding manual feedback delete SQL.
- Create `frontend/src/components/BetaFeedbackCard.jsx`: isolated form and state management.
- Create `frontend/src/components/BetaFeedbackCard.test.jsx`: accessible form, validation and state tests.
- Modify `frontend/src/components/Settings.jsx`: render the card outside the danger zone.
- Modify `frontend/src/components/Settings.test.jsx`: verify settings composition.
- Modify `frontend/src/api/dietApi.js`: authenticated `submitBetaFeedback(payload)`.
- Modify `frontend/src/api/dietApi.test.js`: request contract and error behavior.
- Modify `frontend/src/components/LegalNotices.jsx`: disclose beta feedback fields, purpose and account-deletion path.
- Modify `frontend/src/components/LegalNotices.test.jsx`: pin the disclosure.
- Modify `frontend/src/App.css`: card/form responsive and focus styles using existing settings tokens.
- Create `backend/scripts/check_beta_feedback.py`: synthetic submit, duplicate replay and account-delete lifecycle check with cleanup.
- Modify `backend/tests/unit/test_operational_script_paths.py`: lifecycle checker path, timeout, cleanup and redaction contract.
- Modify `BETA_RELEASE_CHECKLIST.md`, `EVALUATION.md`, and `PORTFOLIO_RESULTS.md`: record scope, commands and measured outcome after verification.

### Task 1: Feedback Schema and Repository

**Files:**
- Create: `backend/scripts/migrations/add_beta_feedback.sql`
- Create: `backend/app/db/feedback.py`
- Create: `backend/tests/security/test_beta_feedback.py`
- Modify: `backend/scripts/audit_account_deletion_schema.py`

**Interfaces:**
- Consumes: existing `app.db.proposals.connection()` async transaction context.
- Produces: `FeedbackInput` dataclass and `FeedbackRepository.create(user_id: str, submission: FeedbackInput) -> tuple[dict, bool]`, where bool is `created`.

- [ ] **Step 1: Write failing repository and migration-contract tests**

Add tests named `test_feedback_insert_uses_authenticated_user_and_fixed_page`, `test_feedback_submission_is_idempotent_per_user`, `test_feedback_migration_has_checks_rls_and_user_cascade`, and `test_feedback_storage_error_redacts_comment`. Assert SQL parameters exclude email/health/chat data, conflict replay returns the same ID with `created=False`, and the migration contains rating/category/comment checks, unique `(user_id, client_submission_id)`, RLS and `ON DELETE CASCADE`.

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `cd backend; venv\Scripts\python.exe -m pytest tests/security/test_beta_feedback.py -v --basetemp=.pytest-feedback-schema-red`

Expected: FAIL because the migration and `app.db.feedback` do not exist.

- [ ] **Step 3: Add the migration**

Create `add_beta_feedback.sql` with UUID PK, `users(id)` cascade FK, rating 1–5, the five fixed categories, nullable 1,000-character comment, fixed `settings` page, per-user submission uniqueness, created timestamp and RLS. Do not add a browser insert policy; service-role/API insertion is the only write path.

- [ ] **Step 4: Implement the repository**

Implement `FeedbackInput` and `FeedbackRepository.create(...)`. Use one `INSERT ... ON CONFLICT ... DO NOTHING RETURNING` followed by a same-user/same-submission lookup on conflict. Raise `FeedbackStorageUnavailable` without copying the underlying exception text into its public message or logs.

- [ ] **Step 5: Extend the account schema audit**

Make `audit_account_deletion_schema.py` fail closed when the table, RLS, FK cascade or unique idempotency constraint is missing.

- [ ] **Step 6: Run focused tests and verify GREEN**

Run: `cd backend; venv\Scripts\python.exe -m pytest tests/security/test_beta_feedback.py -v --basetemp=.pytest-feedback-schema-green`

Expected: all Task 1 tests PASS.

- [ ] **Step 7: Commit Task 1**

```powershell
git add backend/scripts/migrations/add_beta_feedback.sql backend/app/db/feedback.py backend/tests/security/test_beta_feedback.py backend/scripts/audit_account_deletion_schema.py
git commit -m "feat: add secure beta feedback storage"
```

### Task 2: Authenticated Feedback API

**Files:**
- Modify: `backend/app/api/routes/main.py`
- Modify: `backend/tests/security/test_beta_feedback.py`

**Interfaces:**
- Consumes: `FeedbackRepository.create(user_id, FeedbackInput)` from Task 1 and `get_current_user`.
- Produces: `POST /feedback` accepting `FeedbackRequest` and returning `FeedbackResponse` with `id`, `status`, and `created`.

- [ ] **Step 1: Write failing endpoint tests**

Add `test_feedback_requires_authentication`, `test_feedback_uses_internal_user_not_request_identity`, `test_feedback_validates_rating_category_and_comment`, `test_feedback_trims_blank_comment_to_none`, `test_feedback_replay_returns_existing_id`, and `test_feedback_db_failure_returns_redacted_503`. Include explicit assertions that `user_id` and `page` are not request fields and sensitive injected exception/comment text is absent from response and captured logs.

- [ ] **Step 2: Run endpoint tests and verify RED**

Run: `cd backend; venv\Scripts\python.exe -m pytest tests/security/test_beta_feedback.py -v --basetemp=.pytest-feedback-api-red`

Expected: FAIL with missing route/models.

- [ ] **Step 3: Add strict request and response models**

Add `FeedbackRequest` using strict rating bounds, `Literal` category values, a UUID `client_submission_id`, and a pre/post validator that trims comment and converts blank to null while rejecting more than 1,000 characters. Forbid extra fields so `user_id` and `page` fail validation.

- [ ] **Step 4: Add `POST /feedback`**

Derive `current_user` with `Depends(get_current_user)`, construct fixed page=`settings`, call the repository through `asyncio`, return 201 for create and 200 for replay, and translate `FeedbackStorageUnavailable` to generic 503. Log only event name, feedback ID/category/rating, created flag and error type.

- [ ] **Step 5: Run security and API tests**

Run: `cd backend; venv\Scripts\python.exe -m pytest tests/security/test_beta_feedback.py tests/security/test_log_privacy.py -v --basetemp=.pytest-feedback-api-green`

Expected: PASS with no comment text in captured logs.

- [ ] **Step 6: Commit Task 2**

```powershell
git add backend/app/api/routes/main.py backend/tests/security/test_beta_feedback.py
git commit -m "feat: expose authenticated beta feedback api"
```

### Task 3: API Client and Accessible Feedback Card

**Files:**
- Modify: `frontend/src/api/dietApi.js`
- Modify: `frontend/src/api/dietApi.test.js`
- Create: `frontend/src/components/BetaFeedbackCard.jsx`
- Create: `frontend/src/components/BetaFeedbackCard.test.jsx`
- Modify: `frontend/src/components/Settings.jsx`
- Modify: `frontend/src/components/Settings.test.jsx`
- Modify: `frontend/src/App.css`

**Interfaces:**
- Consumes: `POST /feedback` from Task 2.
- Produces: `submitBetaFeedback({rating, category, comment, client_submission_id}) -> Promise<FeedbackResponse>` and `<BetaFeedbackCard />`.

- [ ] **Step 1: Write failing API client tests**

Add tests asserting bearer auth, exact JSON fields, POST URL, parsed success response and generic retryable error without losing the form payload.

- [ ] **Step 2: Implement `submitBetaFeedback` and make client tests pass**

Use existing `BASE_URL`, `authHeaders` and JSON error conventions. Do not add automatic retries.

Run: `cd frontend; npm.cmd test -- --runInBand --watchAll=false src/api/dietApi.test.js`

Expected: PASS.

- [ ] **Step 3: Write failing card tests**

Test the accessible rating radio group, category labels, 1,000-character counter, required inputs, duplicate-click lock, success reset, failure input retention, privacy copy and stable UUID reuse on a failed retry.

- [ ] **Step 4: Implement `BetaFeedbackCard`**

Keep form state inside the component. Generate one submission UUID on first submit, reuse it until success, and reset it after success. Render plain text only and use `role=status` for the result.

- [ ] **Step 5: Compose the card into Settings and add responsive styles**

Place it between service policy and danger zone. Reuse `.settings-card`, existing tokens and focus styles; do not modify account deletion state.

- [ ] **Step 6: Run focused frontend tests**

Run: `cd frontend; npm.cmd test -- --runInBand --watchAll=false src/api/dietApi.test.js src/components/BetaFeedbackCard.test.jsx src/components/Settings.test.jsx`

Expected: PASS.

- [ ] **Step 7: Commit Task 3**

```powershell
git add frontend/src/api/dietApi.js frontend/src/api/dietApi.test.js frontend/src/components/BetaFeedbackCard.jsx frontend/src/components/BetaFeedbackCard.test.jsx frontend/src/components/Settings.jsx frontend/src/components/Settings.test.jsx frontend/src/App.css
git commit -m "feat: add in-app beta feedback form"
```

### Task 4: Privacy Notice and Account Deletion Contract

**Files:**
- Modify: `frontend/src/components/LegalNotices.jsx`
- Modify: `frontend/src/components/LegalNotices.test.jsx`
- Modify: `backend/tests/security/test_account_deletion.py`

**Interfaces:**
- Consumes: Task 1 FK cascade and Task 3 settings card.
- Produces: user-facing disclosure and regression proof that no manual feedback deletion query is required before deleting `users`.

- [ ] **Step 1: Write failing disclosure and deletion-contract tests**

Assert the privacy notice names rating/category/comment, improvement purpose, no automatic health/chat attachment, and deletion with the account. Assert account deletion still deletes the user after checkpoints without issuing an out-of-transaction/manual `delete from beta_feedback`.

- [ ] **Step 2: Run the focused tests and verify RED**

Run backend and frontend focused tests; expect disclosure test failure before copy changes.

- [ ] **Step 3: Update legal copy**

Add the exact feedback fields, purpose and deletion behavior without claiming a retention duration that is not implemented.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `cd backend; venv\Scripts\python.exe -m pytest tests/security/test_account_deletion.py tests/security/test_beta_feedback.py -v --basetemp=.pytest-feedback-delete`

Run: `cd frontend; npm.cmd test -- --runInBand --watchAll=false src/components/LegalNotices.test.jsx src/components/Settings.test.jsx`

Expected: all PASS.

- [ ] **Step 5: Commit Task 4**

```powershell
git add frontend/src/components/LegalNotices.jsx frontend/src/components/LegalNotices.test.jsx backend/tests/security/test_account_deletion.py
git commit -m "docs: disclose beta feedback handling"
```

### Task 5: Migration, Live Lifecycle Verification and Portfolio Evidence

**Files:**
- Create: `backend/scripts/check_beta_feedback.py`
- Modify: `backend/tests/unit/test_operational_script_paths.py`
- Modify: `BETA_RELEASE_CHECKLIST.md`
- Modify: `EVALUATION.md`
- Modify: `PORTFOLIO_RESULTS.md`

**Interfaces:**
- Consumes: deployed migration, API and UI from Tasks 1–4.
- Produces: git-ignored JSON artifact with create/replay/delete counts and redacted timings; committed summary documents.

- [ ] **Step 1: Write the lifecycle checker with a dry/testable core**

The script creates a synthetic Auth user, completes the minimum internal profile setup, submits one feedback payload twice with the same UUID, asserts one row, deletes the account through the public API, asserts zero feedback rows, and removes residual synthetic data in `finally`. It must never print credentials, tokens or comment content.

- [ ] **Step 2: Add script-path and redaction tests**

Extend the operational script tests to assert project-relative paths, bounded timeouts, synthetic-only identifiers, cleanup in `finally`, and redacted artifact fields.

- [ ] **Step 3: Apply the additive migration and verify schema**

Apply `add_beta_feedback.sql` to the configured Supabase project using the established migration channel. Run `backend/scripts/audit_account_deletion_schema.py` and stop on any RLS/FK/constraint mismatch.

- [ ] **Step 4: Run full local verification**

Run: `cd backend; venv\Scripts\python.exe -m pytest --basetemp=.pytest-feedback-final`

Run: `cd frontend; npm.cmd test -- --runInBand --watchAll=false`

Run: `cd frontend; npm.cmd run build`

Expected: all tests pass and production build succeeds.

- [ ] **Step 5: Deploy and run synthetic public lifecycle check**

Push the reviewed commits, wait for both Render services, verify `/health`, then run `check_beta_feedback.py --base-url https://metadiet-api.onrender.com`. Inspect Render logs and LangSmith only for metadata; comment text must not appear.

- [ ] **Step 6: Diagnose failures before retrying once**

Classify failures as migration/schema, auth/RLS, API validation, Render deployment, Supabase availability or network timeout. Preserve the redacted first failure artifact, fix the identified cause, and retry only the failed stage once. If unresolved, leave the feature disabled/unadvertised and document the exact redacted error.

- [ ] **Step 7: Record results and limitations**

Update the three portfolio/release documents with test totals, lifecycle counts, p50/p95 only when sample size supports them, error details and the no-automatic-health-data boundary. Do not change the existing `beta-v1.0.0` tag; this feature is a post-beta follow-up until separately released.

- [ ] **Step 8: Commit Task 5**

```powershell
git add backend/scripts/check_beta_feedback.py backend/tests BETA_RELEASE_CHECKLIST.md EVALUATION.md PORTFOLIO_RESULTS.md
git commit -m "test: verify beta feedback lifecycle"
```
