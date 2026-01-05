# System Overview

Understand how the repository is organized, which services power the stack, and the design decisions behind the Multi-Tenant RAG & Agentic Operations Assistant.

## Repository Structure

```
multi-tenant-rag/
├── backend/                # FastAPI backend
│   ├── api/                # Versioned REST endpoints
│   ├── services/           # Retrieval, LLM, guardrail, and tool orchestration services
│   ├── models/             # SQLAlchemy ORM models with tenant isolation
│   ├── schemas/            # Pydantic request/response schemas
│   ├── scripts/            # Seeding, evaluation, and document management utilities
│   └── database/           # Session management, connection pooling, Alembic base
├── frontend/               # Next.js app router frontend
│   ├── app/                # Protected routes for conversations, tenants, dashboards
│   ├── hooks/              # SWR-based data fetching hooks
│   ├── lib/                # API client, session utilities, intent helpers
│   └── types/              # Shared Zod schemas and TypeScript types
├── seed_data/              # Demo tenants, documents, and evaluation datasets
├── uploads/                # Example markdown uploads used during seeding
└── docs/                   # Project documentation
```

## Runtime Stack

### Backend

- **FastAPI** with dependency injection for auth, tenant scoping, and database sessions
- **SQLAlchemy 2.0** for ORM mappings and migrations (Alembic)
- **Redis** for caching query results and short-lived conversation state
- **Qdrant** for vector search with strict tenant filtering
- **Async jobs (roadmap)** for heavier ingestion/evaluation tasks
- **Pydantic** models for typed service boundaries and API schemas

### Frontend

- **Next.js 14 (App Router)** for streaming UI and layout management
- **Tailwind CSS + Radix UI** for accessible components
- **SWR** for cache-aware data fetching
- **Zod** for shared validation (mirrors backend schemas)
- **Server-Sent Events (SSE)** client for real-time agent updates

### LLM & Embeddings

- Default embeddings: `sentence-transformers/all-MiniLM-L6-v2`
- Optional remote providers: OpenAI (`text-embedding-3-small`, `gpt-4o-mini`), Anthropic (`claude-3-haiku`)
- Reranker toggle for cross-encoder experiments via `RERANKER_ENABLED`

## Data Flow

1. **Authentication** — User selects a tenant, receiving a scoped JWT.
2. **Conversation Start** — A user message is persisted with metadata (strategy, thresholds).
3. **Agent Execution**
   - Intent classifier predicts action vs. informational queries.
   - Retrieval stack gathers tenant-filtered context from Qdrant and Postgres.
   - Planner chooses a tool (e.g., `create_task`) or composes a grounded response.
4. **Streaming Response** — SSE emits status, intent, context, action, and final answer events to the UI.
5. **Persistence & Observability** — Query record stores provider, latency, guardrail info, retrieved sources, and token estimates.

```
User Prompt → FastAPI Agent Endpoint → Intent & Strategy Service
    → Retrieval Service (Qdrant + Postgres) → Tool Execution (optional)
    → Guardrail Reporter → StreamingResponse → Frontend Conversation UI
    → Query & Conversation Persistence
```

## Deployment Topology

Docker Compose defines the local topology:

| Service    | Purpose                                               |
|------------|-------------------------------------------------------|
| `api`      | FastAPI application with autoreload                    |
| `frontend` | Next.js dev server                                     |
| `postgres` | Primary relational database                            |
| `redis`    | Cache for retrieval responses and session metadata     |
| `qdrant`   | Vector store for document embeddings                   |

_Background workers for long-running ingest and evaluation jobs are part of the roadmap; run scripts manually until that land._

## Development Workflow

- **Backend:** `make backend-dev` launches uvicorn with autoreload and watches for Alembic migrations. Ruff & mypy guard code quality.
- **Frontend:** `pnpm dev` starts the Next.js dev server with HMR. ESLint, TypeScript, and Prettier enforce standards.
- **Testing:** `make test` bundles backend pytest suites and frontend Vitest specs (planned).
- **Seeding:** `python -m app.scripts.seed_data --reset` hydrates tenants, documents, tasks, and incidents.

## Key Design Decisions

- **Single database per deployment** with tenant isolation via foreign keys and SQLAlchemy query filters.
- **Vector isolation by metadata** instead of per-tenant collections to simplify maintenance and support cross-tenant analytics experiments.
- **Guardrail transparency** by streaming structured events that the UI can render in side panels before results are committed.
- **Extensible tools** with a planner registry so new task or incident workflows can be dropped in without retraining the base model.
