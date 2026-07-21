# SupportOps AI

**Customer Support Operations Platform** — a multi-agent AI platform that triages, researches, resolves, validates, and escalates customer support tickets, with human approval before any customer-facing action.

Assessment 3: Enterprise AI Operations Platform (Multi-Agent Systems & Agent Engineering)

---

## Stack

| Layer | Technology |
|---|---|
| Agent framework | CrewAI |
| LLM framework | LangChain |
| Backend | FastAPI |
| Frontend | Next.js 14 |
| Vector database | ChromaDB (persistent local client) |
| Database | SQLAlchemy (SQLite engine) |
| Tools | MCP servers |

---

## Repository Structure

```
supportops-ai/
├── backend/          FastAPI app (api, core, models, schemas, services)
├── frontend/         Next.js 14 platform UI
├── agents/           CrewAI agent definitions + prompts
├── workflows/        Crew assembly, state, human-in-the-loop gates
├── rag/              Ingestion, chunking, embedding, retrieval
├── mcp_tools/        MCP servers + tool adapters
├── evaluation/       Evaluation harness + test scenarios
├── docs/             ARCHITECTURE.md, AGENTS.md, PROMPT_LIBRARY.md, ...
└── README.md
```

---

## Setup

### Prerequisites

- Python 3.12+
- Node 22+
- (Optional) Docker + Docker Compose

No database server is required — SQLAlchemy runs on a SQLite file and ChromaDB runs as a persistent local client. Both are created automatically on first start.

### 1. Configure

```bash
git clone <repo-url>
cd supportops-ai
cp .env.example .env
```

Edit `.env` and set at minimum:

- `OPENAI_API_KEY`
- `JWT_SECRET_KEY`

### 2. Backend

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn backend.app.main:app --reload
```

Verify:

```bash
curl http://localhost:8000/health
# {"status":"ok","environment":"development"}
```

### 3. Seed demo data

```bash
python -m scripts.seed
```

Creates four users (one per role) and three sample tickets. Log in as
`lead@example.com` / `lead123` — the lead role can decide every approval kind.

### 4. Frontend

```bash
cd frontend
npm install
npm run dev
```

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| Backend | http://localhost:8000 |
| API docs | http://localhost:8000/docs |

### 5. Run with Docker (alternative)

```bash
docker compose up --build
```

---

## Documentation

| Document | Covers |
|---|---|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Problem statement, use case, users, business value, system architecture, data flow, agent flow, scalability |
| [`docs/AGENTS.md`](docs/AGENTS.md) | Agent responsibilities, inputs, outputs, tools, prompts, failure modes |
| [`docs/PROMPT_LIBRARY.md`](docs/PROMPT_LIBRARY.md) | System, task, validation, routing, escalation prompts |
| [`docs/CONTEXT_ENGINEERING.md`](docs/CONTEXT_ENGINEERING.md) | Context sources, prioritisation, compression, retrieval |
| [`docs/RAG.md`](docs/RAG.md) | Ingestion, chunking, embeddings, vector search, citations |
| `docs/EVALUATION_FRAMEWORK.md` | Agent, tool, retrieval, workflow, response quality evaluation |
| `docs/DEPLOYMENT.md` | Deployment architecture |

---

## Build Status

| Part | Status |
|---|---|
| 1. Enterprise Architecture Design | Done |
| 2. Multi-Agent System Design | Done |
| 3. Agent Orchestration | Done |
| 4. Prompt Engineering | Done |
| 5. Context Engineering | Done |
| 6. RAG | Done |
| 7. MCP Servers & Tools | Done (5 servers) |
| 8. Automated Workflows | Done (3 workflows) |
| 9. Human-in-the-Loop | Done |
| 10. FastAPI Backend | Done |
| 11. Frontend Platform | Done (8 modules) |
| 12. Observability & Evaluation | Partial (events + /metrics) |
| 13. Evaluation Harness | Pending |
| 14. Deployment | Docker Compose done |
| 15. GitHub Requirements | Structure done |
