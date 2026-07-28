# MCP Architecture

## Why

The original platform had agents reaching directly into the database, the RAG
index, and email — `mcp_tools/` wrapped that access in CrewAI adapters, but
the wrapping was in-process: an agent import, not a protocol boundary. This
extension replaces that with a standalone FastMCP server. Agents no longer
import tool code; they call tools over the Model Context Protocol, the same
way any external MCP client could.

```
Before                          After

Agent                           Agent
├── Database Query                 │
├── RAG Search                     ▼
└── Report Generation         MCP Server (mcp_server/, standalone process)
                               ├── Ticket Tools
                               ├── Knowledge Tools
                               ├── Email Tools
                               ├── Analytics Tools
                               └── Report Tools
```

## Structure

```
mcp_server/
├── core.py          ToolResult / ok() / fail() — shared envelope
├── config.py         Transport, DB URL (pydantic-settings, extra="ignore")
├── server.py          Entrypoint. FastMCP instance, registers every tool.
│                       Runs standalone: `python -m mcp_server.server`
├── crew_client.py     StdioServerParameters agents connect through
├── registry.py         Per-agent tool allowlist (AGENT_TOOL_NAMES)
├── tools/
│   ├── tickets.py      get_ticket, find_similar_tickets, update_ticket
│   ├── knowledge.py    search_knowledge, get_chunk
│   ├── email.py        draft_email, send_email
│   ├── analytics.py    agent_success_rates, workflow_stats, queue_pressure
│   └── reports.py      render_report
├── resources/
│   └── schemas.py      schema://ticket, policy://sla
└── prompts/
    └── templates.py     classify_ticket, escalation_summary
```

Each tool file separates **core logic** (a plain function taking `db: Session`
explicitly, returning a `ToolResult`) from its **MCP wrapper** (a
`@mcp.tool(name=...)` closure that opens its own `SessionLocal` and calls the
core function). One implementation, two callers: the standalone server for
live agents, and the evaluation harness, which calls the core functions
directly to test tool correctness without spinning up a server subprocess.

## Transport

`stdio`. Each `TicketResolutionWorkflow` (and `EscalationRiskWorkflow`,
`KnowledgeGapWorkflow`) opens its own `MCPServerAdapter`, which spawns
`python -m mcp_server.server` as a subprocess and talks to it over stdin/
stdout. The adapter is opened once per workflow segment and explicitly
closed (`workflow.close()`) in a `finally` block — a paused run awaiting
human approval must not hold a subprocess open for the hours it may sit
idle.

## Tool inventory

| Tool                   | Used by                              | Notes                                                                                  |
| ---------------------- | ------------------------------------ | -------------------------------------------------------------------------------------- |
| `get_ticket`           | triage, escalation                   |                                                                                        |
| `find_similar_tickets` | research                             | Resolved tickets only — an open ticket isn't precedent                                 |
| `update_ticket`        | triage                               | Field allowlist enforced in the tool, not the prompt                                   |
| `search_knowledge`     | research, diagnostic, resolution     | RAG retrieval, cited results                                                           |
| `get_chunk`            | validation                           | Verifies a citation actually says what a draft claims                                  |
| `draft_email`          | resolution                           | Never sends                                                                            |
| `send_email`           | _(none — not assigned to any agent)_ | Refuses without an approved `RESPONSE_APPROVAL`; called post-approval outside the crew |
| `agent_success_rates`  | reporting                            |                                                                                        |
| `workflow_stats`       | reporting                            |                                                                                        |
| `queue_pressure`       | diagnostic, escalation, reporting    | SLA breach/at-risk buckets                                                             |
| `render_report`        | reporting                            | Sanitizes LLM-generated filenames against path traversal                               |

## Resources

- `schema://ticket` — field reference for the Ticket object
- `policy://sla` — the at-risk/breach thresholds `queue_pressure` uses, kept
  next to the tool so the number an agent's prompt is calibrated against
  can't silently drift from the number the tool actually applies

## Prompts

- `classify_ticket` — intent/severity/product_area classification template
- `escalation_summary` — human-facing escalation summary template

Centralizing these on the server means a wording fix happens once, not once
per agent file that inlined the same instruction.

## Per-agent tool assignment

Enforced in `mcp_server/registry.py` (`AGENT_TOOL_NAMES`), not by convention:

| Agent      | Tools                                                              |
| ---------- | ------------------------------------------------------------------ |
| triage     | get_ticket, update_ticket                                          |
| research   | search_knowledge, find_similar_tickets                             |
| diagnostic | search_knowledge, queue_pressure                                   |
| resolution | search_knowledge, draft_email                                      |
| validation | get_chunk _(no search — verification only, not discovery)_         |
| escalation | get_ticket, queue_pressure                                         |
| reporting  | agent_success_rates, workflow_stats, queue_pressure, render_report |

Fewer tools per agent is deliberate: every extra tool is a plausible wrong
choice, and capability should follow role — a validator that can search is a
validator that stops checking the evidence it was given and goes looking for
better evidence instead, which isn't its job.

## Security boundary

Agents cannot reach the database, ChromaDB, or the email system except
through a tool call. `send_email` is the enforcement example: it checks the
database directly for an approved `RESPONSE_APPROVAL` tied to the run before
sending, and refuses otherwise. That check lives in the tool, not in a
prompt instruction an agent could be talked out of.

## Known issues / workarounds

Two Gemini 3.x compatibility issues surfaced integrating live agents against
this server, both worked around in `agents/llm.py`, not fixed at the source
(litellm/CrewAI):

1. **`additionalProperties` schema rejection.** CrewAI's native Gemini SDK
   path rejects the `additionalProperties` key that every MCP-derived tool
   schema includes. Worked around with `is_litellm=True` on the LLM
   constructor, forcing the generic LiteLLM completion path instead of
   CrewAI's Gemini-specific one.

2. **Missing `thought_signature` on multi-turn tool calls.** Gemini 3.x's
   native function-calling API requires a `thought_signature` token to be
   replayed on every subsequent turn of a tool-calling conversation; litellm's
   Vertex/Gemini integration does not currently preserve it, causing a 400 on
   the second tool call in any session. Worked around by forcing
   `llm.supports_function_calling = lambda: False`, which makes CrewAI fall
   back to text-based (ReAct-style) tool calling — the LLM writes which tool
   to call in plain text rather than using Gemini's structured function-
   calling API, sidestepping the bug entirely. Remove this override once
   litellm round-trips `thought_signature` correctly for `gemini/*` models.

Both were confirmed necessary and sufficient by running a full ticket through
`TicketResolutionWorkflow.start()` end to end: triage classified the ticket,
research called `search_knowledge` live through the MCP server, resolution
drafted a response, validation rejected it via `get_chunk`-verified critique,
and the retry loop redrafted — all tool calls crossing the real MCP protocol
boundary, no in-process imports.
