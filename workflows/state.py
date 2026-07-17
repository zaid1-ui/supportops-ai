"""Workflow state management (Part 3).

The authoritative state lives in `workflow_runs.state`, snapshotted after every
task. Two things depend on that:

- A run pauses at a human gate without holding a worker open. The worker exits;
  approval enqueues a fresh resume.
- A crashed run resumes from its last completed task rather than restarting and
  re-billing every LLM call before the crash point.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from agents.schemas import WorkflowState
from backend.app.core.logging import get_logger
from backend.app.models import Event, EventType, RunStatus, WorkflowRun

logger = get_logger(__name__)


class StateStore:
    """Reads and writes run state, and appends to the event trace.

    Every mutation emits an event. That is not incidental logging — the events
    table is the replay log, the metrics source (Part 12), and the evaluation
    corpus (Part 13). A state change with no event is invisible to all three.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    # -- lifecycle -------------------------------------------------------

    def create_run(self, workflow: str, ticket_id: str | None = None) -> WorkflowRun:
        run = WorkflowRun(
            id=str(uuid.uuid4()),
            workflow=workflow,
            ticket_id=ticket_id,
            status=RunStatus.RUNNING,
            state=WorkflowState(run_id="", ticket_id=ticket_id).model_dump(mode="json"),
        )
        run.state["run_id"] = run.id
        self.db.add(run)
        self.db.commit()
        self.emit(run.id, EventType.RUN_STARTED, payload={"workflow": workflow})
        return run

    def load(self, run_id: str) -> tuple[WorkflowRun, WorkflowState]:
        run = self.db.get(WorkflowRun, run_id)
        if run is None:
            raise LookupError(f"No such run: {run_id}")
        return run, WorkflowState.model_validate(run.state)

    def snapshot(self, run_id: str, state: WorkflowState, current_task: str | None = None) -> None:
        """Persist state after a task. Called from the CrewAI task callback."""
        run = self.db.get(WorkflowRun, run_id)
        if run is None:
            raise LookupError(f"No such run: {run_id}")
        run.state = state.model_dump(mode="json")
        if current_task is not None:
            run.current_task = current_task
        self.db.commit()

    def set_status(self, run_id: str, status: RunStatus, error: str | None = None) -> None:
        run = self.db.get(WorkflowRun, run_id)
        if run is None:
            raise LookupError(f"No such run: {run_id}")
        run.status = status
        run.error = error
        if status in (RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.ESCALATED):
            run.completed_at = datetime.now(timezone.utc)
        self.db.commit()

    # -- event trace -----------------------------------------------------

    def emit(
        self,
        run_id: str,
        event_type: EventType,
        *,
        agent: str | None = None,
        task: str | None = None,
        tool: str | None = None,
        payload: dict | None = None,
        duration_ms: float | None = None,
    ) -> None:
        self.db.add(
            Event(
                run_id=run_id,
                event_type=event_type,
                agent=agent,
                task=task,
                tool=tool,
                payload=payload or {},
                duration_ms=duration_ms,
            )
        )
        self.db.commit()
        logger.info(
            "event",
            extra={"run_id": run_id, "event": event_type.value, "agent": agent, "task": task},
        )


class TaskTimer:
    """Times a task and emits started/completed/failed around it.

    Failures re-raise after emitting. Recovery is the caller's decision
    (workflows/recovery.py); this only guarantees the trace is complete either
    way — a task that fails silently cannot be measured.
    """

    def __init__(self, store: StateStore, run_id: str, agent: str, task: str) -> None:
        self.store = store
        self.run_id = run_id
        self.agent = agent
        self.task = task
        self._t0 = 0.0

    def __enter__(self) -> TaskTimer:
        self._t0 = time.perf_counter()
        self.store.emit(self.run_id, EventType.TASK_STARTED, agent=self.agent, task=self.task)
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        elapsed = (time.perf_counter() - self._t0) * 1000
        if exc_type is None:
            self.store.emit(
                self.run_id,
                EventType.TASK_COMPLETED,
                agent=self.agent,
                task=self.task,
                duration_ms=elapsed,
            )
        else:
            self.store.emit(
                self.run_id,
                EventType.TASK_FAILED,
                agent=self.agent,
                task=self.task,
                payload={"error": str(exc), "type": exc_type.__name__},
                duration_ms=elapsed,
            )
        return False  # never swallow
