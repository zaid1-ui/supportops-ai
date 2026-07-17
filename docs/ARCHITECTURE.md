# SupportOps AI — Enterprise Architecture

**Customer Support Operations Platform**
A multi-agent AI platform that triages, researches, resolves, validates, and escalates customer support tickets — with a human always in the loop before anything reaches a customer.

---

## 1. Problem Statement

Enterprise support organisations are bottlenecked by human throughput, not by human ability. In a typical mid-size SaaS support desk:

- **60–70% of tickets are repeat questions** already answered in the knowledge base, release notes, or a closed ticket from three months ago. Agents re-derive the same answer dozens of times.
- **Knowledge is fragmented** across a KB portal, PDF runbooks, engineering docs, and the ticket history itself. No single search surface spans them.
- **Triage is manual and inconsistent.** Severity and routing depend on which human picks up the ticket, causing SLA breaches on tickets that were misclassified at minute zero.
- **Escalation is reactive.** Nobody notices a ticket is heading for an SLA breach or a churn risk until it already has.
- **Quality is unmeasured.** There is no systematic check that an answer sent to a customer is grounded in real documentation and compliant with refund/policy rules.

A single LLM chatbot does not solve this. Answering a ticket correctly requires *decomposition*: classify → retrieve evidence → diagnose root cause → decide an action → verify the action is grounded and policy-compliant → get human sign-off → execute → record. Each of those is a different job with a different failure mode, a different tool set, and a different definition of "correct."

**That decomposition is the argument for a multi-agent system**, not a stylistic preference.

---

## 2. Enterprise Use Case

SupportOps AI operates as an **AI support organisation** sitting behind the human support team. It does not replace agents; it does the retrieval, drafting, and analysis work and hands humans a decision instead of a blank text box.

Scope of automation:

| Capability | Before | With SupportOps AI |
|---|---|---|
| Ticket triage | Manual, inconsistent | Automatic classification: intent, severity, product area, routing queue |
| Answer research | Human searches 4 systems | RAG across KB + runbooks + ticket history, with citations |
| Root cause analysis | Tribal knowledge | Diagnostic agent correlates symptoms with known issues |
| Response drafting | From scratch | Drafted, cited, policy-checked |
| Quality control | Spot checks | Every response passes a Validation agent before a human sees it |
| Escalation | Reactive | Proactive SLA/sentiment/churn risk scoring |
| Knowledge upkeep | Never | Knowledge Gap workflow finds what the KB is missing |
| Reporting | Manual spreadsheets | Generated RCA and ops reports |

---

## 3. Target Users

| User | Role in the system | What they need |
|---|---|---|
| **Tier-1 Support Agent** | Primary operator. Receives drafted, cited responses; approves, edits, or rejects. | Speed. Trust. One-click approve. Visible citations. |
| **Tier-2 / Escalation Engineer** | Receives escalated tickets with the full agent trace and diagnostic hypothesis attached. | Context without re-reading the thread. |
| **Support Team Lead** | Watches the queue, SLA risk, and agent performance. Sets approval thresholds. | Dashboards, override authority, audit trail. |
| **Knowledge Manager** | Owns the KB. Consumes Knowledge Gap reports. | What's missing, what's stale, what's contradictory. |
| **Support Ops / Director** | Consumes analytics: deflection rate, resolution time, agent success rates. | Metrics and reports, not tickets. |
| **Platform Engineer** | Operates the system itself. | Observability, traces, failure rates, config. |

---

## 4. Business Value

**Quantified target outcomes** (the metrics the Observability layer in Part 12 actually tracks):

- **Time-to-first-response ↓** — Draft ready in <60s vs. ~20 min human research time.
- **Deflection rate ↑** — Repeat questions answered from the KB without a human writing prose.
- **SLA breach rate ↓** — Escalation Risk workflow surfaces at-risk tickets before breach, not after.
- **Answer quality ↑ and *measurable*** — Every response carries citations; the Validation agent gates on groundedness. Retrieval accuracy and hallucination rate become tracked numbers rather than vibes.
- **Knowledge base coverage ↑** — Gap reports turn unresolved tickets into a prioritised content backlog.
- **Audit compliance** — Every automated action has a trace: which agent, which prompt, which retrieved chunk, which human approved it.

