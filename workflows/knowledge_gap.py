"""Knowledge Gap Review workflow (Part 8, workflow 2).

    Research -> Diagnostic -> Validation -> Reporting -> human gate

Scheduled, sequential, batch. Reads unresolved and reopened tickets, probes the
knowledge base for each, and produces a prioritised content backlog.

Why the Validation Agent is in a reporting workflow: a knowledge gap and a
retrieval failure look identical from the outside — both are "we searched and
found nothing." Publishing the second as the first sends a Knowledge Manager off
to write an article that already exists. Validation's job here is to tell them
apart, which is the same groundedness check it runs on customer drafts.

Sequential, not hierarchical: this is a fixed pipeline over a batch. There is
nothing for a manager to decide, so a manager LLM would be pure cost.
"""

from __future__ import annotations

from crewai import Crew, Process, Task
from crewai.tools import BaseTool
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from agents.definitions import (
    build_diagnostic_agent,
    build_reporting_agent,
    build_research_agent,
    build_validation_agent,
)
from agents.prompts import REPORTING_TASK, RESEARCH_TASK
from agents.schemas import ReportingOutput, ResearchOutput, WorkflowState
from backend.app.core.logging import get_logger
from backend.app.models import ApprovalKind, EventType, RunStatus, Ticket, TicketStatus
from mcp_tools.registry import build_tools
from workflows.hitl import ApprovalGate, ApprovalRequired
from workflows.state import StateStore, TaskTimer

logger = get_logger(__name__)

WORKFLOW_NAME = "knowledge_gap_review"
BATCH_LIMIT = 20


