# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

MetaDiet AI — a LangGraph multi-agent diet coaching system. FastAPI backend, React frontend, Supabase Postgres, Pinecone for hybrid RAG. Full architecture is documented in [ARCHITECTURE.md](ARCHITECTURE.md) (with mermaid diagrams per subsystem) and evaluation methodology in [EVALUATION.md](EVALUATION.md) — read those before making non-trivial changes to the graph, RAG pipeline, or eval scripts.

## Commands

**Always use the project venv at `backend/venv`** — the system/Windows-Store `python` is a stub and will fail (exit 49). There is no other interpreter to use.

Backend (from `backend/`):
```
venv\Scripts\activate
python main.py                       # runs on :8000, reload via UVICORN_RELOAD=true
```
Or without activating: `backend\venv\Scripts\python.exe <script>`.

Frontend (from `frontend/`):
```
npm start     # dev server
npm run build
npm test
```

Env setup: `cp backend/.env.example backend/.env` and fill in `OPENAI_API_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `SUPABASE_JWT_SECRET`, `SUPABASE_DB_URL`, `PINECONE_API_KEY`.

RAG index build (from `backend/`, after changing chunking/config or adding PDFs to `docs/nutrition`):
```
python scripts/build_rag.py
```

Evaluation scripts (from `backend/`, see "Evaluation datasets" below for which dataset goes with which script):
```
python scripts/eval/run_routing_eval.py --dataset routing_dataset.json   # or edge_dataset.json
python scripts/eval/run_eval.py --mode dense|hybrid|full --dataset qa_dataset.json --k 4
python scripts/eval/run_ragas_eval.py --dataset gold_dataset.json --mode full --k 4 [--limit N]
```
`run_ragas_eval.py` depends on `ragas==0.2.15`, which is **not** in `requirements.txt` — install it in a separate venv (e.g. `venv_ragas`). In that env, pin `langchain-community==0.4.1` and do **not** install `langchain-experimental`: ragas 0.2.15 imports `langchain_community.chat_models.vertexai`, which `langchain-community` removed starting 0.4.2, and `langchain-experimental` would force `langchain-community>=0.4.2` right back, recreating the conflict.

Tests (from `backend/`):
```
pytest                                # 52 tests in tests/{unit,security,rag,integration}/
```
All external calls (OpenAI/Pinecone/Supabase) are mocked via `tests/conftest.py`'s `FakeSupabase`/`FakeVectorStore` + `mock_current_user`/`fake_sb` fixtures — no network or API keys needed to run it. `pytest.ini` sets `asyncio_mode = auto`. `backend/tests/images/` (sample photos for manual Vision/OCR checks) predates the suite and isn't wired into it.

Demo data: `python scripts/seed_data.py` (3 months synthetic) / `python scripts/seed_male_demo_data.py` (presentation demo data). Graph visualization: `python scripts/visualize_graph.py` → `graph.png`.

## Architecture

### Multi-agent graph

`backend/app/agents/graph.py` builds the LangGraph `StateGraph`. Every request: `load_state` (loads today's intake/targets/latest inbody/goal fields from DB) → `supervisor` (LLM intent classification into one of 8 intents, with heuristic guardrails in `supervisor/node.py: _heuristic_intent()` for high-cost-of-error cases like confirm/edit/inbody/reporter) → routed agent → `save_chat` → END.

Key routing invariant (`route_to_agent` in `supervisor/node.py`): if `awaiting_confirmation=True` and intent isn't one of `[confirm, edit, diet_logger, strategy]`, force-route to `confirm` so a pending meal proposal can't be abandoned mid-flow.

Agents live one per directory under `backend/app/agents/<name>/node.py`: `diet_logger`, `confirm` (HITL gate), `strategy`, `meal_plan`, `validator`, `inbody`, `goal_manager`, `reporter`, `edit`, `supervisor`. `confirm` is wired with `interrupt_before=["confirm"]` — the graph pauses there until the user responds via `/chat/resume`.

`inbody` auto-chains into `goal_manager` (`graph.py`: `inbody → goal_manager → save_chat`) so every InBody upload also gets a goal-progress check, in addition to `goal_manager` being directly reachable via its own chat intent. `goal_manager_node` appends to `state["response"]` rather than overwriting it (`_append()` helper) specifically so the chained case doesn't clobber `inbody`'s own analysis text.

### meal_planner subgraph

`build_meal_planner_subgraph()` in `graph.py` encapsulates a `meal_plan ↔ validator` feedback loop as a single parent node so the HITL/checkpointer behavior outside it is unaffected. `validator` scores the generated plan against nutrition targets; on failure with `validation_attempts < 3` it loops back to `meal_plan` with feedback, otherwise force-passes (`validator/node.py:26`) and hands off to the parent's `confirm`.

### State and reducers

`AgentState` (TypedDict) in `backend/app/schemas/models.py` is the shared state channel set. Each field has an explicit reducer because LangGraph errors on multi-write without one within a step:
- `keep_latest` — overwrite (most scalar fields, including `message` for `/chat/resume` injection)
- `add_messages` — append (`messages`)
- `merge_pending_meals` — `None` clears the pending proposal, otherwise replace
- `keep_max` — monotonic counter (`validation_attempts`, survives the subgraph loop)

`forced_meal_type` lets the frontend's meal-type buttons override `diet_logger`'s LLM-guessed meal type (falls back to LLM guess if absent). `rag_context`/`rag_grounded` are populated once per graph run (by `meal_plan` or whichever agent searches first) and reused by `validator` to avoid duplicate retrieval and token spend.

### RAG pipeline

`backend/app/rag/retriever.py` exposes a single entry point `retrieve(query, k, use_hybrid, use_rerank)`: queries containing Hangul are auto-translated to English first (`_translate_to_english()` — regex-detected, one LLM call; pure-English queries pass through untouched, no extra cost), then Pinecone dense search + BM25 sparse search (`chunks.pkl`) fused via RRF, then FlashRank reranking. If translation actually happened, the *original* Korean query is also searched in parallel and RRF-merged with the translated results (dual query expansion, to recover anything the translation dropped). A result is `grounded` if the rerank score clears `rag_rerank_threshold` (0.15, configurable in `app/core/config.py`), falling back to cosine `rag_score_threshold` (0.35) when sparse/rerank artifacts are missing (dense-only degradation). Embedding model is `text-embedding-3-large` / 3072-dim (`app/core/config.py`'s `embedding_model`/`embedding_dimension` — not hardcoded; changing either requires deleting and recreating the Pinecone index, since dimension is fixed at index-creation time, then re-running `build_rag.py`). `backend/app/rag/qa.py: answer_from_knowledge()` is the guardrailed answerer — refuses with no fabricated answer when ungrounded, and always appends a source/page footer otherwise. Every `retrieve()` caller (8 agent nodes + `rag_nutrition_tool`) follows the same grounded-gating pattern: substitute a "근거 부족" placeholder into the prompt instead of an empty context when `grounded=False`, so the LLM doesn't fabricate citations.

Index is built by `backend/scripts/build_rag.py`: `PyPDFLoader` (keeps page metadata) → junk-page filter → `SemanticChunker` → hard size cap (max 1200 chars / 150 overlap) → Pinecone upsert + local `chunks.pkl` for BM25. Source PDFs live in `docs/nutrition/`.

Nutrition *values* (calories/macros) are deliberately **not** RAG — they're deterministic CSV lookups against `docs/nutrition/식품성분표_10개정판.csv` via `app/tools/nutrition_db.py`, to avoid hallucinated numbers. RAG is reserved for explanatory nutrition knowledge/strategy advice that needs document grounding.

### Checkpointing / time travel

`AsyncPostgresSaver` (Supabase Postgres) persists a state snapshot per node per `thread_id`. `/chat/history/{thread}` lists checkpoints, `/chat/rollback` restores one and lets the conversation resume from that point — used e.g. to fix a previously-confirmed meal without duplicating DB rows (`overwrite_on_confirm` flag tells `confirm` to replace rather than append).

**Windows-specific**: `psycopg`'s async driver requires `SelectorEventLoop`, not the default `ProactorEventLoop`. `backend/main.py` sets `WindowsSelectorEventLoopPolicy` and runs uvicorn via `asyncio.run(server.serve(), loop_factory=lambda: asyncio.SelectorEventLoop(...))` — don't replace this with a plain `uvicorn.run()`/default loop on Windows, it breaks the checkpointer. `AsyncPostgresSaver` also holds a single connection, so a request that's interrupted mid-flight can block subsequent DB calls until the server restarts.

### Authentication

Every endpoint except `/health` and `/nutrition/lookup` requires `Authorization: Bearer <supabase_jwt>`. `app/core/auth.py` has two FastAPI dependencies, and they return **different UUIDs** — don't mix them up:
- `get_current_auth_id` — just decodes the JWT and returns `sub` (Supabase `auth.uid()`). Doesn't require a `users` row to exist, so it's the one `/users/setup` uses (a brand-new signup has no `users` row yet; that endpoint upserts one).
- `get_current_user` — wraps the above, then looks up `users.id` from `auth_id`. *This* is the value the rest of the app calls `user_id` and what `meal_logs.user_id`/`diet_strategies.user_id` etc. actually reference as their FK.

### Vision / OCR

Vision is used only for *parsing*, never for deciding grams or whether to save — that's always a user-confirmed step through `/chat` (`diet_logger`). `app/ocr/food_vision.py` (food photo → food names only) and `app/ocr/inbody_ocr.py` (InBody photo → measurements, with prompt guardrails against misreading body-water/protein/mineral rows as body weight, corrected against history). `app/ocr/image_classifier.py: classify_image_type` lets a single camera button on the frontend dispatch to either path via `POST /image/upload`.

## Evaluation datasets

Each evaluation domain has its own dataset + script; don't conflate them (see [EVALUATION.md](EVALUATION.md) section 8 for the full table):

| Dataset | Used by | Gold field | Measures |
|---|---|---|---|
| `routing_dataset.json` | `run_routing_eval.py` | `expected` (agent label) | baseline routing accuracy, 7 intents |
| `edge_dataset.json` | `run_routing_eval.py` | `expected` + `edge_type` | routing robustness on typos/mixed intent/etc (6 edge types) |
| `qa_dataset.json` | `run_eval.py` | `gold_source`/`gold_page`/`gold_excerpt` | dense vs hybrid vs full RAG retrieval ablation (custom metrics, no Ragas) |
| `gold_dataset.json` | `run_ragas_eval.py` | `gold_answer` + `language` | Ragas `faithfulness`/`context_recall`, EN/KO cross-lingual comparison |

`*_report*.json` files alongside each dataset are committed eval run outputs (for reproducibility), not inputs. The RAG corpus is still English-only PDFs, but the cross-lingual gap this used to cause is largely closed: after adding query translation + dual query expansion + the embedding upgrade above, Ragas Korean scores went from faithfulness 0.200/context_recall 0.300 to **0.850/0.950** (`backend/scripts/eval/ragas_report.json`; see EVALUATION.md section 7 for detail). One open regression from that same change: English context_recall dropped 0.950→0.700 (3/10 samples), suspected to be from `chunks.pkl` re-chunking differently under the new embedding model (`SemanticChunker` boundaries depend on the embedding) — not yet root-caused.
