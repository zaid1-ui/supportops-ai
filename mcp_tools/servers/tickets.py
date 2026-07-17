"""Ticket Database MCP server (Part 7).

Reads and updates tickets. Used by Triage (write classification), Research
(find similar resolved tickets), and Escalation (queue state).
"""

from __future__ import annotations

import asyncio

import mcp.types as types
from mcp.server import Server
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import Ticket, TicketStatus
from mcp_tools.core import ToolResult, fail, ok

TOOL_GET = "get_ticket"
TOOL_SIMILAR = "find_similar_tickets"
TOOL_UPDATE = "update_ticket"

# Fields an agent may write. Everything else is off limits — an agent must not
# be able to set `status=resolved` and close a ticket without a human, so the
# allowlist is the enforcement, not the prompt.
WRITABLE = {"intent", "severity", "product_area", "queue"}


def get_ticket(db: Session, ticket_id: str) -> ToolResult:
    t = db.get(Ticket, ticket_id)
    if t is None:
        return fail(f"no such ticket: {ticket_id}")
    return ok(
        {
            "id": t.id,
            "subject": t.subject,
            "body": t.body,
            "status": t.status.value,
            "account_tier": t.account_tier,
            "intent": t.intent,
            "severity": t.severity,
            "product_area": t.product_area,
            "queue": t.queue,
            "reopen_count": t.reopen_count,
            "message_count": t.message_count,
            "sla_hours": t.sla_hours,
            "created_at": t.created_at,
        }
    )


def find_similar_tickets(
    db: Session,
    product_area: str | None = None,
    intent: str | None = None,
    limit: int = 5,
) -> ToolResult:
    """Resolved tickets matching this shape.

    Deliberately restricted to RESOLVED tickets. An open ticket with the same
    symptoms is not evidence of anything — nobody has established that its
    stated cause is correct yet, and surfacing it as precedent would let one
    wrong diagnosis propagate across every similar ticket that follows.
    """
    stmt = select(Ticket).where(Ticket.status == TicketStatus.RESOLVED)
    if product_area:
        stmt = stmt.where(Ticket.product_area == product_area)
    if intent:
        stmt = stmt.where(Ticket.intent == intent)
    rows = db.execute(stmt.order_by(Ticket.updated_at.desc()).limit(limit)).scalars().all()

    if not rows:
        return ok({"tickets": [], "note": "No resolved tickets match. Not evidence of absence."})
    return ok(
        {
            "tickets": [
                {
                    "id": t.id,
                    "subject": t.subject,
                    "severity": t.severity,
                    "product_area": t.product_area,
                    "resolved_at": t.updated_at,
                }
                for t in rows
            ]
        }
    )


def update_ticket(db: Session, ticket_id: str, updates: dict) -> ToolResult:
    t = db.get(Ticket, ticket_id)
    if t is None:
        return fail(f"no such ticket: {ticket_id}")

    rejected = set(updates) - WRITABLE
    if rejected:
        return fail(
            f"fields not writable by an agent: {sorted(rejected)}. Writable: {sorted(WRITABLE)}"
        )

    for k, v in updates.items():
        setattr(t, k, v)
    db.commit()
    return ok({"id": t.id, "updated": sorted(updates)})


server = Server("supportops-tickets")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name=TOOL_GET,
            description="Fetch a ticket by id.",
            inputSchema={
                "type": "object",
                "properties": {"ticket_id": {"type": "string"}},
                "required": ["ticket_id"],
            },
        ),
        types.Tool(
            name=TOOL_SIMILAR,
            description="Find resolved tickets with the same product area or intent.",
            inputSchema={
                "type": "object",
                "properties": {
                    "product_area": {"type": "string"},
                    "intent": {"type": "string"},
                    "limit": {"type": "integer", "default": 5},
                },
            },
        ),
        types.Tool(
            name=TOOL_UPDATE,
            description=(
                "Update ticket classification. Writable: intent, severity, "
                "product_area, queue. Ticket status is not agent-writable."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "ticket_id": {"type": "string"},
                    "updates": {"type": "object"},
                },
                "required": ["ticket_id", "updates"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    from backend.app.core.database import SessionLocal

    db = SessionLocal()
    try:
        if name == TOOL_GET:
            result = get_ticket(db, arguments["ticket_id"])
        elif name == TOOL_SIMILAR:
            result = find_similar_tickets(
                db,
                product_area=arguments.get("product_area"),
                intent=arguments.get("intent"),
                limit=arguments.get("limit", 5),
            )
        elif name == TOOL_UPDATE:
            result = update_ticket(db, arguments["ticket_id"], arguments["updates"])
        else:
            result = fail(f"unknown tool: {name}")
    finally:
        db.close()
    return [types.TextContent(type="text", text=result.to_text())]


async def main() -> None:
    from mcp.server.stdio import stdio_server

    async with stdio_server() as (r, w):
        await server.run(r, w, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
