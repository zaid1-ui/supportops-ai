"""Escalation Risk Assessment workflow (Part 8, workflow 3).

    Escalation -> Diagnostic -> Reporting -> human gate

Scheduled, sequential, batch. Scores the open queue, explains what is driving
the risk, and hands a Team Lead a ranked register they can act on.

The point is timing. Ticket Resolution (workflow 1) scores risk on one ticket
while it is being worked. This runs across the whole open queue on a schedule
and catches the tickets nobody is currently looking at — which is precisely
where an SLA breach comes from. A ticket being actively worked is not the one
that breaches.
"""

from __future__ import annotations

from datetime import datetime, timezone

from crewai import Crew, Process, Task
from crewai.tools import BaseTool
from sqlalchemy import select
from sqlalchemy.orm import Session

from agents.definitions import (
    build_diagnostic_agent,
    build_escalation_agent,
    build_reporting_agent,
)
from agents.prompts import REPORTING_TASK
from agents.schemas import ReportingOutput, WorkflowState
from backend.app.core.logging import get_logger
from backend.app.models import ApprovalKind, EventType, RunStatus, Ticket, TicketStatus
from mcp_tools.registry import build_tools
from workflows.hitl import ApprovalGate, ApprovalRequired
from workflows.state import StateStore, TaskTimer

logger = get_logger(__name__)

WORKFLOW_NAME = "escalation_risk_assessment"
BATCH_LIMIT = 25


