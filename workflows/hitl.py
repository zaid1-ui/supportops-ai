"""Human-in-the-loop gates (Part 9).

Four intervention points:

    TRIAGE_REVIEW      classification confidence below threshold
    RESPONSE_APPROVAL  any customer-facing send — always, unconditionally
    ESCALATION_REVIEW  agent proposes escalating to a human tier
    REPORT_APPROVAL    report published to stakeholders

The gate is structural. `RESPONSE_APPROVAL` is not a prompt instruction the
agent is asked to respect — it is a row that must exist in APPROVED or EDITED
state before the send path runs. An agent cannot argue its way past a database
check, which is the entire reason the enforcement lives here and not in a
backstory.

Pausing is not blocking. `request()` sets the run to AWAITING_APPROVAL and
returns; the worker exits. `resume()` picks the run back up from its snapshot
when a human decides. An idle run costs nothing.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from agents.schemas import ReportingOutput, ResolutionOutput, TriageOutput, WorkflowState
from backend.app.core.logging import get_logger
from backend.app.models import (
    Approval,
    ApprovalKind,
    ApprovalStatus,
    EventType,
    RunStatus,
)
from workflows.state import StateStore

logger = get_logger(__name__)

# Below this, Triage output goes to a human rather than downstream.
# Matches the threshold stated in the triage prompt — if the two drift apart,
# the agent is calibrating against a rule that no longer fires.
TRIAGE_CONFIDENCE_THRESHOLD = 0.6


class ApprovalRequired(Exception):
    """Raised to unwind the crew when a gate opens. Carries the approval id."""

    def __init__(self, approval_id: str, kind: ApprovalKind) -> None:
        self.approval_id = approval_id
        self.kind = kind
        super().__init__(f"Awaiting {kind.value} approval: {approval_id}")


class ApprovalGate:
    """Creates gates, records decisions, and reports whether a run may proceed."""

    def __init__(self, db: Session, store: StateStore) -> None:
        self.db = db
        self.store = store

    # -- requesting ------------------------------------------------------

    def request(
        self,
        run_id: str,
        kind: ApprovalKind,
        *,
        payload: dict,
        reason: str,
    ) -> Approval:
        """Open a gate and pause the run.

        The run is left AWAITING_APPROVAL with its state already snapshotted, so
        nothing is held in memory waiting for a human who may take hours.
        """
        approval = Approval(
            id=str(uuid.uuid4()),
            run_id=run_id,
            kind=kind,
            status=ApprovalStatus.PENDING,
            payload=payload,
            reason=reason,
        )
        self.db.add(approval)
        self.db.commit()

        self.store.set_status(run_id, RunStatus.AWAITING_APPROVAL)
        self.store.emit(
            run_id,
            EventType.APPROVAL_REQUESTED,
            payload={"approval_id": approval.id, "kind": kind.value, "reason": reason},
        )
        self.store.emit(run_id, EventType.RUN_PAUSED, payload={"awaiting": kind.value})
        return approval

    # -- deciding --------------------------------------------------------

    def decide(
        self,
        approval_id: str,
        *,
        status: ApprovalStatus,
        decided_by: str,
        edited_payload: dict | None = None,
        feedback: str | None = None,
    ) -> Approval:
        """Record a human decision.

        `feedback` is captured on every decision, not just rejections. Approvals
        and edits are the positive training signal for the evaluation harness
        (Part 13) — only ever storing rejections would bias the corpus toward
        the platform's failures.
        """
        approval = self.db.get(Approval, approval_id)
        if approval is None:
            raise LookupError(f"No such approval: {approval_id}")
        if approval.status is not ApprovalStatus.PENDING:
            raise ValueError(f"Approval {approval_id} already decided: {approval.status.value}")
        if status is ApprovalStatus.PENDING:
            raise ValueError("Cannot decide an approval into PENDING")
        if status is ApprovalStatus.EDITED and edited_payload is None:
            raise ValueError("EDITED requires edited_payload")

        approval.status = status
        approval.decided_by = decided_by
        approval.decided_at = datetime.now(timezone.utc)
        approval.edited_payload = edited_payload
        approval.feedback = feedback
        self.db.commit()

        self.store.emit(
            approval.run_id,
            EventType.APPROVAL_DECIDED,
            payload={
                "approval_id": approval.id,
                "kind": approval.kind.value,
                "status": status.value,
                "decided_by": decided_by,
                "edited": edited_payload is not None,
            },
        )
        return approval

    # -- enforcement -----------------------------------------------------

    def is_cleared(self, run_id: str, kind: ApprovalKind) -> bool:
        """Whether a gate of this kind has been cleared for this run.

        The send path calls this. It is the structural check that makes the
        RESPONSE_APPROVAL gate real rather than advisory.
        """
        stmt = select(Approval).where(
            Approval.run_id == run_id,
            Approval.kind == kind,
            Approval.status.in_([ApprovalStatus.APPROVED, ApprovalStatus.EDITED]),
        )
        return self.db.execute(stmt).scalars().first() is not None

    def pending_for(self, run_id: str) -> Approval | None:
        stmt = select(Approval).where(
            Approval.run_id == run_id, Approval.status == ApprovalStatus.PENDING
        )
        return self.db.execute(stmt).scalars().first()

    def inbox(self, limit: int = 50) -> list[Approval]:
        """Everything waiting on a human, oldest first.

        Oldest-first is deliberate: a newest-first queue starves the tickets
        that have been waiting longest, which are the ones closest to breaching.
        """
        stmt = (
            select(Approval)
            .where(Approval.status == ApprovalStatus.PENDING)
            .order_by(Approval.created_at.asc())
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars().all())

    # -- resuming --------------------------------------------------------

    def resume(self, run_id: str) -> tuple[WorkflowState, Approval]:
        """Reload a paused run after its gate was decided.

        Applies an EDITED payload back into the state. The human's edit becomes
        the state — the agent's rejected draft is not re-run, because the human
        has already done that work and redoing it would discard their decision.
        """
        run, state = self.store.load(run_id)
        approval = self.pending_for(run_id)
        if approval is not None:
            raise ValueError(f"Run {run_id} still has a pending approval: {approval.id}")

        decided = (
            self.db.execute(
                select(Approval)
                .where(Approval.run_id == run_id)
                .order_by(Approval.decided_at.desc())
            )
            .scalars()
            .first()
        )
        if decided is None:
            raise ValueError(f"Run {run_id} has no decided approval to resume from")

        if decided.status is ApprovalStatus.EDITED and decided.edited_payload:
            state = self._apply_edit(state, decided)

        state.awaiting_approval = False
        self.store.snapshot(run_id, state)
        self.store.set_status(run_id, RunStatus.RUNNING)
        self.store.emit(
            run_id,
            EventType.RUN_RESUMED,
            payload={"approval_id": decided.id, "status": decided.status.value},
        )
        return state, decided

    @staticmethod
    def _apply_edit(state: WorkflowState, approval: Approval) -> WorkflowState:
        """Merge a human edit into the run state, re-validating the result.

        Note `model_validate` rather than `model_copy(update=...)`. `model_copy`
        does not validate, so an edit of {"severity": "S2"} would store the raw
        string where the schema declares a Severity enum — and the mismatch would
        surface much later, in whichever agent consumed it. Edits arrive from an
        HTTP request body, which makes them untrusted input like any other.
        """
        payload = approval.edited_payload or {}

        if approval.kind is ApprovalKind.TRIAGE_REVIEW and state.triage is not None:
            merged = {**state.triage.model_dump(mode="json"), **payload}
            # A human corrected the label, so the model's confidence no longer
            # describes anything. Ground it in the human's judgement instead.
            merged["confidence"] = 1.0
            state.triage = TriageOutput.model_validate(merged)

        elif approval.kind is ApprovalKind.RESPONSE_APPROVAL and state.resolution is not None:
            merged = {**state.resolution.model_dump(mode="json"), **payload}
            state.resolution = ResolutionOutput.model_validate(merged)

        elif approval.kind is ApprovalKind.REPORT_APPROVAL and state.report is not None:
            merged = {**state.report.model_dump(mode="json"), **payload}
            state.report = ReportingOutput.model_validate(merged)

        return state


# --------------------------------------------------------------------------
# Gate conditions
# --------------------------------------------------------------------------


def needs_triage_review(state: WorkflowState) -> bool:
    """Low-confidence classification goes to a human before it costs anything."""
    return state.triage is not None and state.triage.confidence < TRIAGE_CONFIDENCE_THRESHOLD


def needs_response_approval(state: WorkflowState) -> bool:
    """Always true when there is a draft. There is no autonomous send path."""
    return state.resolution is not None
