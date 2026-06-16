# MetaDiet AI

MetaDiet AI is a personalized diet coaching system built with a LangGraph-based Multi-Agent architecture. It records meals through natural language and food photos, calculates nutrition from a structured CSV food database, provides document-grounded nutrition advice with RAG, and updates diet targets from InBody photo uploads.

## Key Features

- Multi-Agent orchestration with LangGraph
- Supervisor-based intent routing
- Human-in-the-loop meal confirmation before DB writes
- Meal logging from natural language and food photo recognition
- CSV-based nutrition lookup for deterministic calorie/macronutrient calculation
- Hybrid RAG for nutrition knowledge: Pinecone dense retrieval + BM25 + RRF + FlashRank reranking
- Grounded generation with source/page citations and guardrails
- InBody OCR/Vision flow for strategy updates
- Meal plan generation with validator feedback loop
- Checkpointing, time travel, and rollback with LangGraph checkpointer
- Structured evaluation pipeline with reproducible datasets and LangSmith tracing

## Architecture Highlights

- `supervisor`: routes user intent to specialized agents
- `diet_logger`: parses meal text and calculates nutrition
- `confirm`: handles HITL confirm/modify/cancel
- `strategy`: provides diet advice
- `meal_plan`: generates daily meal plans
- `validator`: validates meal plans and sends feedback
- `inbody`: updates diet strategy from InBody history
- `reporter`: creates weekly/monthly nutrition reports
- `edit`: modifies or deletes saved meals

See [ARCHITECTURE.md](ARCHITECTURE.md) for the detailed architecture and [EVALUATION.md](EVALUATION.md) for routing/RAG evaluation.

## Tech Stack

- Frontend: React
- Backend: FastAPI, Python
- Agent framework: LangGraph, LangChain
- LLM/Vision: OpenAI GPT models
- Embedding: `text-embedding-3-small`
- Vector DB: Pinecone
- Reranker: FlashRank `ms-marco-MiniLM-L-12-v2`
- Database: Supabase Postgres
- Tracing/Evaluation: LangSmith, local JSON eval reports

## Environment Variables

Secrets are not committed. Copy `backend/.env.example` to `backend/.env` and fill in your own keys.

```bash
cp backend/.env.example backend/.env
```

Required values include:

- `OPENAI_API_KEY`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_KEY`
- `SUPABASE_JWT_SECRET`
- `SUPABASE_DB_URL`
- `PINECONE_API_KEY`

## Run Locally

Backend:

```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Frontend:

```bash
cd frontend
npm install
npm start
```

## Evaluation

Evaluation datasets (`routing_dataset.json`, `edge_dataset.json`, `gold_dataset.json`) contain input QA items used for testing.
Result reports (`routing_report_*.json`, `ragas_report_*.json`) record eval run outputs and are committed for reproducibility.
Detailed file classification: [EVALUATION.md](EVALUATION.md).

### Supervisor Routing

- Baseline routing eval: **18/18** (intent_accuracy 1.00, route_accuracy 1.00)
- Edge-case routing eval: **15/18 → 18/18** after adding food/intake keyword signals
  (`_FOOD_KW` / `_INTAKE_KW`) to `_heuristic_intent()` with "log-first" policy
- 6 edge types covered: typo, missing_unit, empty_or_irrelevant, mixed_lang, pending_flow, mixed_intent
- Eval datasets: `routing_dataset.json` (18 cases), `edge_dataset.json` (18 cases)
- Detail: [EDGE_EVAL_REPORT.md](backend/scripts/eval/EDGE_EVAL_REPORT.md)

### RAG (Hybrid Retrieval + Grounded QA)

- Gold dataset: `gold_dataset.json` — EN/KO bilingual QA 10쌍, 총 20개 (동일 근거 공유, cross-lingual retrieval 영향 분리 목적)
- Eval modes: dense / hybrid / full — page_hit, excerpt_hit, faithfulness, citation_rate
- full mode result: source_hit 1.00 / page_hit 1.00 / excerpt_hit 0.90 / avg_score 0.978
- Detail: [EVALUATION.md](EVALUATION.md)

### Ragas Evaluation

- Framework: ragas 0.2.15 — `faithfulness` + `context_recall` on `gold_dataset.json`
- English QA (n=10): faithfulness **0.900** / context_recall **0.950** — stable
- Korean QA (n=10): faithfulness **0.200** / context_recall **0.300** — cross-lingual retrieval gap
- Finding: the performance gap is driven by querying an English PDF corpus with Korean questions,
  not by RAG pipeline failure; improvement direction is query translation or multilingual embedding
- Note: ragas is managed via a separate evaluation script (`run_ragas_eval.py`),
  independent of the main `requirements.txt` environment
- Detail: [RAGAS_EVAL_REPORT.md](backend/scripts/eval/RAGAS_EVAL_REPORT.md)

### LangSmith Tracing

- `routing-eval` and `rag-eval` traces confirmed in the `diet-agent` LangSmith project
- `LANGSMITH_*` env vars mapped to `LANGCHAIN_*` in all eval scripts
- `tracing_context(enabled=True)` + `Client().flush()` applied for reliable trace delivery
- Detail: [EVALUATION.md](EVALUATION.md)

## Notes

- Nutrition values are calculated through CSV lookup, not RAG, to reduce hallucination.
- RAG is used for nutrition knowledge and advice with document grounding.
- Food photos are used to identify food names only; grams and meal type are confirmed by the user.
- `.env`, virtual environments, local DB files, and generated caches are ignored by Git.