class EscalationRiskWorkflow:
    """Scores the open queue and produces a ranked risk register."""

    def __init__(self, db: Session, tools: dict[str, list[BaseTool]] | None = None) -> None:
        self.db = db
        self.store = StateStore(db)
        self.gate = ApprovalGate(db, self.store)
        self.tools = tools if tools is not None else build_tools(db)

    def _t(self, name: str) -> list[BaseTool]:
        return self.tools.get(name, [])

    def start(self, ticket_id: str | None = None) -> str:
        """Assess the queue. `ticket_id` ignored — batch job, signature kept uniform."""
        run = self.store.create_run(WORKFLOW_NAME)
        state = WorkflowState(run_id=run.id)

        try:
            queue = self._open_queue()
            if not queue:
                self.store.emit(run.id, EventType.RUN_COMPLETED, payload={"note": "queue is empty"})
                self.store.set_status(run.id, RunStatus.COMPLETED)
                return run.id
            self._assess(run.id, state, queue)
        except ApprovalRequired as gate:
            logger.info("run %s paused at %s", run.id, gate.kind.value)
        except Exception as exc:  # noqa: BLE001
            self.store.set_status(run.id, RunStatus.FAILED, error=str(exc))
            self.store.emit(run.id, EventType.RUN_FAILED, payload={"error": str(exc)})
            raise
        return run.id

    def resume(self, run_id: str) -> str:
        state, approval = self.gate.resume(run_id)
        self.store.emit(run_id, EventType.RUN_COMPLETED,
                        payload={"acknowledged_by": approval.decided_by})
        self.store.set_status(run_id, RunStatus.COMPLETED)
        return run_id

    def _open_queue(self) -> list[Ticket]:
        stmt = (
            select(Ticket)
            .where(Ticket.status != TicketStatus.RESOLVED)
            .order_by(Ticket.created_at.asc())
            .limit(BATCH_LIMIT)
        )
        return list(self.db.execute(stmt).scalars().all())

    def _assess(self, run_id: str, state: WorkflowState, queue: list[Ticket]) -> None:
        escalation = build_escalation_agent(self._t("escalation"))
        diagnostic = build_diagnostic_agent(self._t("diagnostic"))
        reporting = build_reporting_agent(self._t("reporting"))

        # SLA arithmetic is done here, in Python, not by the model. Age against
        # target is a subtraction: asking an LLM to do it introduces a way for
        # the single strongest risk signal to be wrong.
        now = datetime.now(timezone.utc)
        rows = []
        for t in queue:
            created = t.created_at if t.created_at.tzinfo else t.created_at.replace(tzinfo=timezone.utc)
            age = (now - created).total_seconds() / 3600
            consumed = (age / t.sla_hours * 100) if t.sla_hours else 0
            rows.append(
                f"- [{t.id}] {t.subject}\n"
                f"    severity={t.severity or 'unclassified'} tier={t.account_tier} "
                f"age={age:.1f}h sla={t.sla_hours}h consumed={consumed:.0f}% "
                f"reopens={t.reopen_count} messages={t.message_count}"
            )
        table = "\n".join(rows)

        score_task = Task(
            description=(
                "Score escalation risk for every ticket in the open queue.\n\n"
                f"<queue>\n{table}\n</queue>\n\n"
                "Weigh, in this order:\n"
                "- SLA consumed. Past 75% with no resolution is the strongest single signal, "
                "and it is objective — unlike tone, it does not depend on how the customer "
                "chose to phrase things.\n"
                "- Reopens. One means the last answer was wrong. Two means the process is "
                "failing, not the answer, and the fix is not another reply.\n"
                "- Message count. A long thread means the issue is not understood.\n"
                "- Account tier. Enterprise accounts carry contractual response terms.\n"
                "- Unclassified severity plus age. Nobody has even looked at it.\n\n"
                "Rules:\n"
                "- Every S1 is high risk, regardless of everything else.\n"
                "- Tone is not in this data and is not needed. Escalate on trajectory.\n"
                "- Rank by risk. Include every ticket, even low risk — a lead needs to see "
                "the whole queue to trust the ranking of the top of it."
            ),
            expected_output="Every ticket ranked by risk, each with the drivers that moved it.",
            agent=escalation,
        )

        explain_task = Task(
            description=(
                "Explain what is driving the high and medium risk tickets.\n\n"
                "A ranked list tells a lead which tickets are in trouble. It does not tell "
                "them why, and 'why' is what determines whether the fix is more staff, a "
                "knowledge article, or an engineering escalation.\n\n"
                "Look for the pattern across tickets, not just within them: several tickets "
                "in the same product area means something is broken upstream, and reassigning "
                "them individually will not help.\n\n"
                "Where the data does not support a cause, say so. Do not invent a narrative "
                "to explain a ranking."
            ),
            expected_output="Risk drivers per ticket, plus any cross-queue pattern.",
            agent=diagnostic,
            context=[score_task],
        )

        report_task = Task(
            description=REPORTING_TASK.format(
                report_type="escalation risk register",
                data=(
                    "Use the scored queue and the driver analysis from the previous steps. "
                    "The reader is a Support Team Lead deciding what to do in the next hour. "
                    "Lead with what needs intervention now. Every recommendation names the "
                    "ticket, the action, and who does it. If the queue is healthy, say that "
                    "plainly — an honest all-clear is a useful finding."
                ),
            ),
            expected_output="A ReportingOutput: a ranked, owned risk register.",
            agent=reporting,
            context=[explain_task],
            output_pydantic=ReportingOutput,
        )

        crew = Crew(
            agents=[escalation, diagnostic, reporting],
            tasks=[score_task, explain_task, report_task],
            process=Process.sequential,
            verbose=True,
        )

        with TaskTimer(self.store, run_id, "escalation", "risk_assessment"):
            crew.kickoff()

        state.report = report_task.output.pydantic
        self.store.snapshot(run_id, state, current_task="reporting")

        approval = self.gate.request(
            run_id,
            ApprovalKind.ESCALATION_REVIEW,
            payload=state.report.model_dump(mode="json"),
            reason=(
                f"Risk register for {len(queue)} open ticket(s). "
                "A Team Lead decides which interventions actually happen."
            ),
        )
        state.awaiting_approval = True
        self.store.snapshot(run_id, state)
        raise ApprovalRequired(approval.id, ApprovalKind.ESCALATION_REVIEW)
