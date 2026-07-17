"""SQLAlchemy ORM models.

Imported by init_db() for metadata registration — every model must be
re-exported here or its table will not be created.
"""

from backend.app.models.knowledge import Chunk, Document, DocType, IngestStatus
from backend.app.models.orchestration import (
    Approval,
    ApprovalKind,
    ApprovalStatus,
    Event,
    EventType,
    RunStatus,
    Ticket,
    TicketStatus,
    WorkflowRun,
)

__all__ = [
    "Ticket",
    "TicketStatus",
    "WorkflowRun",
    "RunStatus",
    "Event",
    "EventType",
    "Approval",
    "ApprovalStatus",
    "ApprovalKind",
    "Document",
    "DocType",
    "IngestStatus",
    "Chunk",
]
