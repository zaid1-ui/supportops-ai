"""Email MCP tools.

The only tools that can reach a customer, and therefore where the
human-in-the-loop guarantee is actually enforced rather than merely intended.

draft_email is safe for any agent to call freely — it never sends.
send_email refuses unless an APPROVED RESPONSE_APPROVAL exists for the run.
That check is a database lookup, not a prompt instruction, so an agent
cannot reason its way past it and neither can a prompt injection in a
ticket body. No agent is assigned send_email in the registry (Phase 4) —
it's called post-approval, outside the crew.
"""

from __future__ import annotations

from backend.app.core.database import SessionLocal
from backend.app.core.logging import get_logger
from backend.app.models import ApprovalKind, EventType

logger = get_logger(__name__)

# Idempotency ledger, keyed by run_id. A real deployment puts this in the
# database; the point being demonstrated is that the key is the run, so a
# retry is recognised as the same send.
_SENT: dict[str, dict] = {}


def register_email_tools(mcp):
    @mcp.tool()
    def draft_email(to: str, subject: str, body: str) -> dict:
        """Compose an email. Does NOT send — sending requires human approval
        and is not available to you.
        """
        if not to or "@" not in to:
            return {"ok": False, "error": f"invalid recipient: {to!r}"}
        if not body.strip():
            return {"ok": False, "error": "body is empty"}
        return {
            "ok": True,
            "data": {
                "to": to,
                "subject": subject,
                "body": body,
                "status": "drafted",
                "note": "Not sent. Sending requires human approval.",
            },
        }

    @mcp.tool()
    def send_email(run_id: str, to: str, subject: str, body: str) -> dict:
        """Send an email. Requires an approved RESPONSE_APPROVAL for the run.
        Idempotent on run_id. Not assigned to any agent — called post-approval.
        """
        from workflows.hitl import ApprovalGate
        from workflows.state import StateStore

        db = SessionLocal()
        try:
            store = StateStore(db)
            gate = ApprovalGate(db, store)

            if not gate.is_cleared(run_id, ApprovalKind.RESPONSE_APPROVAL):
                store.emit(
                    run_id,
                    EventType.TOOL_FAILED,
                    tool="email.send",
                    payload={"reason": "no approved RESPONSE_APPROVAL"},
                )
                return {
                    "ok": False,
                    "error": (
                        "Refused: no approved RESPONSE_APPROVAL for this run. "
                        "Every customer-facing send requires human approval."
                    ),
                }

            if run_id in _SENT:
                return {
                    "ok": True,
                    "data": {**_SENT[run_id], "status": "already_sent", "idempotent": True},
                }

            record = {"to": to, "subject": subject, "body": body, "run_id": run_id}
            _SENT[run_id] = record
            store.emit(run_id, EventType.TOOL_CALLED, tool="email.send", payload={"to": to})
            logger.info("email sent for run %s to %s", run_id, to)
            return {"ok": True, "data": {**record, "status": "sent"}}
        finally:
            db.close()