**The value thesis:** humans stay in the decision seat, agents absorb the retrieval and drafting labour. Approval throughput becomes the constraint instead of research throughput.

---

## 5. System Architecture

### 5.1 Layered View

```
┌──────────────────────────────────────────────────────────────────────┐
│  PRESENTATION — Next.js 14 (App Router) + Tailwind + TanStack Query  │
│  Dashboard · Agent Monitor · Workflows · Documents · Search ·        │
│  Chat Workspace · Analytics · Approval Inbox (HITL)                  │
└───────────────────────────────┬──────────────────────────────────────┘
                                │ REST + SSE (streaming agent events)
┌───────────────────────────────▼──────────────────────────────────────┐
│  API — FastAPI                                                       │
│  Auth (JWT/OAuth2) · Pydantic validation · RBAC · Rate limit ·       │
│  Structured logging · Error envelope · OpenAPI                       │
└───────────────────────────────┬──────────────────────────────────────┘
                                │
┌───────────────────────────────▼──────────────────────────────────────┐
│  ORCHESTRATION — CrewAI                                              │
│  Crews · Tasks · Sequential + Hierarchical process · Manager LLM ·   │
│  Delegation · Callbacks → event bus · Retry / fallback policy        │
└──────┬──────────────────┬──────────────────┬─────────────────────────┘
       │                  │                  │
┌──────▼──────┐  ┌────────▼────────┐  ┌──────▼──────────┐
│ AGENT LAYER │  │ CONTEXT ENGINE  │  │ HITL ENGINE     │
│ 7 agents    │  │ short/long-term │  │ approval gates  │
│ (Part 2)    │  │ user/task/ent.  │  │ pause + resume  │
└──────┬──────┘  └────────┬────────┘  └──────┬──────────┘
       │                  │                  │
┌──────▼──────────────────▼──────────────────▼─────────────────────────┐
│  TOOL / MCP LAYER — 5 MCP servers exposed as CrewAI tools            │
│  knowledge_retrieval · ticket_db · email · analytics · report_gen    │
└──────┬───────────────────────────────────────────────┬───────────────┘
       │                                               │
┌──────▼──────────────┐  ┌──────────────────┐  ┌───────▼──────────────┐
│ RAG PIPELINE        │  │ PERSISTENCE      │  │ OBSERVABILITY        │
│ ingest → chunk →    │  │ SQLAlchemy ORM   │  │ event store · traces │
│ embed → ChromaDB    │  │ (SQLite engine)  │  │ metrics · eval runs  │
│ → dense retrieve    │  │ (tickets, users, │  │                      │
│ → cite              │  │  runs, approvals)│  │                      │
└─────────────────────┘  └──────────────────┘  └──────────────────────┘
```

### 5.2 Component Responsibilities

| Component | Technology | Responsibility |
|---|---|---|
| Frontend | Next.js 14, TypeScript, Tailwind, TanStack Query | Operator UI, SSE consumption for live agent traces |
| API Gateway | FastAPI, Pydantic v2, python-jose | Contract enforcement, authn/authz, request lifecycle |
| Orchestrator | CrewAI | Crew assembly, task graph, delegation, state handoff |
| LLM Framework | LangChain | LLM abstraction, embeddings, document loaders, text splitters |
| Agents | CrewAI `Agent` + prompt library | Domain reasoning, one job each |
| Tools | MCP servers (`mcp` Python SDK) → CrewAI `BaseTool` adapters | Side effects and external reads |
| Vector store | ChromaDB (persistent client) | Dense retrieval over enterprise knowledge |
| Relational store | SQLAlchemy 2.0 (SQLite) | Tickets, users, workflow runs, approvals, events, feedback |
| Observability | Event table + structured JSON logs + `/metrics` | Agent success, retrieval accuracy, tool usage, failures |

