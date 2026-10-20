# Bounded Agentic RAG implementation and frozen comparison

Approved scope: evaluate retrieved evidence, rewrite and retrieve again; preserve the existing LangGraph, HITL, corpus and citation boundary. No production data writes.

Implementation: optional default-off wrapper; at most two retrieval rounds and two controller calls; shared request model/tool budget plus a 35-second local deadline. Evaluate against the original immutable question. Relevant passages must pass the existing similarity gate AND controller sufficiency. A rewrite does not change the question being answered. Never promote ungrounded documents. Exceptions/cancellation/duplicate rewrites stop; sources keep original metadata. A second assessment can reject newly retrieved evidence; no endless retries. Prompt v1 text remains unchanged; controller has its own version/hash.

Plan: (1) failing tests for limits and unsafe evidence; (2) wrapper, configuration and progress integration; (3) fixed matched experiment; (4) regressions and review; (5) conditional rollout, browser verification and documentation.

Frozen protocol before calls: 100 attempts per condition, repeated balanced development core40 (not the sealed final20), same order/corpus/retrieval mode/answer model/prompt. Alternate pair order. Keep failures and timeouts. Report exact repeats, source-page support, independent Pro correctness/faithfulness, median/p95, actual token estimates including controller/translation/embedding and separate judge cost. No real-user or clinical claims. Missing usage means cost incomplete, never zero.

Rollout gate: both >=100, candidate correctness >=95% and >=baseline; support not lower; failure rate not higher; quality improves by >=2 percentage points; median <=1.5x and p95 <=1.5x baseline; complete estimated serving cost <=2x baseline. Otherwise leave AGENTIC_RAG_ENABLED=false and publish the result. These limits explicitly accept bounded overhead only for measured quality improvement. Do not tune on this evaluation after seeing results.
