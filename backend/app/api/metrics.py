"""Metrics route (Part 10 endpoint; Part 12 observability).

Every figure is derived from the `events` table, which is written by the
orchestration layer as it runs. Nothing here is instrumented separately —
a metric that needs its own instrumentation drifts from the behaviour it claims
to describe.
"""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import func, select

from fastapi import APIRouter

from backend.app.api.deps import CurrentUser, DbSession
from backend.app.models import (
    Approval,
    ApprovalStatus,
    Event,
    EventType,
    RunStatus,
    WorkflowRun,
)
from backend.app.schemas.api import MetricsResponse

router = APIRouter(tags=["metrics"])


@router.get("/metrics", response_model=MetricsResponse)
def metrics(db: DbSession, user: CurrentUser) -> MetricsResponse:
    runs_by_status: dict[str, int] = {
        s.value: c
        for s, c in db.execute(
            select(WorkflowRun.status, func.count()).group_by(WorkflowRun.status)
        ).all()
    }
    total_runs = sum(runs_by_status.values())

    completed = runs_by_status.get(RunStatus.COMPLETED.value, 0)
    failed = runs_by_status.get(RunStatus.FAILED.value, 0)
    escalated = runs_by_status.get(RunStatus.ESCALATED.value, 0)

    # Denominator is finished runs only. Counting in-flight and awaiting-approval
    # runs as incomplete would make the rate a function of how recently someone
    # started work rather than of whether the platform works.
    finished = completed + failed + escalated
    completion_rate = (completed / finished) if finished else 0.0
    failure_rate = (failed / finished) if finished else 0.0

    # Per-agent success from task events.
    done: dict[str, int] = defaultdict(int)
    fail: dict[str, int] = defaultdict(int)
    for agent, etype, count in db.execute(
        select(Event.agent, Event.event_type, func.count())
        .where(Event.event_type.in_([EventType.TASK_COMPLETED, EventType.TASK_FAILED]))
        .where(Event.agent.is_not(None))
        .group_by(Event.agent, Event.event_type)
    ).all():
        (done if etype is EventType.TASK_COMPLETED else fail)[agent] += count

    agent_success: dict[str, float] = {}
    for agent in set(done) | set(fail):
        attempts = done[agent] + fail[agent]
        agent_success[agent] = round(done[agent] / attempts, 4) if attempts else 0.0

    tool_usage: dict[str, int] = {
        tool: count
        for tool, count in db.execute(
            select(Event.tool, func.count())
            .where(Event.event_type == EventType.TOOL_CALLED, Event.tool.is_not(None))
            .group_by(Event.tool)
        ).all()
    }

    decided = db.execute(
        select(func.count()).select_from(Approval).where(Approval.status != ApprovalStatus.PENDING)
    ).scalar_one()
    accepted = db.execute(
        select(func.count())
        .select_from(Approval)
        .where(Approval.status.in_([ApprovalStatus.APPROVED, ApprovalStatus.EDITED]))
    ).scalar_one()

    return MetricsResponse(
        workflow_completion_rate=round(completion_rate, 4),
        agent_success_rates=agent_success,
        tool_usage=tool_usage,
        failure_rate=round(failure_rate, 4),
        approval_rate=round(accepted / decided, 4) if decided else 0.0,
        total_runs=total_runs,
        runs_by_status=runs_by_status,
    )
