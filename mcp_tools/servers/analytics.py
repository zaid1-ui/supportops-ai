"""Analytics MCP server (Part 7).

Reads the events table (Part 3) and turns it into the metrics Part 12 tracks.
Consumed by the Escalation Agent (queue pressure), the Diagnostic Agent
(incident correlation), and the Reporting Agent.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import mcp.types as types
from mcp.server import Server
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.models import Event, EventType, RunStatus, Ticket, TicketStatus, WorkflowRun
from mcp_tools.core import ToolResult, fail, ok

TOOL_AGENT_STATS = "agent_success_rates"
TOOL_WORKFLOW_STATS = "workflow_stats"
TOOL_QUEUE = "queue_pressure"


def agent_success_rates(db: Session, since_hours: int = 168) -> ToolResult:
    """Per-agent completion rate from the event trace.

    Success is completed / (completed + failed). Tasks still running are
    excluded rather than counted as failures — counting them would make the
    metric drop whenever the platform is merely busy.
    """
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

    return ok({"window_hours": since_hours, "agents": stats})


def workflow_stats(db: Session, since_hours: int = 168) -> ToolResult:
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

    return ok({"window_hours": since_hours, "workflows": out})


def queue_pressure(db: Session) -> ToolResult:
    """Open tickets by SLA proximity. The Escalation Agent's strongest driver."""
    now = datetime.now(timezone.utc)
    rows = db.execute(
        select(Ticket).where(Ticket.status.in_([TicketStatus.OPEN, TicketStatus.PENDING_CUSTOMER]))
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
            # Matches the escalation prompt's stated threshold. If the two drift
            # apart, the agent calibrates against a rule nothing enforces.
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

    return ok({"open_total": len(rows), "buckets": buckets, "at_risk": at_risk})


server = Server("supportops-analytics")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name=TOOL_AGENT_STATS,
            description="Per-agent task success rates from the event trace.",
            inputSchema={
                "type": "object",
                "properties": {"since_hours": {"type": "integer", "default": 168}},
            },
        ),
        types.Tool(
            name=TOOL_WORKFLOW_STATS,
            description="Workflow run counts and completion rates by status.",
            inputSchema={
                "type": "object",
                "properties": {"since_hours": {"type": "integer", "default": 168}},
            },
        ),
        types.Tool(
            name=TOOL_QUEUE,
            description="Open tickets bucketed by SLA proximity, with the at-risk list.",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    from backend.app.core.database import SessionLocal

    db = SessionLocal()
    try:
        if name == TOOL_AGENT_STATS:
            result = agent_success_rates(db, arguments.get("since_hours", 168))
        elif name == TOOL_WORKFLOW_STATS:
            result = workflow_stats(db, arguments.get("since_hours", 168))
        elif name == TOOL_QUEUE:
            result = queue_pressure(db)
        else:
            result = fail(f"unknown tool: {name}")
    finally:
        db.close()
    return [types.TextContent(type="text", text=result.to_text())]


async def main() -> None:
    from mcp.server.stdio import stdio_server

    async with stdio_server() as (r, w):
        await server.run(r, w, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
