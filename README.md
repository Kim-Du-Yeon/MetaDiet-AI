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
- Routing and RAG evaluation reports

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

## Notes

- Nutrition values are calculated through CSV lookup, not RAG, to reduce hallucination.
- RAG is used for nutrition knowledge and advice with document grounding.
- Food photos are used to identify food names only; grams and meal type are confirmed by the user.
- `.env`, virtual environments, local DB files, and generated caches are ignored by Git.