class KnowledgeGapWorkflow:
    """Turns unresolved tickets into a prioritised knowledge backlog."""

    def __init__(self, db: Session, tools: dict[str, list[BaseTool]] | None = None) -> None:
        self.db = db
        self.store = StateStore(db)
        self.gate = ApprovalGate(db, self.store)
        self.tools = tools if tools is not None else build_tools(db)

    def _t(self, name: str) -> list[BaseTool]:
        return self.tools.get(name, [])

    def start(self, ticket_id: str | None = None) -> str:
        """Run the review. `ticket_id` is ignored — this workflow is a batch job.

        The signature matches the other workflows so POST /workflows/run can
        dispatch any of them without special-casing.
        """
        run = self.store.create_run(WORKFLOW_NAME)
        state = WorkflowState(run_id=run.id)

        try:
            candidates = self._candidates()
            if not candidates:
                self.store.emit(run.id, EventType.RUN_COMPLETED,
                                payload={"note": "no unresolved tickets to review"})
                self.store.set_status(run.id, RunStatus.COMPLETED)
                return run.id

            self.store.emit(run.id, EventType.TASK_STARTED,
                            payload={"candidates": [t.id for t in candidates]})
            self._review(run.id, state, candidates)
        except ApprovalRequired as gate:
            logger.info("run %s paused at %s", run.id, gate.kind.value)
        except Exception as exc:  # noqa: BLE001
            self.store.set_status(run.id, RunStatus.FAILED, error=str(exc))
            self.store.emit(run.id, EventType.RUN_FAILED, payload={"error": str(exc)})
            raise
        return run.id

    def resume(self, run_id: str) -> str:
        """Backlog approved. The report is the deliverable, so publishing ends it."""
        state, approval = self.gate.resume(run_id)
        self.store.emit(run_id, EventType.RUN_COMPLETED,
                        payload={"published_by": approval.decided_by})
        self.store.set_status(run_id, RunStatus.COMPLETED)
        return run_id

    def _candidates(self) -> list[Ticket]:
        """Unresolved, or resolved-then-reopened.

        A reopen is the strongest signal available: the knowledge base answered
        and the answer did not hold. That is a content defect, not a gap, and it
        outranks a ticket nobody has answered yet.
        """
        stmt = (
            select(Ticket)
            .where(or_(Ticket.status != TicketStatus.RESOLVED, Ticket.reopen_count > 0))
            .order_by(Ticket.reopen_count.desc())
            .limit(BATCH_LIMIT)
        )
        return list(self.db.execute(stmt).scalars().all())

    def _review(self, run_id: str, state: WorkflowState, tickets: list[Ticket]) -> None:
        research = build_research_agent(self._t("research"))
        diagnostic = build_diagnostic_agent(self._t("diagnostic"))
        validation = build_validation_agent(self._t("validation"))
        reporting = build_reporting_agent(self._t("reporting"))

        probes = "\n".join(
            f"- [{t.id}] {t.subject} (area={t.product_area or 'unknown'}, "
            f"reopens={t.reopen_count}): {t.body[:200]}"
            for t in tickets
        )

        probe_task = Task(
            description=RESEARCH_TASK.format(
                summary=(
                    "Probe the knowledge base for EACH ticket below. For every one where "
                    "no document answers it, record the gap.\n\n"
                    f"<tickets>\n{probes}\n</tickets>"
                ),
                intent="knowledge_gap_review",
                product_area="unknown",
            ),
            expected_output="A ResearchOutput. knowledge_gap=True if any ticket has no answer.",
            agent=research,
            output_pydantic=ResearchOutput,
        )

        cluster_task = Task(
            description=(
                "Cluster the misses from the research step into themes.\n\n"
                "A list of twenty unanswered tickets is not a backlog — it is a list. "
                "Group them by the missing subject, so each cluster becomes one article "
                "someone can actually write. Rank clusters by how many tickets they would "
                "have deflected, weighting reopened tickets double: a reopen means the "
                "existing content was wrong, which is worse than absent.\n\n"
                "Report only what the evidence supports. Do not invent themes to make the "
                "backlog look fuller."
            ),
            expected_output="Ranked clusters, each with the tickets it covers and why it matters.",
            agent=diagnostic,
            context=[probe_task],
        )

        verify_task = Task(
            description=(
                "Verify each claimed gap is real before it reaches a Knowledge Manager.\n\n"
                "A genuine gap and a retrieval failure are indistinguishable from the "
                "outside: both look like 'we searched and found nothing'. For each cluster, "
                "use get_chunk and check whether the knowledge base already covers it under "
                "different wording. Vocabulary mismatch between the customer's words and the "
                "product's own terminology is the usual cause of a false gap.\n\n"
                "FAIL any cluster where the content already exists. Say which chunk covers it. "
                "Sending someone to write an article that already exists wastes a week and "
                "teaches them to ignore these reports."
            ),
            expected_output="Each cluster marked real or already-covered, with the covering chunk id.",
            agent=validation,
            context=[cluster_task],
        )

        report_task = Task(
            description=REPORTING_TASK.format(
                report_type="knowledge gap backlog",
                data=(
                    "Use the verified clusters from the previous step. Every recommendation is "
                    "one article: what it must cover, which tickets it deflects, and the owner "
                    "(Knowledge Manager). Order by deflection value. Exclude anything the "
                    "validation step marked already-covered."
                ),
            ),
            expected_output="A ReportingOutput: a prioritised, owned content backlog.",
            agent=reporting,
            context=[verify_task],
            output_pydantic=ReportingOutput,
        )

        crew = Crew(
            agents=[research, diagnostic, validation, reporting],
            tasks=[probe_task, cluster_task, verify_task, report_task],
            process=Process.sequential,
            verbose=True,
        )

        with TaskTimer(self.store, run_id, "research", "knowledge_gap_review"):
            crew.kickoff()

        state.research = probe_task.output.pydantic
        state.report = report_task.output.pydantic
        self.store.snapshot(run_id, state, current_task="reporting")

        approval = self.gate.request(
            run_id,
            ApprovalKind.REPORT_APPROVAL,
            payload=state.report.model_dump(mode="json"),
            reason=(
                f"Knowledge gap backlog from {len(tickets)} ticket(s). "
                "A Knowledge Manager should confirm the priorities before this becomes work."
            ),
        )
        state.awaiting_approval = True
        self.store.snapshot(run_id, state)
        raise ApprovalRequired(approval.id, ApprovalKind.REPORT_APPROVAL)
