# Quickstart

Get the Multi-Tenant RAG & Agentic Operations Assistant running locally in six steps. The process is optimized for fast iteration on multi-tenant retrieval, guardrails, and agent workflows.

## Step 1: Clone the repository

```bash
git clone https://github.com/princeemensah/multi-tenant-rag.git
cd multi-tenant-rag
```

## Step 2: Configure environment variables

### Backend

```bash
cp ./backend/.env.example ./backend/.env
```

Populate the following minimum values:

- `DATABASE_URL=sqlite:///./data/app.db`
- `REDIS_URL=redis://localhost:6379/0`
- `QDRANT_URL=http://localhost:6333`
- `JWT_SECRET_KEY` — any random string for local dev
- `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` — optional, required for LLM responses

### Frontend

```bash
cp ./frontend/.env.example ./frontend/.env.local
```

Set `NEXT_PUBLIC_BACKEND_URL=http://localhost:8000`.

> **Tip:** The provided example files include sensible defaults. Update them only when pointing to remote infrastructure.

## Step 3: Start core services

Spin up Postgres, Redis, and Qdrant with Docker Compose (swap with managed services as needed):

```bash
make docker-up-infra
# or
docker compose up -d postgres redis qdrant
```

When using Docker, set backend environment variables to target the containers:
- `DATABASE_URL=postgresql+psycopg://rag:rag@postgres:5432/rag`
- `REDIS_URL=redis://redis:6379/0`
- `QDRANT_HOST=qdrant`, `QDRANT_PORT=6333`

## Step 4: Install dependencies

```bash
make install
```

Creates/updates `.venv` and installs frontend packages with Yarn.

## Step 5: Start application servers

```bash
make backend-dev
make frontend-dev
```

The backend runs at http://localhost:8000 and the frontend at http://localhost:3000.

## Step 6: Seed sample data (optional)

Use the built-in script to create demo tenants, documents, tasks, and incidents:

```bash
make seed
```

Flags:

- `--skip-docs` — omit document ingestion when Qdrant is offline
- `--tenant acme-health` — seed a single tenant

## Step 7: Verify the deployment

1. Open http://localhost:3000 and sign in with the seeded admin user (`ops-admin@acmehealth.example` / `ChangeMe!123`).
2. Select a tenant from the left navigation.
3. Start a conversation and send a prompt. You should see:
   - Streaming assistant response
   - Guardrail warnings when intent confidence is low
   - Retrieved context snippets and executed tool summaries
4. Inspect http://localhost:8000/docs for interactive API exploration.

## Next steps

- Review the [System Overview](architecture/system-overview.md) for architecture details.
- Follow the [Operations Guide](operations.md) to manage tenants, documents, and scheduled jobs.
- Run the [Evaluation Playbook](evaluation.md) to benchmark retrieval quality in your domain.