### 5.3 Why These Choices

- **CrewAI over LangGraph** — the workflows here are *role-shaped* (a triage person, a researcher, a QA reviewer), not arbitrary state machines. CrewAI's role/goal/backstory abstraction maps directly onto how a real support org is structured, and its hierarchical process gives task delegation for free. Trade-off accepted: less fine-grained control over state transitions than LangGraph, mitigated by an explicit `WorkflowState` object passed through task context.
- **Dense retrieval only** — Part 6 requires vector search and citations. Hybrid retrieval (BM25 + reciprocal rank fusion) and cross-encoder reranking are the known next lever on retrieval accuracy, but they are a scaling path, not implemented here: each adds a dependency and a failure mode, and neither earns its keep until the retrieval metrics in Part 12 show dense search missing.
- **ChromaDB over FAISS** — needs metadata filtering (`product_area`, `doc_type`, `version`, `updated_at`) at query time for scoped retrieval, and persistence without hand-rolling an index sidecar. FAISS is faster at raw ANN but has no native metadata filter or persistence story.
- **SQLAlchemy (SQLite backend)** — the ORM is the contract; the engine URL is a single config value, so the same models run on SQLite locally and on any server engine later without code changes. JSON columns hold agent traces and workflow state snapshots. Keeps the reproducible setup the assessment requires to one `pip install` with no database server to provision.
- **Next.js over Streamlit** — the deliverable must "resemble an enterprise platform rather than a chatbot." Streamlit cannot express an approval inbox, a live agent trace, and a metrics dashboard as coherent product surfaces.

---

## 6. Data Flow

### 6.1 Ingestion Flow (knowledge enters the system)

```
Upload (PDF/DOCX/TXT)
   │
   ├─► Store raw → data/uploads/  +  documents row (SQLAlchemy)
   │
   ├─► Loader        PyPDFLoader / Docx2txtLoader / TextLoader
   │
   ├─► Normalise     strip boilerplate, collapse whitespace, keep page/heading map
   │
   ├─► Chunk         RecursiveCharacterTextSplitter, 800 tokens / 120 overlap,
   │                 heading-aware split points  (justified in RAG.md)
   │
   ├─► Enrich        metadata: doc_id, source, page, heading, product_area,
   │                 doc_type, version, updated_at
   │
   ├─► Embed         text-embedding-3-small  (batch)   [justified in RAG.md]
   │
   └─► Upsert        ChromaDB collection `enterprise_knowledge`
                     + chunks row (SQLAlchemy) for citation resolution
```

### 6.2 Query Flow (a question gets answered)

```
Question
   │
   ├─► Context Engine assembles:
   │     short-term (last N turns, compressed)
   │     user       (DB: role, permissions, team)
   │     task       (current workflow state)
   │     enterprise (retrieval, below)
   │
   ├─► Retrieval:
   │     embed query ─► Chroma dense search, metadata-filtered
   │                    by product_area / doc_type ─► top-5
   │
   ├─► Context assembly under token budget (priority order, then compress)
   │
   ├─► Agent reasoning (CrewAI task)
   │
   ├─► Validation agent: groundedness + policy check against retrieved chunks
   │
   └─► Response + citations [doc_id, page, chunk_id, score]
```

### 6.3 Write Flow (the system changes something)

Every side effect goes through an MCP tool, and every MCP tool call is recorded in the `events` table **before and after** execution. Customer-visible writes (email send, refund, ticket status change) are additionally gated by an approval record. No agent can write to a customer without a row in `approvals` with `status='approved'` and a `human_user_id`.

---

## 7. Agent Flow

### 7.1 The Crew

