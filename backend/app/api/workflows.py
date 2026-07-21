"""Workflow routes (Part 10)."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from backend.app.api.deps import CurrentUser, DbSession
from backend.app.core.logging import get_logger
from backend.app.models import Approval, ApprovalStatus, Event, Ticket, WorkflowRun
from backend.app.schemas.api import (
    EventResponse,
    WorkflowRunResponse,
    WorkflowStatusResponse,
)
from workflows import BATCH_WORKFLOWS, WORKFLOW_REGISTRY

router = APIRouter(tags=["workflows"])
logger = get_logger(__name__)


@router.get("/workflows", response_model=list[str])
def list_workflows(user: CurrentUser) -> list[str]:
    return list(WORKFLOW_REGISTRY)


@router.post("/workflows/run", response_model=WorkflowRunResponse, status_code=status.HTTP_202_ACCEPTED)
def run_workflow(
    payload: dict, db: DbSession, user: CurrentUser, background: BackgroundTasks
) -> WorkflowRunResponse:
    """Start a workflow run.

    202, not 200: a crew takes minutes and may pause for hours at a human gate,
    so the request cannot wait for a result. The run id is the handle; progress
    comes from GET /workflows/{run_id}/status.
    """
    workflow = payload.get("workflow")
    ticket_id = payload.get("ticket_id")

    if workflow not in WORKFLOW_REGISTRY:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown workflow '{workflow}'. Available: {', '.join(WORKFLOW_REGISTRY)}",
        )

    # Batch workflows scan a queue; a ticket_id would be meaningless for them.
    if workflow not in BATCH_WORKFLOWS:
        if not ticket_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Workflow '{workflow}' requires a ticket_id",
            )
        if db.get(Ticket, ticket_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail=f"No such ticket: {ticket_id}")

    wf = WORKFLOW_REGISTRY[workflow](db)
    run_id = wf.start(ticket_id)

    run = db.get(WorkflowRun, run_id)
    pending = (
        db.query(Approval)
        .filter(Approval.run_id == run_id, Approval.status == ApprovalStatus.PENDING)
        .first()
    )
    return WorkflowRunResponse(
        run_id=run_id,
        workflow=workflow,
        status=run.status.value,
        awaiting_approval_id=pending.id if pending else None,
    )


@router.get("/workflows/{run_id}/status", response_model=WorkflowStatusResponse)
def workflow_status(run_id: str, db: DbSession, user: CurrentUser) -> WorkflowStatusResponse:
    run = db.get(WorkflowRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No such run: {run_id}")

    events = (
        db.query(Event).filter(Event.run_id == run_id).order_by(Event.created_at.asc()).all()
    )
    return WorkflowStatusResponse(
        run_id=run.id,
        workflow=run.workflow,
        status=run.status.value,
        ticket_id=run.ticket_id,
        current_task=run.current_task,
        error=run.error,
        state=run.state,
        started_at=run.started_at,
        completed_at=run.completed_at,
        events=[
            EventResponse(
                event_type=e.event_type.value,
                agent=e.agent,
                task=e.task,
                tool=e.tool,
                payload=e.payload,
                duration_ms=e.duration_ms,
                created_at=e.created_at,
            )
            for e in events
        ],
    )
