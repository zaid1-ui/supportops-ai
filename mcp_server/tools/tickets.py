"""Ticket-related MCP tools."""

from __future__ import annotations

from sqlalchemy import select

from backend.app.core.database import SessionLocal
from backend.app.models import Ticket, TicketStatus

# Fields an agent may write. Everything else is off limits — an agent must not
# be able to set `status=resolved` and close a ticket without a human, so the
# allowlist is the enforcement, not the prompt.
WRITABLE = {"intent", "severity", "product_area", "queue"}


def register_ticket_tools(mcp):
    @mcp.tool()
    def get_ticket(ticket_id: str) -> dict:
        """Fetch a ticket by id, with its classification and SLA fields."""
        db = SessionLocal()
        try:
            t = db.get(Ticket, ticket_id)
            if t is None:
                return {"ok": False, "error": f"no such ticket: {ticket_id}"}
            return {
                "ok": True,
                "data": {
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
                },
            }
        finally:
            db.close()

    @mcp.tool()
    def find_similar_tickets(
        product_area: str | None = None,
        intent: str | None = None,
        limit: int = 5,
    ) -> dict:
        """Find previously RESOLVED tickets with the same product area or intent.

        Open tickets are excluded — an unresolved ticket is not precedent.
        """
        db = SessionLocal()
        try:
            stmt = select(Ticket).where(Ticket.status == TicketStatus.RESOLVED)
            if product_area:
                stmt = stmt.where(Ticket.product_area == product_area)
            if intent:
                stmt = stmt.where(Ticket.intent == intent)
            rows = db.execute(stmt.order_by(Ticket.updated_at.desc()).limit(limit)).scalars().all()

            if not rows:
                return {
                    "ok": True,
                    "data": {"tickets": [], "note": "No resolved tickets match. Not evidence of absence."},
                }
            return {
                "ok": True,
                "data": {
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
                },
            }
        finally:
            db.close()

    @mcp.tool()
    def update_ticket(ticket_id: str, updates: dict) -> dict:
        """Write a classification back to a ticket.

        Writable fields: intent, severity, product_area, queue.
        Ticket status is not agent-writable.
        """
        db = SessionLocal()
        try:
            t = db.get(Ticket, ticket_id)
            if t is None:
                return {"ok": False, "error": f"no such ticket: {ticket_id}"}

            rejected = set(updates) - WRITABLE
            if rejected:
                return {
                    "ok": False,
                    "error": f"fields not writable by an agent: {sorted(rejected)}. Writable: {sorted(WRITABLE)}",
                }

            for k, v in updates.items():
                setattr(t, k, v)
            db.commit()
            return {"ok": True, "data": {"id": t.id, "updated": sorted(updates)}}
        finally:
            db.close()