# Gemini task routing — implementation and evidence ledger

User-approved brief: keep deterministic nutrition and HITL, use environment-configured
Flash-Lite for bounded parsing/classification/query translation, Flash for coaching,
Vision and tool-using agents, and Pro for offline Ragas. Compare identical frozen
cases at least 100 attempts per condition; deploy enabled only after quality,
freshness, failure, latency and cost gates pass. Preserve the supplied role table
in portfolio/GitHub, distinguishing recommendations from actual adoption.

## Scope and decisions

- Existing purpose-specific call sites select a model without an extra router LLM.
- Main Supervisor delegates and tool loops remain Flash: they are not bounded
  classification. No automatic Pro escalation without a separately evaluated policy.
- Reviewed-food fast path remains zero-model. Embeddings/index are unchanged.
- `MODEL_ROUTING_ENABLED=false` is the rollback/default; `GEMINI_SIMPLE_MODEL`
  applies only to extraction, classification and query_translation. Existing
  `GEMINI_MODEL`, `GEMINI_VISION_MODEL`, `GEMINI_EVAL_MODEL` retain their meanings.
- Explicit injected test factories and legacy model overrides keep priority.
- Actual provider usage, including reasoning output, is needed for cost evidence;
  absent usage is unknown, never free. Account billing is not estimated usage cost.
- No production data in the evaluation: synthetic reads, mocked proposal boundary.

## Steps

1. Verify model availability and billing using sanitized preflight; record failures.
2. RED→GREEN routing/configuration/capability and call-site tests.
3. Implement purpose routing, safe model metadata and existing-node wiring.
4. Freeze 100 synthetic cases and compare baseline/routing in alternating order;
   assess structured tasks deterministically and coaching with an independent-role
   Pro judge plus freshness against current fixture values. Keep all failures.
5. Full backend regression; document image/table, prices, evidence and limitations.
6. Fresh-context final review; publish code/docs to GitHub. Enable/deploy only if
   the live evaluation passes; otherwise leave routing disabled and report blocker.

## Ledger

- Repository inspected, architecture/evaluation methodology read; working branch
  `codex/gemini-task-routing`. Initial branch creation needed filesystem escalation.
- Existing `.env` remains git-ignored; no key values are printed or copied to docs.
- User clarification: env chooses model IDs; code chooses workload purpose.
- RED→GREEN: purpose routing6 expected initial failures; cost/gate import RED;
  explicit env credential test RED→GREEN; per-task gate RED→GREEN; shard identity
  merge tests RED→GREEN. Full suite1394 passed/1existing skip before merge tests.
- Preflight: file key Flash/Lite200, Pro429 free tier. SDK pilot used stale inherited
  key402; explicit eval-only env credential override fixed that without production changes.
- Final fresh reviewer found contract/reasoning mismatch and aggregate gate risk;
  fixed against real legacy prompts/nodes and task-level gates. Subsequent order
  review found task-fixed pair ordering; use occurrence-based alternation.
- Final v2 uses3 independent worker processes, same frozen100 cases partitioned
  by index%3, baseline/candidate per occurrence alternate. Earlier runs are
  exploratory and preserved, not silently dropped from their own records.
- Actual Flash quota: HTTP429, free-tier daily20 requests, retry81792s. Pro remains
  unavailable; no paid changes authorized/performed. Failure rows remain in final
  denominator; no enabled deployment without full cost/judge evidence.
- Final exact200 rows verified across3 shards: baseline17/100 (all zero-model
  heuristics), routed74/100 (17 heuristics+57 Lite), coaching0/25 each. Full judge
  and unknown costs block adoption; no speed/accuracy improvement claimed.
- Error-label substring402 bug and Windows CRLF identity mismatch reproduced
  with RED→GREEN tests; preserve raw rows and execution snapshot, canonicalize
  only text hash/newlines and separately normalize unambiguous RateLimit type.
- Final backend1399 passed/1existing skip; frontend108/31 suites passed/build
  succeeded. Eight staged execution-source identities verified after Git LF
  normalization. Publish draft branch/PR; production flag stays false.
