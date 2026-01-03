# Multi-Tenant AI Operations Assistant

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
