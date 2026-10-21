# Prompt control operating notes (work in progress)

## Immutable release, mutable environment pointer

Eight private template repositories are controlled through a ninth private `metadiet-release-manifest` repository. A release pins full child commit IDs, SHA-256, required variables and code-owned output contract IDs. Only an Ed25519-approved manifest is executable. Editing a child in the LangSmith UI creates a draft: changing its staging/production tag alone never changes runtime. Assemble, evaluate and sign a new complete release, then promote that release-manifest commit. This extra approval boundary deliberately prevents untested combinations and UI edits from bypassing code safety.

Refresh is asynchronous every60 seconds (`PROMPT_REFRESH_SECONDS`,minimum10). An administrator can POST `/admin/prompts/refresh` or use the administrator prompt panel. The next new request uses the successfully validated snapshot. `/admin/prompts` lists actual child commits and hashes; no prompt bodies, signer key, user IDs or health records are added to this response.

An in-flight request uses a ContextVar snapshot. A pending HITL checkpoint stores its complete bounded generic snapshot, so confirmation retains the old release even after promotion/restart. Subsequent ordinary requests can use the new release. User A/B is disabled unless BOTH `PROMPT_AB_ENABLED` and `PROMPT_AB_LIVE_APPROVED` are enabled with an approved experiment manifest; do not enable these without separate human approval. Deterministic HMAC assignment is experiment-specific and preserves user/conversation consistency. Synthetic allocation tests are not live-user A/B results.

## Failure and restart

Fetch timeout8 seconds; each LangSmith request timeout2 seconds and no retry. Fetch all8 children, validate contracts/signature/hashes, atomically persist, then swap. Any failure keeps the last good snapshot. `PROMPT_LAST_GOOD_PATH` should point to persistent storage where available. Render ephemeral `/tmp` is NOT guaranteed across replacement/redeploy: preserve packaged local v1 as first boot fallback; remote production is revalidated on refresh. Pending durable checkpoints still contain their old snapshot, but old approval public keys must remain trusted until those flows finish. No claim of cross-Pod instantaneous refresh is made.

Private signer: ignored `backend/.env.prompt-signer`; public verifier: `backend/app/prompts/approval-public-key.json`. Do not upload the private file to LangSmith, GitHub or Render. Do not regenerate the signing key casually. Rotating keys needs an explicit migration of trust for existing HITL pins.

## Caching decision

Ordinary GenerateContent calls already support implicit caching. A zero observed cache-read count does NOT mean caching was disabled. The new model usage event reports `cached_input_tokens` and `reasoning_output_tokens`; raw provider usage is retained in synthetic experiment artifacts.

Official minimum for Gemini3.8 Flash explicit caching is4096 tokens. Measured static prefixes: team base+meal740, compact252; a short synthetic history493 is only a sample, NOT maximum production history. Current history bound remains10 messages×2000 characters. Never pad prompts or lengthen history to qualify. Current records, current goals/questions and fresh search results remain dynamic.

`CachePool` implements TTL, release/model/exact-prefix/scope/revision keys, same-process creation coalescing, negative creation cache, expiry, race-safe invalidation and deletion retry until TTL. `invoke_cached` retries normal generation once only for definitive missing/invalid cached-reference errors; ambiguous timeout/other failures do not cause duplicate generation. The provider adapter uses the existing google-genai client. This is infrastructure, not evidence of production savings.

Explicit/private cache feature flags remain OFF. Private cache has no production call site: no personal conversations are uploaded by this implementation. A future adoption must connect mutation/account-deletion hooks and a durable deletion queue/shared lease before enabling it across workers. The current in-memory pool is single-process, and provider TTL is the cleanup backstop after a crash. This limitation is intentional and must not be presented as deployed private-cache lifecycle coverage.

Separate these concepts: Python client reuse saves connection/setup work; local pickle/BM25 caches support retrieval; checkpoint saves workflow state; search-result cache avoids retrieval; Gemini input caching discounts reused model input. They are not interchangeable.

## Official references checked2026-10-21

- https://docs.langchain.com/langsmith/manage-prompts — commit diff, environment promotion, rollback UI.
- https://docs.langchain.com/langsmith/manage-prompts-programmatically — immutable commit pulls/private repositories.
- https://ai.google.dev/gemini-api/docs/generate-content/caching?hl=en — implicit/explicit support, minimum and TTL.
- https://ai.google.dev/gemini-api/docs/pricing — Flash3.8 $0.75 input/$3.75 output/$0.075 cache-read per1M; storage$0.50 per1M-token-hour, at the checked date. Rates can change.

Cost calculations are usage×published rates, not verified invoices. The existing spend ledger is preserved; this task's incremental ceiling is$12 (estimated$4–8). Unknown usage/fatal account capacity/budget exhaustion stop further billable work while preserving resume state. Individual quality failures remain in the denominator.

Refresh optimization: when the release-manifest head commit is unchanged, reuse the already validated child bundle instead of re-reading all8 templates. A changed manifest always triggers complete child readback. This reduces routine LangSmith API traffic without trusting independent mutable child tags.
