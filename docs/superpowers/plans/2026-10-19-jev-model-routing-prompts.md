# Jev model selection and prompt releases implementation plan

> Execute inline with superpowers:executing-plans and TDD; one fresh-context review at end.

**Goal:** Explain existing disabled task routing, compare rules/Jev model selection
on frozen100 synthetic cases each, and make primary prompts reproducibly versioned.

**Architecture:** Existing model selection stays deterministic and disabled in
production. An experimental selector uses the existing JevClient with safe
Flash fallback; it cannot authorize tools/writes or replace HITL. Prompt releases
are packaged local JSON with stable IDs/versions/content hashes; no network pull
is added. Keep the current exact baseline text and track release/system-instruction
hash in LangSmith metadata without logging user text or health values.

**Tech stack:** Existing Python, Pydantic, LangChain, httpx, Gemini/Jev clients.

## Tasks

- [x] Prompt registry RED→GREEN: version/hash validation, invalid release/path,
  corruption, exact migrated content and safe metadata.
- [x] Version the reusable DietTeam base/roles/compact, legacy parse/classify and
  RAG translation system templates. Env PROMPT_RELEASE=v1, packaged files,
  request runtime metadata; unchanged model-bound tool protocol and messages.
- [x] Experimental rules/Jev router RED→GREEN: offered choices, locked tasks,
  no-model path, low-confidence/provider fallback, shared execution budget.
- [x] Freeze100 cases; alternate each task's pair order, router-only latency,
  decisions, fallback and usage. No Gemini generation required for router-only
  comparison. Keep all failures. No end-to-end/quality/cost claim without evidence.
- [x] Full regression, review, update draft PR2, README and portfolio. No deployment
  or production Jev activation while generation/judge quotas block final validation.

## Safety and evidence constraints

- Only public synthetic questions sent to Jev; no actual user records/DB writes.
- No new dependency. Existing keys stay in ignored env; explicit eval key reading
  avoids prior inherited-key confusion. Pin Jev model version.
- >=100 attempts/condition, failures/timeouts denominator, same frozen case hash.
- Router decision gold is development annotation, not downstream answer quality.
- Preserve previous quota-blocked model experiment; don't relabel its failures.
- Local prompt releases are not a claim that LangSmith Prompt Hub was provisioned.
- Completed live 100+100 router-only attempts; Jev 57 accepted/43 low-confidence
  fallback, zero transport failures. Offline saved-decision replay matches 100/100.
- Review confirmed eight unchanged templates; reproduced stale task trace attribution
  (1 failed, 12 passed), added task to provider reuse key, focused 31 passed.
- Full backend regression: 1418 passed, one pre-existing skip, three deprecation warnings.
- No production deployment: Jev adds latency; downstream model/judge quota limitations remain.

## Ledger

- Existing codex/gemini-task-routing worktree/branch reused, draft PR2 attached.
- Official TypeSafe docs inspected: typed choices/confidence; no guarantee that
  a valid choice is correct. Existing prior Jev delegation/reranking experiments
  failed adoption criteria; model selection is a different experiment.
- Official LangSmith prompt versions/tags reviewed; use Git-local releases first
  to avoid runtime dependency on remote prompt fetches and extra network latency.
