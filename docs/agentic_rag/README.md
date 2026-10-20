# Bounded Agentic RAG (experimental)

The active LangGraph coaching team can optionally call a read-only evidence loop: retrieve → assess against the original question → rewrite → retrieve → assess. This is a bounded tool-internal workflow, not a replacement of the supervisor graph or HITL write gate.

- `AGENTIC_RAG_ENABLED=false` by default. Rollback by disabling it and restarting.
- `AGENTIC_RAG_MAX_ROUNDS=2` (hard range1–2): initial search plus at most one rewritten search.
- `AGENTIC_RAG_TIMEOUT_SECONDS=35` (hard maximum60): total local loop deadline, also subject to the request deadline.
- At most two Lite controller calls,512 output tokens each; controller input capped at6000 evidence characters. Korean query translation is also reserved in the shared model budget. Every additional retrieval reserves a shared tool call.
- Existing dense similarity gating remains mandatory. A controller cannot promote low-score evidence. Rejected, timed-out, failed or unassessed passages cannot become answer evidence. Source/page/document hashes survive excerpt clipping.
- No retries on transport/controller errors in this request; subsequent distinct queries are suppressed after operational failure. No user record writes or automatic confirmation.
- Progress events report actual retrieval, evaluation, rewrite and research phases. Sources still require explicit answer citations; retrieved-but-unused documents do not become citations.
- Controller prompt has its own version/hash. Existing prompt release v1 is unchanged. Prompt versioning does not eliminate model nondeterminism.

## Evaluation

[Fixed100-per-condition read-only development comparison](20261020/README.md) records the conditional rollout decision and limits. Do not infer clinical accuracy or public browser p95 from a repeated development QA benchmark. The historical sealed final20 was not used to tune this loop.

## Official design references

- [LangGraph Agentic RAG](https://docs.langchain.com/oss/python/langgraph/agentic-rag): grade documents and route to generation or question rewriting. Our loop additionally has hard call/deadline limits and fail-closed evidence handling.
- [Gemini structured outputs](https://ai.google.dev/gemini-api/docs/structured-output): schema-constrained output; local validation and failure handling are still required.
- [Gemini thinking token limits](https://ai.google.dev/gemini-api/docs/thinking): output limits include reasoning; a512-token Pro judge can truncate before JSON completes.
- [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing): frozen token estimates are not invoices; embedding text input listed at$0.20/M tokens when checked2026-10-20.

## Reproduce

Run from repository root with the project venv and ignored backend/.env. Never commit credentials. The runner reads production vectors but never creates an index or touches user tables.

```powershell
backend/venv/Scripts/python.exe backend/scripts/eval/benchmark_agentic_rag.py --output docs/agentic_rag/20261020
backend/venv/Scripts/python.exe backend/scripts/eval/rejudge_agentic_rag.py --output docs/agentic_rag/20261020 --grades-name new-judges.jsonl
backend/venv/Scripts/python.exe backend/scripts/eval/analyze_agentic_rag.py docs/agentic_rag/20261020 --grades-name quality-status.jsonl
```

Runners refuse to overwrite existing attempts. Copy the frozen cases/protocol into a new result directory for a new experiment. Existing failure rows must remain in reports. Recovered judging never regenerates serving answers; original judge failures/cost remain separate.
