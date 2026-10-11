# MetaDiet AI RAG final post-selection evaluation v1

## Scope

This evaluation measures the selected production candidate after parser, chunking,
embedding-dimension, search-mode, and reranker experiments were complete. It does
not tune the recipe from these results.

- Recipe: PyPDF + recursive chunks + `gemini-embedding-2` 3072 dimensions +
  hybrid Dense/BM25 retrieval + no reranker
- Retrieval: candidate 20, return 4, 6,000-character answer context
- Generation: `gemini-3.8-flash`
- Judge: `gemini-3.1-pro-preview` through Ragas 0.2.15
- Dataset: 20 questions / 10 bilingual fact groups
- Dataset SHA-256: `9182df0b969772b1e63c713f6efeaa2ada64a1dd78d1cf5350fc5586e5a807f6`
- Capture identity: `911f0cc524201b91e746`

The fact groups are disjoint from the previous pilot, development 40, and earlier
heldout 20. The earlier heldout set was already queried during embedding selection,
so it is not reused for a new independent claim. This is a sealed post-selection
evaluation assembled and source-reviewed by Codex, not blinded human clinical
adjudication.

## Results

| Measure | Result | Interpretation |
|---|---:|---|
| Completed requests | 20/20 | No provider failure in the approved network run |
| Strict gold source-page Recall@4 | 85% | 17/20 contained the designated page and excerpt |
| Adjudicated evidence support | 95% | Two misses retrieved another WHO page with the same scope statement |
| Grounded gate pass | 100% | The threshold accepted all retrieved contexts |
| Appropriate abstention | 1/1 | The one truly missing evidence case did not fabricate an answer |
| Source-reviewed answer correctness | 95% | 19/20 answered the requested fact; review was post-hoc and non-blind |
| Ragas faithfulness | 1.00 | 20/20 valid scores |
| Ragas context recall | 0.95 | 20/20 valid scores |
| Request latency p50 / p95 | 11.23 s / 25.02 s | Retrieval plus answer generation on this workstation/network |
| Generation tokens | 58,151 total | 44,499 input and 13,652 output tokens |

The strict misses were:

- `who_fat_scope-en` and `who_fat_scope-ko`: the gold page was 15, while retrieved
  pages 11 and 32 state the same prevention-versus-treatment scope. The original
  85% metric is preserved; the alternative-evidence adjudication is reported
  separately.
- `who_tfa_children_indirect-en`: the English query did not retrieve the page-16
  child-extrapolation remark. The answerer returned its no-evidence response. The
  Korean pair retrieved the remark and answered correctly.

The last case suggests an English-query expansion gap: Korean translation produced
retrieval terms closer to “extrapolation”, whereas English queries currently bypass
translation/expansion. It is a candidate for a later development experiment. This
final set must not be used to tune and then re-score the same claim.

## Ragas answer-correctness diagnostic

`FactualCorrectness` produced 0.325 with its default prompts and 0.347 after Korean
prompt adaptation plus a source-reviewed Korean reference overlay. Both runs had
20/20 valid metric calls, but exact source-correct answers such as the BMI classes
and exercise dose still received zero. These values are retained as evaluator
diagnostics and are not adopted as service-quality scores.

Ragas documentation recommends adapting LLM-powered metric prompts for the target
language. Applying that recommendation did not sufficiently calibrate this pinned
Ragas/Gemini combination. The accepted answer-correctness result is therefore the
explicit source review above, with its non-blind limitation stated. Faithfulness and
context recall remain the primary Ragas metrics.

## LangSmith and failures

The LangSmith summary smoke trace `final-rag-trace-smoke-v1` was observed after a
five-second indexing delay with status `success`. Ragas child traces expose case ID,
metric, model usage, latency, and token usage. No health-record text or API key was
added to trace metadata.

Failures and diagnosis retained during this stage:

1. The sandbox run stalled in a synchronous SDK/network thread. The same command
   completed 20/20 outside the restricted network, isolating it as an execution
   environment failure rather than a RAG failure.
2. Importing Ragas in the sandbox blocked in `nest_asyncio` while Windows created a
   `socketpair`. Heavy Ragas imports were moved behind the scoring entry point, so
   pure validation tests no longer create an event loop.
3. A direct Ragas import without `artifacts/ragas-runtime` failed because the main
   `langchain-community` no longer contains the legacy VertexAI module expected by
   Ragas 0.2.15. The documented compatibility runtime works and produced all scores.
4. An attempted cached trace replay was interrupted after its new scorer identity
   would have caused fresh judge calls. Its partial LangSmith runs are diagnostic
   only and are excluded from the reported metrics.

## Reproduction

The source dataset is `gold_final20_v1.json`; the Korean judge overlay and post-hoc
adjudication are preserved beside this report. Runtime artifacts are under
`backend/artifacts/final-rag-v1/911f0cc524201b91e746/`. The capture and scoring
 scripts fail closed on dataset SHA, answer SHA, source PDF SHA, case IDs, capture
 identity, active namespace/model/dimension/candidate count, and the parser/chunking
 metadata stored in every activated chunk. Failed capture rows are retried only up to
 a cumulative three-attempt limit; completed rows are reused only after their inputs
 and required output fields match the sealed case.

The post-hoc adjudication is bound to the exact `answers.json` bytes with SHA-256
`3cfed2c001a66f405052722e368d7d921137a983d03c1809aab8d33d5020b2f1`.
