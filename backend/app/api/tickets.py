"""Ticket routes — create and list tickets from the console.

Used during demonstrations to invent a ticket on the spot (e.g. TK-5005) and
then run a workflow against it, without reaching for a CLI or the seed script.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from backend.app.api.deps import CurrentUser, DbSession
from backend.app.core.logging import get_logger
from backend.app.models import Ticket, TicketStatus
from backend.app.schemas.api import TicketCreate, TicketResponse

router = APIRouter(prefix="/tickets", tags=["tickets"])
logger = get_logger(__name__)


@router.post("", response_model=TicketResponse, status_code=status.HTTP_201_CREATED)
def create_ticket(payload: TicketCreate, db: DbSession, user: CurrentUser) -> TicketResponse:
    """Create a new OPEN ticket.

    Fails with 409 if the id is already taken, so a demo can't silently
    overwrite an existing ticket.
    """
    if db.get(Ticket, payload.id) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ticket {payload.id} already exists",
        )

    ticket = Ticket(
        id=payload.id,
        subject=payload.subject,
        body=payload.body,
        customer_email=payload.customer_email,
        account_tier=payload.account_tier,
        status=TicketStatus.OPEN,
        sla_hours=payload.sla_hours,
        message_count=1,
    )
    db.add(ticket)
    db.commit()
    logger.info("ticket created %s by %s", payload.id, user.email)
    return _to_response(ticket)


@router.get("", response_model=list[TicketResponse])
def list_tickets(db: DbSession, user: CurrentUser) -> list[TicketResponse]:
    """List all tickets, newest first."""
    rows = db.query(Ticket).order_by(Ticket.created_at.desc()).all()
    return [_to_response(t) for t in rows]


def _to_response(t: Ticket) -> TicketResponse:
    return TicketResponse(
        id=t.id,
        subject=t.subject,
        body=t.body,
        customer_email=t.customer_email,
        account_tier=t.account_tier,
        status=t.status.value,
        intent=t.intent,
        severity=t.severity,
        product_area=t.product_area,
        queue=t.queue,
        reopen_count=t.reopen_count,
        message_count=t.message_count,
        sla_hours=t.sla_hours,
        created_at=t.created_at,
    )