| # | Agent | One-line job |
|---|---|---|
| 1 | **Triage Agent** | Classify and route: intent, severity, product area, queue |
| 2 | **Research Agent** | Find grounded evidence via RAG + ticket history |
| 3 | **Diagnostic Agent** | Form a root-cause hypothesis from symptoms + evidence |
| 4 | **Resolution Agent** | Decide the action and draft the customer response |
| 5 | **Validation Agent** | Gate: is it grounded, policy-compliant, and complete? |
| 6 | **Escalation Agent** | Detect SLA/sentiment/churn risk; route to a human tier |
| 7 | **Reporting Agent** | Produce RCA reports, gap reports, ops summaries |

Full responsibilities / inputs / outputs / tools / prompts / failure modes → `docs/AGENTS.md` (Part 2).

### 7.2 Primary Workflow — Ticket Resolution

```
        ┌──────────────┐
Ticket ─►│  1. TRIAGE   │ intent, severity, product_area, confidence
        └──────┬───────┘
               │
      confidence < 0.6 ────────────────────────────► HUMAN TRIAGE REVIEW
               │                                              │
               ▼                                              ▼
        ┌──────────────┐                              (corrected label)
        │ 2. RESEARCH  │ ◄──── knowledge_retrieval_mcp ───────┘
        └──────┬───────┘       ticket_db_mcp (similar past tickets)
               │ evidence[] + citations[]
      no evidence found ──────────────► KNOWLEDGE GAP flag ──► Reporting
               │
               ▼
        ┌──────────────┐
        │3. DIAGNOSTIC │ root-cause hypothesis + confidence
        └──────┬───────┘
               │
               ▼
        ┌──────────────┐
        │4. RESOLUTION │ action plan + drafted response (cited)
        └──────┬───────┘
               │
               ▼
        ┌──────────────┐   FAIL (max 2 retries)
        │5. VALIDATION │──────────► back to Resolution with critique
        └──────┬───────┘            3rd failure ──► Escalation
               │ PASS
               ▼
        ┌──────────────┐
        │6. ESCALATION │ risk score. high risk ──► Tier-2 queue
        └──────┬───────┘
               │ low risk
               ▼
        ╔══════════════╗
        ║  HUMAN GATE  ║  approve / edit / reject   ◄── mandatory
        ╚══════┬═══════╝
               │ approved
               ▼
        ┌──────────────┐
        │   EXECUTE    │ email_mcp.send + ticket_db_mcp.update
        └──────┬───────┘
               │
               ▼
        ┌──────────────┐
        │ 7. REPORTING │ log outcome → analytics + eval corpus
        └──────────────┘
```

### 7.3 Orchestration Mechanics (CrewAI)

- **Process:** `Process.hierarchical` for Ticket Resolution — a manager LLM delegates and can re-dispatch to Research if Validation rejects for missing evidence. `Process.sequential` for the two batch workflows.
- **Agent communication:** typed `WorkflowState` (Pydantic) passed via CrewAI task `context`; agents never free-text at each other. Each task declares `output_pydantic`, so handoffs are schema-validated.
- **Task delegation:** manager agent holds `allow_delegation=True`; workers are `allow_delegation=False` to prevent delegation loops.
- **State management:** authoritative state in the `workflow_runs.state` JSON column, snapshotted after every task via `task_callback`. Enables pause-at-HITL and resume-after-crash.
- **Error recovery:** per-tool retry with exponential backoff → agent-level retry with critique injected → LLM fallback (primary → secondary model) → dead-letter to human queue. No silent failures; every degradation emits an event.

### 7.4 The Other Two Workflows

**Knowledge Gap Review** (scheduled, sequential): pull unresolved/reopened tickets → Research probes the KB for each → Diagnostic clusters the misses → Validation confirms the gap is real (not a retrieval failure) → Reporting emits a prioritised content backlog → human Knowledge Manager approves the backlog.

**Escalation Risk Assessment** (scheduled, sequential): Analytics pulls the open queue → Escalation agent scores each ticket on SLA proximity, sentiment trajectory, reopen count, account tier → Diagnostic explains the drivers → Reporting emits a ranked risk register → human Team Lead triggers interventions.

---

## 8. Scalability Considerations

### 8.1 Where It Breaks First

