"""Analytics MCP tools.

Reads the events table and turns it into the metrics observability tracks.
Consumed by the Escalation Agent (queue pressure), the Diagnostic Agent
(incident correlation), and the Reporting Agent.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from backend.app.core.database import SessionLocal
from backend.app.models import Event, EventType, RunStatus, Ticket, TicketStatus, WorkflowRun


def register_analytics_tools(mcp):
    @mcp.tool()
    def agent_success_rates(since_hours: int = 168) -> dict:
        """Per-agent task success rates over a time window.

        Success is completed / (completed + failed). Tasks still running are
        excluded rather than counted as failures — counting them would make
        the metric drop whenever the platform is merely busy.
        """
        db = SessionLocal()
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
            rows = db.execute(
                select(Event.agent, Event.event_type, func.count(Event.id))
                .where(
                    Event.created_at >= cutoff,
                    Event.agent.is_not(None),
                    Event.event_type.in_([EventType.TASK_COMPLETED, EventType.TASK_FAILED]),
                )
                .group_by(Event.agent, Event.event_type)
            ).all()

            stats: dict[str, dict] = {}
            for agent, event_type, count in rows:
                s = stats.setdefault(agent, {"completed": 0, "failed": 0})
                s["completed" if event_type is EventType.TASK_COMPLETED else "failed"] += count

            for s in stats.values():
                total = s["completed"] + s["failed"]
                s["success_rate"] = round(s["completed"] / total, 3) if total else None

            return {"ok": True, "data": {"window_hours": since_hours, "agents": stats}}
        finally:
            db.close()

    @mcp.tool()
    def workflow_stats(since_hours: int = 168) -> dict:
        """Workflow run counts and completion rates by status."""
        db = SessionLocal()
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
            rows = db.execute(
                select(WorkflowRun.workflow, WorkflowRun.status, func.count(WorkflowRun.id))
                .where(WorkflowRun.started_at >= cutoff)
                .group_by(WorkflowRun.workflow, WorkflowRun.status)
            ).all()

            out: dict[str, dict] = {}
            for workflow, status, count in rows:
                out.setdefault(workflow, {})[status.value] = count

            for w in out.values():
                completed = w.get(RunStatus.COMPLETED.value, 0)
                total = sum(w.values())
                w["completion_rate"] = round(completed / total, 3) if total else None

            return {"ok": True, "data": {"window_hours": since_hours, "workflows": out}}
        finally:
            db.close()

    @mcp.tool()
    def queue_pressure() -> dict:
        """Open tickets bucketed by SLA proximity (breached / at_risk /
        healthy), with the at-risk list.
        """
        db = SessionLocal()
        try:
            now = datetime.now(timezone.utc)
            rows = db.execute(
                select(Ticket).where(
                    Ticket.status.in_([TicketStatus.OPEN, TicketStatus.PENDING_CUSTOMER])
                )
            ).scalars().all()

            buckets = {"breached": 0, "at_risk": 0, "healthy": 0}
            at_risk: list[dict] = []

            for t in rows:
                created = t.created_at if t.created_at.tzinfo else t.created_at.replace(tzinfo=timezone.utc)
                age = (now - created).total_seconds() / 3600
                pct = age / t.sla_hours if t.sla_hours else 0

                if pct >= 1.0:
                    buckets["breached"] += 1
                elif pct >= 0.75:
                    buckets["at_risk"] += 1
                    at_risk.append(
                        {
                            "ticket_id": t.id,
                            "severity": t.severity,
                            "age_hours": round(age, 1),
                            "sla_hours": t.sla_hours,
                            "sla_used_pct": round(pct * 100, 1),
                        }
                    )
                else:
                    buckets["healthy"] += 1

            return {
                "ok": True,
                "data": {"open_total": len(rows), "buckets": buckets, "at_risk": at_risk},
            }
        finally:
            db.close()