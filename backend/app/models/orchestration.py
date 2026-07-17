"""ORM models for orchestration: tickets, runs, events, approvals.

`workflow_runs.state` holds the serialised WorkflowState (agents/schemas.py).
It is the authoritative record — a run is resumable from this row alone, which
is what makes the human approval gate possible without holding a worker open.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------
# Enumerations
# --------------------------------------------------------------------------


class RunStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    ESCALATED = "escalated"


class ApprovalStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EDITED = "edited"  # Approved, but the human changed the draft first.


class ApprovalKind(str, enum.Enum):
    TRIAGE_REVIEW = "triage_review"        # Low-confidence classification.
    RESPONSE_APPROVAL = "response_approval"  # Customer-facing send.
    ESCALATION_REVIEW = "escalation_review"
    REPORT_APPROVAL = "report_approval"


class EventType(str, enum.Enum):
    RUN_STARTED = "run_started"
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    TOOL_CALLED = "tool_called"
    TOOL_FAILED = "tool_failed"
    VALIDATION_FAILED = "validation_failed"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_DECIDED = "approval_decided"
    RUN_PAUSED = "run_paused"
    RUN_RESUMED = "run_resumed"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"
    DEGRADED = "degraded"  # A fallback fired. Never silent.


class TicketStatus(str, enum.Enum):
    OPEN = "open"
    PENDING_CUSTOMER = "pending_customer"
    RESOLVED = "resolved"
    ESCALATED = "escalated"


# --------------------------------------------------------------------------
# Models
# --------------------------------------------------------------------------


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    subject: Mapped[str] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(Text)
    customer_email: Mapped[str] = mapped_column(String(320))
    account_tier: Mapped[str] = mapped_column(String(50), default="standard")
    status: Mapped[TicketStatus] = mapped_column(
        Enum(TicketStatus), default=TicketStatus.OPEN
    )

    # Written back by the Triage Agent.
    intent: Mapped[str | None] = mapped_column(String(50), nullable=True)
    severity: Mapped[str | None] = mapped_column(String(10), nullable=True)
    product_area: Mapped[str | None] = mapped_column(String(100), nullable=True)
    queue: Mapped[str | None] = mapped_column(String(50), nullable=True)

    reopen_count: Mapped[int] = mapped_column(Integer, default=0)
    message_count: Mapped[int] = mapped_column(Integer, default=1)
    sla_hours: Mapped[int] = mapped_column(Integer, default=24)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    runs: Mapped[list[WorkflowRun]] = relationship(back_populates="ticket")


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workflow: Mapped[str] = mapped_column(String(100))
    status: Mapped[RunStatus] = mapped_column(Enum(RunStatus), default=RunStatus.PENDING)

    ticket_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("tickets.id"), nullable=True
    )

    # Serialised WorkflowState. The run is resumable from this alone.
    state: Mapped[dict] = mapped_column(JSON, default=dict)

    current_task: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    ticket: Mapped[Ticket | None] = relationship(back_populates="runs")
    events: Mapped[list[Event]] = relationship(back_populates="run")
    approvals: Mapped[list[Approval]] = relationship(back_populates="run")


class Event(Base):
    """Append-only trace. Every run is replayable from its events.

    Also the source for the observability metrics in Part 12 and the evaluation
    harness in Part 13, which is why tool calls are recorded before *and* after
    execution rather than only on success.
    """

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("workflow_runs.id"), index=True)

    event_type: Mapped[EventType] = mapped_column(Enum(EventType), index=True)
    agent: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    task: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tool: Mapped[str | None] = mapped_column(String(100), nullable=True)

    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    run: Mapped[WorkflowRun] = relationship(back_populates="events")


class Approval(Base):
    """A human decision gate.

    No customer-facing action executes without a row here in APPROVED or EDITED
    state. The check is structural, not a prompt instruction — an agent cannot
    talk its way past a database constraint.
    """

    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("workflow_runs.id"), index=True)

    kind: Mapped[ApprovalKind] = mapped_column(Enum(ApprovalKind))
    status: Mapped[ApprovalStatus] = mapped_column(
        Enum(ApprovalStatus), default=ApprovalStatus.PENDING, index=True
    )

    # What the human is being asked to approve.
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    # Why it was routed to a human — low confidence, policy, always-on gate.
    reason: Mapped[str] = mapped_column(Text)

    # The decision.
    decided_by: Mapped[str | None] = mapped_column(String(320), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    edited_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    run: Mapped[WorkflowRun] = relationship(back_populates="approvals")
