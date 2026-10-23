# Prompt control operating notes

## Immutable release, mutable environment pointer

Eight private template repositories are controlled through a ninth private `metadiet-release-manifest` repository. A release pins full child commit IDs, SHA-256, required variables and code-owned output contract IDs. Only an Ed25519-approved manifest is executable. Editing a child in the LangSmith UI creates a draft: changing its staging/production tag alone never changes runtime. Assemble, evaluate and sign a new complete release, then promote that release-manifest commit. This extra approval boundary deliberately prevents untested combinations and UI edits from bypassing code safety.

Refresh is asynchronous every60 seconds (`PROMPT_REFRESH_SECONDS`,minimum10). An administrator can POST `/admin/prompts/refresh` or use the administrator prompt panel. The next new request uses the successfully validated snapshot. `/admin/prompts` lists actual child commits and hashes; no prompt bodies, signer key, user IDs or health records are added to this response.

An in-flight request uses a ContextVar snapshot. A pending HITL checkpoint stores its complete bounded generic snapshot, so confirmation retains the old release even after promotion/restart. Subsequent ordinary requests can use the new release. User A/B is disabled unless BOTH `PROMPT_AB_ENABLED` and `PROMPT_AB_LIVE_APPROVED` are enabled with an approved experiment manifest; do not enable these without separate human approval. Deterministic HMAC assignment is experiment-specific and preserves user/conversation consistency. Synthetic allocation tests are not live-user A/B results.

## Failure and restart

Fetch timeout8 seconds; each LangSmith request timeout2 seconds and no retry. Fetch all8 children, validate contracts/signature/hashes, atomically persist, then swap. Any failure keeps the last good snapshot. `PROMPT_LAST_GOOD_PATH` should point to persistent storage where available. Render ephemeral `/tmp` is NOT guaranteed across replacement/redeploy: preserve packaged local v1 as first boot fallback; remote production is revalidated on refresh. Pending durable checkpoints still contain their old snapshot, but old approval public keys must remain trusted until those flows finish. No claim of cross-Pod instantaneous refresh is made.

Private signer: ignored `backend/.env.prompt-signer`; public verifier: `backend/app/prompts/approval-public-key.json`. Do not upload the private file to LangSmith, GitHub or Render. Do not regenerate the signing key casually. Rotating keys needs an explicit migration of trust for existing HITL pins.

## Caching decision

Ordinary GenerateContent calls already support implicit caching. A zero observed cache-read count does NOT mean caching was disabled. The new model usage event reports `cached_input_tokens` and `reasoning_output_tokens`; raw provider usage is retained in synthetic experiment artifacts.

The official guide lists4096 for implicit caching. Actual explicit admission probes for Flash3.8,Pro3.1 andLite3.1 returned min_total_token_count1024. Do not conflate these thresholds. Measured static prefixes: team base+meal740, compact252; a short synthetic history493 is only a sample, NOT maximum production history. Current history bound remains10 messages×2000 characters. Never pad prompts or lengthen history to qualify. Current records, current goals/questions and fresh search results remain dynamic.

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

## Native traces and saved-result experiments

Set `LANGSMITH_TRACING=true`, `LANGSMITH_HIDE_INPUTS=true`, `LANGSMITH_HIDE_OUTPUTS=true` for live service spans; provider invocations resolve the pinned release metadata at call time, including tool/structured-output bindings. The saved200-result comparison was imported to Dataset/Experiments posthoc without regenerating answers. Import spans intentionally represent import work, NOT original provider duration/cost. Use measured_ms/token/cost metadata and frozen artifacts for comparison. Public browser requests have separately verified native spans with the actual release commit. No user/account/thread identifier was copied into new evidence files.

`publish_prompt_comparison.py` checks source hashes, uses deterministic case/run IDs, reuses saved outputs and adds numerical feedback only. Bulk metadata operations use10-second timeout after a2-second read timeout was observed; normal release fetch retains its2-second request timeout and8-second whole-refresh timeout. LangSmith trace queries are kept at100records or less per API request. Official SDK references: https://reference.langchain.com/python/langsmith/client/Client/list_runs and https://docs.langchain.com/langsmith/trace-query-syntax .

## Verified SDK/model support (2026-10-22)

Installed: `google-genai2.29.0`, `langchain-google-genai4.4.0`, `langsmith0.8.6`. Existing GenerateContent/v1beta SDK path supports `cached_content`; real streamed cache reuse confirmed it. Interactions API is not the implemented path and does not support explicit caches.

| Model / role | Implicit minimum in guide | Explicit minimum in actual rejection | Input / output / cached input, USD per1M | Storage USD per1M-token-hour |
|---|---:|---:|---|---:|
| Flash3.8 / ordinary Agent | 4096 | 1024 | .75 /3.75 /.075 | .50 through2026-12-31 |
| Flash-Lite3.1 / extraction | Not specified in that guide table | 1024 | .25 /1.50 /.025 | 1.00 |
| Pro3.1 Preview / independent judge | 4096 | 1024 | 2 /12 /.20 for <=200k | 4.50 |

These are the checked models, not a claim about all Gemini versions. Explicit TTL defaults to1hour; this experiment explicitly limits it to300seconds. Cache tokens still count toward model limits. The provider's current implicit table must not be reused as an explicit admission threshold. [Runtime rejection evidence](explicit-admission-probes.json) and [official GenerateContent cache guide](https://ai.google.dev/gemini-api/docs/generate-content/caching?hl=en) document the distinction; [prices](https://ai.google.dev/gemini-api/docs/pricing) are estimates, not invoices.

Public RAG cache benchmark freezes only exactly identical retrieved public context and static rules; question remains dynamic. It groups40identical prefixes to test short-window reuse, not real traffic locality. Bounded synthetic multi-turn histories have100distinct prefixes: a conservative creation+storage estimate fails the10% saving threshold when each prefix is used once. Do not enlarge histories or upload private records to manufacture reuse.

`benchmark_prompt_cache.py --allow-paid` saves each attempt before I/O, prevents regeneration of ambiguous interrupted attempts, and resumes from completed case/condition keys. `judge_prompt_cache.py --allow-paid` only grades saved paired answers. `analyze_prompt_cache.py` is offline and refuses fewer than100attempts per condition. The ordinary condition retains implicit caching. Costs include actual cache-read tokens and conservative full-price creation input plus full TTL storage; any unknown use retains its full ledger reservation. Interrupted streams never settle from interim usage alone. Failed/truncated/ungraded answers remain in the frozen100 denominator. Generation-timeout rows are not silently retried.

Windows artifact recovery: `PermissionError WinError5` occurred in `Path.replace` while saving the next write-ahead row, before its API invocation. The existing committed JSON preserved completed attempts. A bounded replacement-only retry (six attempts, <=300ms total sleep) was added and tested; it never retries model calls. The exact locking process was not established. [Python os.replace documentation](https://docs.python.org/3/library/os.html#os.replace) and [CPython Windows issue46003](https://bugs.python.org/issue46003) explain platform-specific replacement failures. [Execution incidents](cache-rag/execution-incidents.json) distinguishes this recovered file failure from the unresolved anomalous request timeout.
