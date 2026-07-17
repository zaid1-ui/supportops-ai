"""Email MCP server (Part 7).

The only tool that can reach a customer, and therefore the one place where the
human-in-the-loop guarantee is actually enforced rather than merely intended.

Two rules, both structural:

1. `send_email` refuses unless an APPROVED or EDITED RESPONSE_APPROVAL row
   exists for the run. Not a prompt instruction — a database check. An agent
   cannot reason its way past it, and neither can a prompt injection in a
   ticket body.
2. Sends are idempotent on run_id. A retried send after a timeout must not
   deliver twice; the customer sees one email regardless of how the transport
   misbehaves.
"""

from __future__ import annotations

import asyncio

import mcp.types as types
from mcp.server import Server
from sqlalchemy.orm import Session

from backend.app.core.logging import get_logger
from backend.app.models import ApprovalKind, EventType
from mcp_tools.core import ToolResult, fail, ok

logger = get_logger(__name__)

TOOL_DRAFT = "draft_email"
TOOL_SEND = "send_email"

# Idempotency ledger, keyed by run_id. A real deployment puts this in the
# database; the point being demonstrated is that the key is the run, so a retry
# is recognised as the same send.
_SENT: dict[str, dict] = {}


def draft_email(to: str, subject: str, body: str) -> ToolResult:
    """Compose an email. Never sends. Safe for an agent to call freely."""
    if not to or "@" not in to:
        return fail(f"invalid recipient: {to!r}")
    if not body.strip():
        return fail("body is empty")
    return ok(
        {
            "to": to,
            "subject": subject,
            "body": body,
            "status": "drafted",
            "note": "Not sent. Sending requires human approval.",
        }
    )


def send_email(
    db: Session,
    run_id: str,
    to: str,
    subject: str,
    body: str,
) -> ToolResult:
    """Send — only with a cleared approval gate for this run."""
    # Imported here: workflows imports mcp_tools for its registry, so a
    # module-level import would close the cycle.
    from workflows.hitl import ApprovalGate
    from workflows.state import StateStore

    store = StateStore(db)
    gate = ApprovalGate(db, store)

    if not gate.is_cleared(run_id, ApprovalKind.RESPONSE_APPROVAL):
        store.emit(
            run_id,
            EventType.TOOL_FAILED,
            tool="email.send",
            payload={"reason": "no approved RESPONSE_APPROVAL"},
        )
        return fail(
            "Refused: no approved RESPONSE_APPROVAL for this run. "
            "Every customer-facing send requires human approval."
        )

    if run_id in _SENT:
        # Idempotent replay. Report it rather than pretending it is a new send,
        # so a caller retrying in a loop can tell.
        return ok({**_SENT[run_id], "status": "already_sent", "idempotent": True})

    # Transport boundary. A real deployment calls SMTP or a provider API here.
    record = {"to": to, "subject": subject, "body": body, "run_id": run_id}
    _SENT[run_id] = record
    store.emit(run_id, EventType.TOOL_CALLED, tool="email.send", payload={"to": to})
    logger.info("email sent for run %s to %s", run_id, to)
    return ok({**record, "status": "sent"})


server = Server("supportops-email")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name=TOOL_DRAFT,
            description="Compose an email without sending it.",
            inputSchema={
                "type": "object",
                "properties": {
                    "to": {"type": "string"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["to", "subject", "body"],
            },
        ),
        types.Tool(
            name=TOOL_SEND,
            description=(
                "Send an email. Requires an approved RESPONSE_APPROVAL for the run. "
                "Idempotent on run_id."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "run_id": {"type": "string"},
                    "to": {"type": "string"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["run_id", "to", "subject", "body"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    from backend.app.core.database import SessionLocal

    if name == TOOL_DRAFT:
        result = draft_email(arguments["to"], arguments["subject"], arguments["body"])
    elif name == TOOL_SEND:
        db = SessionLocal()
        try:
            result = send_email(
                db,
                arguments["run_id"],
                arguments["to"],
                arguments["subject"],
                arguments["body"],
            )
        finally:
            db.close()
    else:
        result = fail(f"unknown tool: {name}")
    return [types.TextContent(type="text", text=result.to_text())]


async def main() -> None:
    from mcp.server.stdio import stdio_server

    async with stdio_server() as (r, w):
        await server.run(r, w, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
