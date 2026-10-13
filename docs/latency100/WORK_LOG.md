# 100-case verification implementation ledger

Accepted scope: build identity; real UI recommendation routing; durable budget optimization; verification-first streaming experiment; SSE recovery; Markdown/buttons; minimum 100 requests per condition including failures; public deployment and portfolio.

Ruling: continue in the existing authorized checkout, touching only named files; unrelated tmp files remain untracked.
Ruling: final evidence guard can rewrite the whole response. Never release raw model tokens before that guard. Implement buffered native streaming measurement first; enable user-visible partial streaming only if an equivalent safe incremental guard is demonstrated. Otherwise document non-adoption, as approved.
Ruling: public before/after uses a frozen 20-case set repeated five times (100 each), same synthetic account, serial requests. Public deployment comparisons are sequential, not randomized; local feature ablations will alternate configurations. Failed/blocked/timeouts stay in denominator.

- [x] baseline 100
- [x] build identity + real UI routing (health + v2 started/completed + LangSmith model metadata)
- [x] budget optimization + failure/concurrency checks (experimental only, below acceptance gate)
- [x] buffered provider streaming + SSE v2 recovery (native provider experiment, default invoke)
- [x] Markdown/components (raw HTML/images disabled, completed text authoritative)
- [x] regression/review + candidate 100 and blinded quality
- [x] public verification, docs and portfolio
- [x] synthetic fixture cleanup: verified selection-*@example.invalid; removed its Auth/app data/checkpoints and ignored credential file after public functional verification

## Findings and rulings

- Live DB alternating 100 reservations per mode: 65.04→56.19ms median (13.6%). Ruling: do not enable initialize-once in production because the predefined 20% gate was not met. Keep instrumentation and opt-in experiment; transaction locks/pre-effect reservation unchanged. 12 concurrent reservations: 4 accepted, 8 blocked; committed count 4; rollback retained row.
- Native chunk unit test exposed mixed string/list content dropped by response_text. LangChain merge_content permits both strings and blocks in one list; support strings while still excluding thought blocks. Retested 26/26.
- Markdown renderer is ESM. CRA Jest27 needs transform allowlist plus mappings for exports/imports unsupported until Jest28. No renderer mock; real rendering/security tests run.
- Fresh reviewer found missing-checkpoint retries could restart the model, and post-completed network failure could falsely replace a successful answer with an error. Added red tests then v2 explicit reconnect flag, journal-first lookup, fail-closed missing run, and stop reader at terminal event. Green backend7 + frontend19.
- Full regression before final review fixes: backend948 passed/1 pre-existing skipped; frontend75 passed. Full suite is rerun after the fixes.
- Evaluation scopes are separate: public serial before/after; native alternating actual-model calls with a synthetic fresh DB. They run concurrently for part of this session, so quota/provider shared-load is a confound; do not claim a controlled public causal estimate or production user p95.
- Final backend regression: 955 passed, 1 existing skipped; frontend 77 passed and production build passed. Summary guard tests: 3 passed after the last evaluation code edit.
- Public browser: recommendation button, actual follow-up, Markdown lists, 390px mobile, reload preserving conversation passed. Public SSE functional smoke: unique monotonic IDs, exact terminal replay, empty replay after terminal, missing-run fail-closed passed.
- Actual LangSmith root/model metadata matched 95e167d and first_direct/low; no prompt content or account identifiers exported in trace_metadata.json.
- Automated native-answer judge failed one five-answer batch with GoogleAPIError. The original retained only exception class, so exact HTTP cause is unknown. SDK also emitted an unawaited ClientResponse.json warning. Official Gemini troubleshooting was consulted; preserve the failures in primary denominator, retry only that batch into a supplemental file. Future failures record a safe error code, not secrets or raw request payloads.

Official references: [LangChain chunks](https://reference.langchain.com/python/langchain-core/messages/ai), [Gemini integration](https://reference.langchain.com/python/langchain-google-genai/chat_models/ChatGoogleGenerativeAI), [Jest transform](https://jestjs.io/docs/configuration#transformignorepatterns-arraystring), [Jest28 exports](https://jestjs.io/blog/2022/04/25/jest-28), [ReactMarkdown security](https://github.com/remarkjs/react-markdown#security), [SSE IDs](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events), [reader cancel](https://developer.mozilla.org/en-US/docs/Web/API/ReadableStreamDefaultReader/cancel), [Render identity](https://render.com/docs/environment-variables).
