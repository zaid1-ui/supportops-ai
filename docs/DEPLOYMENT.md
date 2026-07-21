# Deployment

**Files:** `docker-compose.yml`, `backend/Dockerfile`, `frontend/Dockerfile`

This document covers the deployment architecture and how to run the platform in containers. The design goal is a **reproducible local deployment** — clone, set one env file, `docker compose up`, and the whole platform runs with no external services to provision.

---

## Architecture

```
┌────────────────────────────────────────────────────────┐
│                    docker compose                       │
│                                                        │
│  ┌──────────────┐          ┌──────────────────────┐   │
│  │  frontend    │          │      backend         │   │
│  │  Next.js 15  │──REST───▶│      FastAPI         │   │
│  │  :3000       │          │      :8000           │   │
│  └──────────────┘          │                      │   │
│                            │  ┌────────────────┐  │   │
│                            │  │  SQLite  (DB)  │  │   │
│                            │  │  ChromaDB      │  │   │
│                            │  │  fastembed     │  │   │
│                            │  └───────┬────────┘  │   │
│                            └──────────┼───────────┘   │
│                                       │               │
│                            ┌──────────▼───────────┐   │
│                            │  ./data  (volume)    │   │
│                            │  db + vectors + docs │   │
│                            └──────────────────────┘   │
└────────────────────────────────────────────────────────┘
                            │
                            ▼
                   external LLM API
              (Gemini / OpenAI / xAI …)
```

**Two services, one volume, one external dependency.** The only thing outside the compose network is the LLM provider. Everything else — relational store, vector store, embeddings — runs in-process in the backend container. This is the payoff of the SQLite and local-embeddings decisions (`ARCHITECTURE.md`, `RAG.md`): there is no Postgres container, no Redis, no separate vector-database service, and no embedding API to key.

---

## Services

### backend

`python:3.12-slim`. Installs `requirements.txt`, copies the application packages, seeds the database on first boot, and serves FastAPI with uvicorn.

- **Port** 8000
- **Volume** `./data` → `/app/data` holds the SQLite file, the Chroma collection, and uploaded documents. Persisting it means state survives a container restart.
- **Healthcheck** hits `/health`; the frontend waits on it (`depends_on: condition: service_healthy`) so it never starts against a backend that isn't ready.
- **Seed on boot** runs `scripts.seed` with `|| true`, so a redeploy against an already-seeded volume doesn't abort.

The `PYTHONPATH=/app` env var is what lets the `backend.app.*`, `agents.*`, `mcp_tools.*` imports resolve — the same reason the app must be run from the repo root locally.

### frontend

Multi-stage `node:22-alpine` build: install deps, `next build`, then a minimal runner serving the standalone output.

- **Port** 3000
- **Build arg** `NEXT_PUBLIC_API_URL`. This matters: Next.js inlines `NEXT_PUBLIC_*` variables **at build time**, not runtime, so the backend URL must be present when `next build` runs. Passing it as a runtime env var alone would leave the compiled bundle pointing at `undefined`. It is threaded through compose → Dockerfile `ARG` → `ENV` → build.
- Uses `output: 'standalone'` (in `next.config.js`), which produces a self-contained server bundle with only the needed `node_modules`, keeping the runtime image small.

---

## Running It

### Prerequisites

- Docker and Docker Compose
- An LLM API key (Gemini's free tier needs no card — see below)

### Steps

```bash
cp .env.example .env
# edit .env: set LLM_API_KEY, LLM_MODEL, and a JWT_SECRET_KEY
docker compose up --build
```

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| Backend | http://localhost:8000 |
| API docs | http://localhost:8000/docs |

Sign in with a seeded account — `lead@example.com` / `lead123`.

### Configuration

Everything is environment-driven (`.env`); nothing is hardcoded. The essentials:

```bash
LLM_API_KEY=...                      # your provider key
LLM_MODEL=gemini/gemini-3.1-flash-lite   # must carry a provider/ prefix
EMBEDDING_PROVIDER=local             # fastembed; no key, no network
JWT_SECRET_KEY=<a long random string>
```

The `LLM_MODEL` prefix (`gemini/`, `openai/`, `xai/`) is required — litellm routes on it. `EMBEDDING_PROVIDER=local` keeps embeddings on-device, so retrieval needs no second key and no data leaves the container.

---

## Why This Isn't a Cloud Deployment

The platform is packaged for reproducible local deployment, not a hosted URL. Two honest reasons:

1. **fastembed downloads a model and ChromaDB carries native deps**, which makes the backend image large enough that most free hosting tiers (with tight image-size and cold-start limits) would struggle. A real hosted deployment would move embeddings to a hosted API or a dedicated vector service.
2. **SQLite is single-node by design.** It is the right choice for a reproducible, self-contained deployment and the wrong choice for a horizontally-scaled hosted one. The migration path is a `DATABASE_URL` change (the ORM is the boundary — `ARCHITECTURE.md §8.2`), not a rewrite.

The scaling story — async workers for long runs, a rollup table for metrics, a client/server database and vector service, per-tenant isolation — is documented in `ARCHITECTURE.md §8`. None of it is built here, because none of it is what "reproducible setup" asks for, and building it unprompted would trade the one-command local run for complexity the assessment doesn't require.

---

## Production Checklist (not done here, documented for completeness)

If this were going to a real environment, the changes would be:

- `DATABASE_URL` → a client/server engine; run migrations rather than `create_all`.
- Embeddings → a hosted API or dedicated service; vector store → managed.
- Long workflow runs → an async worker queue, so `POST /workflows/run` returns immediately (already returns `202`; the executor would move off the request thread).
- Secrets → a secrets manager, not `.env`.
- `JWT_SECRET_KEY` → rotated, not static.
- CORS, rate limits, and per-tenant token budgets tightened for real traffic.
- Metrics → the rollup table; logs → a real aggregator.

Each of these is a known, bounded change with a place already prepared for it in the architecture, which is the point of documenting them rather than half-building them.
