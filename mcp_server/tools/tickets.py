"""Ticket-related MCP tools.

Core logic is db-taking plain functions (get_ticket, update_ticket,
find_similar_tickets) — callable directly by the evaluation harness without
a live MCP server. register_ticket_tools wraps each in a @mcp.tool() that
opens its own session, for real agents talking over the protocol.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.database import SessionLocal
from backend.app.models import Ticket, TicketStatus
from mcp_server.core import ToolResult, fail, ok

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
            "created_at": str(t.created_at),
        }
    )


def find_similar_tickets(
    db: Session,
    product_area: str | None = None,
    intent: str | None = None,
    limit: int = 5,
) -> ToolResult:
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
                    "resolved_at": str(t.updated_at),
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
        return fail(f"fields not writable by an agent: {sorted(rejected)}. Writable: {sorted(WRITABLE)}")

    for k, v in updates.items():
        setattr(t, k, v)
    db.commit()
    return ok({"id": t.id, "updated": sorted(updates)})


def register_ticket_tools(mcp):
    @mcp.tool(name="get_ticket")
    def get_ticket_tool(ticket_id: str) -> dict:
        """Fetch a ticket by id, with its classification and SLA fields."""
        db = SessionLocal()
        try:
            return get_ticket(db, ticket_id).to_dict()
        finally:
            db.close()

    @mcp.tool(name="find_similar_tickets")
    def find_similar_tickets_tool(
        product_area: str | None = None,
        intent: str | None = None,
        limit: int = 5,
    ) -> dict:
        """Find previously RESOLVED tickets with the same product area or intent."""
        db = SessionLocal()
        try:
            return find_similar_tickets(db, product_area, intent, limit).to_dict()
        finally:
            db.close()

    @mcp.tool(name="update_ticket")
    def update_ticket_tool(ticket_id: str, updates: dict) -> dict:
        """Write a classification back to a ticket. Writable: intent, severity, product_area, queue."""
        db = SessionLocal()
        try:
            return update_ticket(db, ticket_id, updates).to_dict()
        finally:
            db.close()