# Multi-Tenant RAG & Agentic Operations Assistant

This repository hosts the implementation for a multi-tenant AI Operations Assistant that combines Retrieval-Augmented Generation (RAG), intent classification, and agentic tool execution. The goal is to provide tenant-isolated knowledge retrieval alongside actionable workflows (e.g., task management) while maintaining observability and guardrails.

## Status

- Backend scaffolding with multi-tenant auth, document ingestion, task/incident services, and the first agent orchestration pass
- Frontend integration will follow after wiring the agent API into the chat UI

## Repository Layout

- backend/ — FastAPI services, ingestion pipeline, retrieval stack, and domain data models
- frontend/ — Next.js interface for chat, tooling, and administration (placeholder)
- Makefile — Common project commands (setup, lint, test, etc.)

## Sample Data

To load demo tenants (Acme Health, Globex Security, Innotech Manufacturing) together with overlapping tasks, incidents, and Zero Trust policy documents, run:

```
python -m app.scripts.seed_data --reset
```

Use `--skip-docs` to omit document ingestion when Qdrant is unavailable. The script is idempotent and skips existing records by title/subdomain.

## Embedding & Vector Strategy

- **Embedding model**: `sentence-transformers/all-MiniLM-L6-v2` (384-dim) balances quality and self-hostability, keeping GPU/CPU footprint low while supporting multilingual tenant content. When OpenAI keys are present, embeddings can fall back to `text-embedding-3-small` for parity with production.
- **Collection topology**: a single Qdrant collection (`multi_tenant_documents`) stores all chunks with hard tenant filters (`tenant_id`, `document_id`) indexed for fast metadata filtering. This keeps maintenance simple while still guaranteeing isolation at query time.
- **Filter strategy**: every search request injects tenant-specific filters; additional metadata (tags, document_id) powers fine-grained retrieval without cross-tenant leakage.

Additional design documentation and setup instructions will follow as the implementation progresses.

## Configuration

Populate a `.env` file (or export environment variables) with the following chunking controls to tune how documents are split before embedding:

- `CHUNK_MAX_CHARS` — maximum characters per chunk, defaults to 512.
- `CHUNK_OVERLAP_CHARS` — overlap between consecutive chunks, defaults to 50.

The backend reads these values via Settings in [backend/app/config.py](backend/app/config.py), allowing you to widen or shrink chunk sizing without code changes.

### Retrieval Tuning

- `CACHE_ENABLED`, `CACHE_NAMESPACE`, `CACHE_TTL_SECONDS` control the Redis-backed retrieval cache. Provide `REDIS_URL` and leave caching enabled to avoid recomputing embeddings for repeated tenant queries. Set `CACHE_ENABLED=false` locally when Redis is unavailable.
- `RERANKER_ENABLED`, `RERANKER_MODEL`, `RERANKER_MAX_CANDIDATES` enable the optional cross-encoder step in [backend/app/services/rerank_service.py](backend/app/services/rerank_service.py). When enabled, ensure the sentence-transformers package can download the configured model.

### Retrieval Evaluation

Prepare a JSON dataset (see [seed_data/eval_queries.sample.json](seed_data/eval_queries.sample.json) for structure) and run the evaluator to measure hit rate, recall, and MRR:

```
python -m app.scripts.evaluate_retrieval --dataset seed_data/eval_queries.sample.json
```

Add `--disable-cache` or `--disable-reranker` to compare retrieval variants. Verbose output surfaces per-query matches for easier troubleshooting.

## Running Locally

1. **Infrastructure**
	- Start Redis (`brew services start redis` or `docker run -p 6379:6379 redis:7`).
	- Launch Qdrant (`docker run -p 6333:6333 qdrant/qdrant:latest`).
	- Provide a database URL; SQLite is fine for local work (`DATABASE_URL=sqlite:///./data/app.db`).
2. **Backend**
	- Create a virtualenv, install deps, and populate `.env` inside `backend/` with at least:

```
DATABASE_URL=sqlite:///./data/app.db
REDIS_URL=redis://localhost:6379/0
JWT_SECRET_KEY=dev-secret-change-me
APP_NAME=Multi-Tenant RAG System
DEBUG=1
```

	- Run the API with:

```
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

3. **Frontend**
	- Create `frontend/.env.local` and set `NEXT_PUBLIC_BACKEND_URL` to the backend origin (default `http://localhost:8000`).
	- Install and start Next.js:

```
cd frontend
pnpm install
pnpm dev
```

4. **Smoke Test**
	- Log in via the web UI, pick a tenant, open a conversation, and send a prompt. You should see a live assistant response while the backend caches and stores the exchange. Use `seed_data/corpus.json` with `python -m app.scripts.seed_data --reset` if you need demo tenants/documents.

## Operations

- Reprocess stored documents by calling POST /api/v1/documents/reprocess with the payload defined in [backend/app/schemas/document.py](backend/app/schemas/document.py#L120-L151). The endpoint accepts explicit document_ids or filtering parameters and queues background processing for matching records.

## Agent Layer Overview

- **Endpoint**: `POST /api/v1/agent/execute`
	- Runs LLM-based intent classification, decomposes informational queries, retrieves tenant-scoped context, and synthesises a grounded response.
	- Action intents are mapped to built-in tools (`create_task`, `get_open_tasks`, `summarize_incidents`) using an LLM planner before executing against tenant data.
- **Request payload** (`AgentRequest`):
	- `query` (string, required)
	- Optional overrides for `llm_provider`, `llm_model`, retrieval cutoffs (`max_chunks`, `score_threshold`)
- **Response** (`AgentResponse`):
	- `execution.intent` — classification metadata with confidence and extracted entities
	- `execution.result` — chat-ready answer plus the context snippets used
	- `execution.action` — populated when a tool is invoked, including tool outputs for downstream audit trails

Agents reuse the existing `LLMService`, `EmbeddingService`, and `QdrantVectorService`, ensuring all tenant isolation guarantees remain intact.
