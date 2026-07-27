"""Ticket-related MCP tools."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from mcp_server.config import config
from backend.app.models import Ticket

engine = create_engine(config.database_url)
SessionLocal = sessionmaker(bind=engine)


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
                },
            }
        finally:
            db.close()