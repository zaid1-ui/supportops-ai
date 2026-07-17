"""Approval routes (Part 9 human-in-the-loop, exposed per Part 10)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from backend.app.api.deps import CurrentUser, DbSession
from backend.app.core.logging import get_logger
from backend.app.models import Approval, ApprovalStatus, WorkflowRun
from backend.app.schemas.api import ApprovalDecision, ApprovalResponse
from workflows import WORKFLOW_REGISTRY
from workflows.hitl import ApprovalGate
from workflows.state import StateStore

router = APIRouter(prefix="/approvals", tags=["approvals"])
logger = get_logger(__name__)


@router.get("", response_model=list[ApprovalResponse])
def inbox(db: DbSession, user: CurrentUser, limit: int = 50) -> list[ApprovalResponse]:
    """Everything waiting on a human, oldest first."""
    gate = ApprovalGate(db, StateStore(db))
    return [_to_response(a) for a in gate.inbox(limit=limit)]


@router.get("/{approval_id}", response_model=ApprovalResponse)
def get_approval(approval_id: str, db: DbSession, user: CurrentUser) -> ApprovalResponse:
    approval = db.get(Approval, approval_id)
    if approval is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such approval")
    return _to_response(approval)


@router.post("/{approval_id}/decide", response_model=ApprovalResponse)
def decide(
    approval_id: str, payload: ApprovalDecision, db: DbSession, user: CurrentUser
) -> ApprovalResponse:
    """Record a human decision and resume the run.

    Authority is checked server-side against the caller's role. The frontend
    hiding a button is an affordance, not an authorisation boundary.
    """
    approval = db.get(Approval, approval_id)
    if approval is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such approval")

    if not user.may_decide(approval.kind.value):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{user.role.value}' may not decide '{approval.kind.value}'",
        )

    store = StateStore(db)
    gate = ApprovalGate(db, store)

    try:
        gate.decide(
            approval_id,
            status=ApprovalStatus(payload.status),
            decided_by=user.email,
            edited_payload=payload.edited_payload,
            feedback=payload.feedback,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    # A rejection ends the run — the human has taken it over. Only an approval
    # or an edit resumes the crew.
    if payload.status == "rejected":
        from backend.app.models import RunStatus

        store.set_status(approval.run_id, RunStatus.ESCALATED, error="Rejected by reviewer")
    else:
        run = db.get(WorkflowRun, approval.run_id)
        wf_cls = WORKFLOW_REGISTRY.get(run.workflow)
        if wf_cls is not None:
            try:
                wf_cls(db).resume(approval.run_id)
            except Exception as exc:  # noqa: BLE001
                logger.exception("resume failed for run %s", approval.run_id)
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Resume failed: {exc}"
                ) from exc

    return _to_response(db.get(Approval, approval_id))


def _to_response(a: Approval) -> ApprovalResponse:
    return ApprovalResponse(
        id=a.id,
        run_id=a.run_id,
        kind=a.kind.value,
        status=a.status.value,
        reason=a.reason,
        payload=a.payload,
        decided_by=a.decided_by,
        decided_at=a.decided_at,
        created_at=a.created_at,
    )