Ranked by what actually saturates:

1. **LLM tokens/sec and cost** — the real ceiling. A 7-agent run is 15–25 LLM calls.
2. **Long-running runs vs. HTTP** — a run with a human gate can idle for hours.
3. **Vector search latency** at corpus growth.
4. **Database write amplification** from the event stream.

### 8.2 Mitigations

**LLM layer**
- **Model tiering** — Triage and Escalation are classification jobs → small fast model. Diagnostic and Resolution → frontier model. Cuts blended cost materially versus one model everywhere.
- **Semantic caching** — cache keyed on `(normalised_question, product_area, kb_version)`. Repeat questions are the majority of the queue by definition, so cache hit rate is the single biggest cost lever.
- **Prompt caching** on the static system prompt + policy block.
- **Budget guard** — per-run token ceiling; exceeding it escalates to a human rather than looping.

**Execution layer**
- **Workflows are async jobs, not requests.** `POST /workflows/run` returns `202` + `run_id`; Celery worker executes; frontend subscribes to SSE. The API never blocks on a crew.
- **Durable pause/resume at HITL** — state is serialised to the database and the worker releases. Human approval enqueues a resume job. Idle runs consume zero compute.
- **Horizontal workers** — stateless Celery workers; scale on queue depth. Separate queues for interactive (ticket resolution) vs. batch (scheduled reports) so a nightly report run can't starve live tickets.

**Retrieval layer**
- Chroma persistent server mode with HNSW tuned (`M=32`, `ef_construction=200`); metadata pre-filtering shrinks the candidate set before ANN.
- Collection **sharded by `product_area`** — retrieval is almost always scoped, so this cuts search space and blast radius.
- Embeddings computed once at ingest. Query embedding is the only per-query model call, so retrieval cost is flat in corpus size.
- Ingestion is a separate worker pool — a 500-page PDF upload must not affect query latency.

**Data layer**
- SQLite is the development engine and the single-node ceiling. Because persistence goes through the SQLAlchemy ORM, moving to a client/server engine is a `DATABASE_URL` change, not a rewrite — this is the main reason the ORM is the boundary rather than raw SQL.
- `events` is append-only; archive rows past 90 days rather than letting the table grow unbounded.
- Metrics pre-aggregated into a rollup table by a periodic job; the dashboard reads rollups, not raw events.

**Multi-tenancy**
- `tenant_id` on every table and every Chroma metadata record; enforced at the repository layer, not left to callers.
- Per-tenant rate limits and token budgets so one tenant cannot exhaust shared LLM capacity.

### 8.3 Reliability

- **Idempotency keys** on every side-effecting MCP tool — a retried `email.send` must not double-send.
- **Circuit breakers** per external dependency; open circuit → degrade to human queue rather than fail the run.
- **Graceful degradation ladder:** Chroma down → the Research Agent reports a knowledge gap rather than guessing, and the run escalates. LLM primary down → fallback model. All down → tickets queue for humans, and the platform says so plainly.
- **Every run is replayable** from its event stream, which is also what feeds the evaluation harness in Part 13.

---

## 9. Repository Map

```
supportops-ai/
├── backend/          FastAPI app, auth, API routes, services
├── agents/           CrewAI agent definitions + prompt library
├── workflows/        Crew assembly, state machine, HITL gates
├── rag/              ingestion, chunking, embedding, retrieval, citation
├── mcp_tools/        5 MCP servers + CrewAI tool adapters
│                  (named mcp_tools, not mcp: a top-level `mcp/` package
│                   shadows the MCP SDK's own `mcp` package on sys.path)
├── evaluation/       harness, scenarios, benchmark cases
├── frontend/         Next.js 14 platform UI
├── docs/             ARCHITECTURE.md · AGENTS.md · PROMPT_LIBRARY.md
│                     CONTEXT_ENGINEERING.md · RAG.md
│                     EVALUATION_FRAMEWORK.md · DEPLOYMENT.md
└── scripts/          seed, ingest, eval runners
```
