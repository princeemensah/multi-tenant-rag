# Multi-Tenant RAG & Agentic Operations Assistant

<div align="left">

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Built with: FastAPI + Next.js + Qdrant](https://img.shields.io/badge/Built%20with-FastAPI%20%2B%20Next.js%20%2B%20Qdrant-green.svg)

</div>

---

**Documentation**: [docs/README.md](docs/README.md)

This repository shows a multi-tenant retrieval-augmented generation (RAG) pipeline, intent-aware agent orchestration, and guarded tool execution behind a FastAPI backend and Next.js frontend.

## 1. Architecture Overview

```
User Query
	│
	├─► Intent Classifier (informational / analytical / action / clarify)
	│        │
	│        └─► Tool Planner (decide if tools are required)
	│
	├─► Retriever (chunking + embeddings + tenant-filtered Qdrant search)
	│
	├─► Context Builder (dedupe, rank, cite)
	│
	├─► LLM Reasoning (structured prompts, guardrails, streaming events)
	│
	└─► Optional Agent Tool Invocation (tasks, documents, incidents)
				│
				└─► Response with citations + guardrail summary
```

- **Backend**: FastAPI, SQLAlchemy, Pydantic, structlog, Redis, PostgreSQL, Qdrant.
- **Frontend**: Next.js App Router, Tailwind, Radix UI, SWR data hooks.
- **LLM integration**: Provider-agnostic `LLMService` (OpenAI/Anthropic), MiniLM embeddings for ingestion and retrieval.
- **Multi-tenancy**: Tenant-scoped DB sessions, tenant metadata enforced at retrieval and tool level.

## 2. Repository Layout

```
backend/     FastAPI application, agents, services, evaluation scripts
frontend/    Next.js UI for chat, tenant selection, and admin views
docs/        Supplemental design notes and diagrams
seed_data/   Demo tenant corpus and evaluation query samples
uploads/     Example document uploads used during local testing
Makefile     One-command workflows for setup, linting, tests, and Docker
docker-compose.yml  Local infrastructure for Postgres, Redis, Qdrant, app containers
```

## 3. Prerequisites

- macOS or Linux (tested on macOS Monterey / Sonoma)
- Python 3.12 (virtual environment managed via `make install`)
- Node.js 20 (used by the frontend when running outside Docker)
- Docker Desktop 4.x (Compose v2)
- OpenAI / Anthropic API keys (optional, required for live LLM calls)

## 4. Setup & Local Development

### 4.1 Clone the project

```bash
git clone https://github.com/princeemensah/multi-tenant-rag.git
cd multi-tenant-rag
```

### 4.2 Configure environment variables

Backend:

```bash
cp backend/.env.example backend/.env
```

Set values for `DATABASE_URL`, `REDIS_URL`, `QDRANT_URL`, and any provider credentials (OpenAI, Anthropic). The examples default to local infrastructure.

Frontend:

```bash
cp frontend/.env.example frontend/.env.local
```

Set `NEXT_PUBLIC_BACKEND_URL=http://localhost:8000` for local development.

### 4.3 Install dependencies

```bash
make install
```

Creates `.venv`, installs backend (editable) and frontend dependencies, and aligns tooling versions (ruff, pytest, TypeScript, etc.).

### 4.4 Start supporting infrastructure

```bash
make docker-up-infra
# or
docker compose up -d postgres redis qdrant
```

> **DNS on macOS**: If Docker pulls fail with `docker-images-prod...r2.cloudflarestorage.com: no such host`, set Wi-Fi DNS servers to public resolvers and retry:
> ```bash
> sudo networksetup -setdnsservers "Wi-Fi" 1.1.1.1 1.0.0.1
> networksetup -getdnsservers "Wi-Fi"
> ```

When the infra stack is running, the backend `.env` should target container hostnames:

- `DATABASE_URL=postgresql+psycopg://rag:rag@postgres:5432/rag`
- `REDIS_URL=redis://redis:6379/0`
- `QDRANT_HOST=qdrant`, `QDRANT_PORT=6333`

### 4.5 Run the backend API

```bash
make backend-dev
```

FastAPI serves at http://localhost:8000 with automatic reload.

### 4.6 Run the frontend UI

```bash
make frontend-dev
```

Next.js dev server runs on http://localhost:3000.

## 5. Running the Full Stack in Docker

Both application images are built from Dockerfiles that mirror production packaging:

- **Backend**: [backend/Dockerfile](backend/Dockerfile#L1-L26) installs directly from `pyproject.toml` (`pip install .`).
- **Frontend**: [frontend/Dockerfile](frontend/Dockerfile#L1-L20) pins Yarn 1.22.22 to stay compatible with the v1 lockfile.

```bash
docker compose build backend frontend
docker compose up -d backend frontend
```

Stop any local `yarn dev` processes occupying port 3000 before starting the frontend container. Tear down the stack with:

```bash
docker compose down
```

## 6. Seed Sample Tenants (Optional)

```bash
make seed
```

Resets the database and loads demo tenants (Acme Health, Globex Security, Innotech Manufacturing) with documents, tasks, and incidents. Seed scripts rely on the infra services being available.

## 7. Tests

```bash
make lint            # Ruff (backend) + Next.js lint (frontend)
make test            # Pytest suite for backend services
make format-backend  # Ruff format
make format-frontend # Next.js lint --fix
```

## 8. Key Design Decisions

### Retrieval Pipeline

- Documents are chunked into windowed segments (default 512 tokens overlap 64) during ingestion.
- Embeddings use MiniLM via `SentenceTransformerEmbeddingService` for cost-efficient semantic search.
- Qdrant stores vectors with tenant, document type, created_at metadata to enable compound filtering.
- Retrieval executes top-k semantic search with optional reranking (BM25 fallback and score-based pruning).

### Multi-Tenant Isolation

- Each request carries a tenant identifier resolved from auth/session middleware.
- Database access relies on scoped sessions that inject tenant filters at the ORM layer.
- Retriever queries include tenant metadata filters; cross-tenant results are structurally impossible.
- Agent tools require tenant IDs explicitly, and data access is validated before execution.

### Agent & Tooling

- `IntentService` classifies requests into informational, analytical, action, or clarify buckets.
- Planner decides whether to call tools such as `get_open_tasks`, `create_task`, `summarize_incidents`.
- Tool invocation happens via structured payloads with validation; failures are caught and surfaced to the LLM so it can recover gracefully.
- Responses include citations to retrieved context and a guardrail summary detailing actions taken.

### Evaluation & Guardrails

- Retrieval evaluation script (`python -m app.scripts.evaluate_retrieval`) reports hit rate and recall on sample queries.
- Conversations persist telemetry (model, latency, cost, guardrail warnings) for offline analysis.
- Guardrail service checks context length, content type, and tool call outcomes before completing a response.

### Observability

- `structlog` provides JSON logs with trace IDs across the request lifecycle.
- Server-sent events stream reasoning steps, retrieved chunks, tool invocations, and guardrail messages to the UI for transparency.

## 9. Troubleshooting

- **Docker DNS failures**: Configure Wi-Fi DNS as described in section 4.4 and restart Docker Desktop.
- **Port 3000 in use**: Stop any local Next.js dev server (`yarn dev`) before running the frontend container.
- **Stale volumes**: `docker compose down -v` removes Postgres/Qdrant data if you need a clean environment.

## 10. License

Released under the MIT License (see `LICENSE`).
