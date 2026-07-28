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

from sqlalchemy.orm import Session

from backend.app.core.database import SessionLocal
from backend.app.core.logging import get_logger
from backend.app.models import ApprovalKind, EventType
from mcp_server.core import ToolResult, fail, ok

logger = get_logger(__name__)

# Idempotency ledger, keyed by run_id. A real deployment puts this in the
# database; the point being demonstrated is that the key is the run, so a
# retry is recognised as the same send.
_SENT: dict[str, dict] = {}


def draft_email(to: str, subject: str, body: str) -> ToolResult:
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


def send_email(db: Session, run_id: str, to: str, subject: str, body: str) -> ToolResult:
    """Send an email. Requires an approved RESPONSE_APPROVAL for the run.

    Idempotent on run_id. Not assigned to any agent — called post-approval,
    from the workflow's execute segment, the same way the MCP server's
    send_email tool would call it for any other caller.
    """
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
        return ok({**_SENT[run_id], "status": "already_sent", "idempotent": True})

    record = {"to": to, "subject": subject, "body": body, "run_id": run_id}
    _SENT[run_id] = record
    store.emit(run_id, EventType.TOOL_CALLED, tool="email.send", payload={"to": to})
    logger.info("email sent for run %s to %s", run_id, to)
    return ok({**record, "status": "sent"})


def register_email_tools(mcp):
    @mcp.tool(name="draft_email")
    def draft_email_tool(to: str, subject: str, body: str) -> dict:
        """Compose an email. Does NOT send — sending requires human approval
        and is not available to you.
        """
        return draft_email(to, subject, body).to_dict()

    @mcp.tool(name="send_email")
    def send_email_tool(run_id: str, to: str, subject: str, body: str) -> dict:
        """Send an email. Requires an approved RESPONSE_APPROVAL for the run.
        Idempotent on run_id. Not assigned to any agent — called post-approval.
        """
        db = SessionLocal()
        try:
            return send_email(db, run_id, to, subject, body).to_dict()
        finally:
            db.close()