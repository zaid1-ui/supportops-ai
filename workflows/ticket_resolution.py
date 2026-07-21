"""Ticket Resolution workflow (Part 3 orchestration, Part 8 workflow 1).

Structure
---------
The run is split into *segments* separated by human gates:

    segment 1  TRIAGE                          -> gate: triage review (conditional)
    segment 2  RESEARCH -> DIAGNOSTIC ->
               RESOLUTION -> VALIDATION        (hierarchical, manager delegates)
    segment 3  ESCALATION                      -> gate: response approval (always)
    segment 4  EXECUTE -> REPORT

Why segments rather than one crew
---------------------------------
A CrewAI crew runs to completion. It cannot pause for a human who may take four
hours and it cannot survive a worker restart. Both are hard requirements here:
every customer-facing send is gated (Part 9), and an idle run must not hold a
worker (ARCHITECTURE.md §8.2).

So the gates define the segment boundaries. Each segment is a crew invocation
that runs to completion, snapshots state, and returns. `ApprovalRequired` unwinds
the worker; a human decision enqueues `resume()`, which re-enters at the next
segment. The state in `workflow_runs.state` is the only thing carried across —
nothing lives in memory between segments.

Delegation
----------
Segment 2 uses `Process.hierarchical`. The manager holds `allow_delegation=True`
and can re-dispatch to Research when Validation fails for missing evidence,
which is the one case where the right fix is to go back rather than retry
forward. Workers are all `allow_delegation=False` — mutual delegation between
workers loops, and a reviewer that can delegate hands work back to the author it
is supposed to be checking.
"""

from __future__ import annotations

from crewai import Crew, Process, Task
from crewai.tools import BaseTool
from sqlalchemy.orm import Session

from agents.definitions import (
    build_diagnostic_agent,
    build_escalation_agent,
    build_reporting_agent,
    build_research_agent,
    build_resolution_agent,
    build_triage_agent,
    build_validation_agent,
)
from agents.llm import Tier, get_llm
from agents.prompts import (
    DIAGNOSTIC_TASK,
    ESCALATION_TASK,
    RESEARCH_TASK,
    RESOLUTION_TASK,
    TRIAGE_TASK,
    VALIDATION_TASK,
)
from agents.schemas import (
    DiagnosticOutput,
    EscalationOutput,
    ResearchOutput,
    ResolutionOutput,
    TriageOutput,
    ValidationOutput,
    ValidationVerdict,
    WorkflowState,
)
from backend.app.core.logging import get_logger
from backend.app.models import ApprovalKind, EventType, RunStatus, Ticket
from workflows.hitl import (
    ApprovalGate,
    ApprovalRequired,
    needs_response_approval,
    needs_triage_review,
)
from workflows.recovery import RecoveryExhausted, should_retry_validation
from workflows.state import StateStore, TaskTimer

logger = get_logger(__name__)

WORKFLOW_NAME = "ticket_resolution"


class TicketResolutionWorkflow:
    """Orchestrates the ticket resolution crew across gate-separated segments."""

    def __init__(
        self,
        db: Session,
        tools: dict[str, list[BaseTool]] | None = None,
    ) -> None:
        self.db = db
        self.store = StateStore(db)
        self.gate = ApprovalGate(db, self.store)
        # Tools are injected per agent name. Empty until the MCP layer (Part 7)
        # is wired in; the orchestration contract does not depend on them.
        self.tools = tools or {}

    def _t(self, name: str) -> list[BaseTool]:
        return self.tools.get(name, [])

    # ------------------------------------------------------------------
    # Entry points
    # ------------------------------------------------------------------

    def start(self, ticket_id: str) -> str:
        """Begin a run. Returns the run id immediately on a gate."""
        ticket = self.db.get(Ticket, ticket_id)
        if ticket is None:
            raise LookupError(f"No such ticket: {ticket_id}")

        run = self.store.create_run(WORKFLOW_NAME, ticket_id=ticket_id)
        state = WorkflowState(run_id=run.id, ticket_id=ticket_id)

        try:
            self._run_from(run.id, state, ticket, start_at="triage")
        except ApprovalRequired as gate:
            logger.info("run %s paused at %s", run.id, gate.kind.value)
        except RecoveryExhausted as exc:
            self.store.set_status(run.id, RunStatus.ESCALATED, error=str(exc))
        return run.id

    def resume(self, run_id: str) -> str:
        """Continue a paused run after a human decision."""
        state, approval = self.gate.resume(run_id)
        ticket = self.db.get(Ticket, state.ticket_id) if state.ticket_id else None
        if ticket is None:
            raise LookupError(f"Run {run_id} has no ticket")

        # Re-enter at the segment after the gate that paused us.
        start_at = {
            ApprovalKind.TRIAGE_REVIEW: "research",
            ApprovalKind.RESPONSE_APPROVAL: "execute",
        }.get(approval.kind, "research")

        try:
            self._run_from(run_id, state, ticket, start_at=start_at)
        except ApprovalRequired as gate:
            logger.info("run %s paused again at %s", run_id, gate.kind.value)
        except RecoveryExhausted as exc:
            self.store.set_status(run_id, RunStatus.ESCALATED, error=str(exc))
        return run_id

    # ------------------------------------------------------------------
    # Segment driver
    # ------------------------------------------------------------------

    def _run_from(
        self,
        run_id: str,
        state: WorkflowState,
        ticket: Ticket,
        *,
        start_at: str,
    ) -> None:
        segments = ["triage", "research", "escalate", "execute"]
        for segment in segments[segments.index(start_at) :]:
            getattr(self, f"_segment_{segment}")(run_id, state, ticket)

    # ------------------------------------------------------------------
    # Segment 1 — Triage
    # ------------------------------------------------------------------

    def _segment_triage(self, run_id: str, state: WorkflowState, ticket: Ticket) -> None:
        agent = build_triage_agent(self._t("triage"))
        task = Task(
            description=TRIAGE_TASK.format(
                subject=ticket.subject,
                customer_email=ticket.customer_email,
                account_tier=ticket.account_tier,
                body=ticket.body,
                product_areas=_product_areas(),
            ),
            expected_output="A TriageOutput with calibrated confidence.",
            agent=agent,
            output_pydantic=TriageOutput,
        )

        with TaskTimer(self.store, run_id, "triage", "classify"):
            result = Crew(agents=[agent], tasks=[task], process=Process.sequential).kickoff()

        state.triage = result.pydantic
        self.store.snapshot(run_id, state, current_task="triage")

        # Persist the classification back onto the ticket.
        ticket.intent = state.triage.intent.value
        ticket.severity = state.triage.severity.value
        ticket.product_area = state.triage.product_area
        ticket.queue = state.triage.queue.value
        self.db.commit()

        if needs_triage_review(state):
            approval = self.gate.request(
                run_id,
                ApprovalKind.TRIAGE_REVIEW,
                payload=state.triage.model_dump(mode="json"),
                reason=(
                    f"Classification confidence {state.triage.confidence:.2f} is below "
                    f"threshold. Ambiguous ticket — confirm before research spend."
                ),
            )
            state.awaiting_approval = True
            self.store.snapshot(run_id, state)
            raise ApprovalRequired(approval.id, ApprovalKind.TRIAGE_REVIEW)

    # ------------------------------------------------------------------
    # Segment 2 — Research, Diagnostic, Resolution, Validation
    # ------------------------------------------------------------------

    def _segment_research(self, run_id: str, state: WorkflowState, ticket: Ticket) -> None:
        """The reasoning segment. Hierarchical so the manager can re-dispatch."""
        research = build_research_agent(self._t("research"))
        diagnostic = build_diagnostic_agent(self._t("diagnostic"))
        resolution = build_resolution_agent(self._t("resolution"))
        validation = build_validation_agent(self._t("validation"))

        research_task = Task(
            description=RESEARCH_TASK.format(
                summary=state.triage.summary,
                intent=state.triage.intent.value,
                product_area=state.triage.product_area,
            ),
            expected_output="A ResearchOutput: cited evidence, or an explicit knowledge gap.",
            agent=research,
            output_pydantic=ResearchOutput,
        )

        diagnostic_task = Task(
            description=DIAGNOSTIC_TASK.format(
                summary=state.triage.summary,
                evidence="{research_evidence}",
                similar_tickets="{research_similar}",
            ),
            expected_output="A DiagnosticOutput with confidence tracking the evidence.",
            agent=diagnostic,
            # Agent communication: typed output flows via task context, not prose.
            context=[research_task],
            output_pydantic=DiagnosticOutput,
        )

        crew = Crew(
            agents=[research, diagnostic],
            tasks=[research_task, diagnostic_task],
            process=Process.hierarchical,
            manager_llm=get_llm(Tier.REASONING),
            verbose=True,
        )

        with TaskTimer(self.store, run_id, "research", "gather_and_diagnose"):
            crew.kickoff()

        state.research = research_task.output.pydantic
        state.diagnostic = diagnostic_task.output.pydantic
        self.store.snapshot(run_id, state, current_task="diagnostic")

        # A knowledge gap is a real outcome, not an error. It feeds the Knowledge
        # Gap workflow and there is nothing to draft from, so stop here.
        if state.research.knowledge_gap:
            self.store.emit(
                run_id,
                EventType.DEGRADED,
                agent="research",
                payload={"knowledge_gap": state.research.gap_description},
            )

        self._draft_and_validate(run_id, state, ticket, resolution, validation)

    def _draft_and_validate(
        self,
        run_id: str,
        state: WorkflowState,
        ticket: Ticket,
        resolution_agent,
        validation_agent,
    ) -> None:
        """Draft, validate, and revise on failure.

        The retry loop is explicit Python rather than a CrewAI construct because
        the cap has to be enforced from outside: a prompt cannot reliably count
        its own attempts, and two LLMs left to iterate on each other will not
        stop on their own.
        """
        critique: str | None = None

        while True:
            draft_task = Task(
                description=RESOLUTION_TASK.format(
                    subject=ticket.subject,
                    body=ticket.body,
                    hypothesis=state.diagnostic.hypothesis,
                    confidence=state.diagnostic.confidence,
                    missing_information=state.diagnostic.missing_information,
                    evidence=_render_evidence(state),
                    policies=_policies(),
                )
                + (f"\n\nA previous draft was rejected. Fix exactly this:\n{critique}\n" if critique else ""),
                expected_output="A ResolutionOutput with every claim cited.",
                agent=resolution_agent,
                output_pydantic=ResolutionOutput,
            )

            with TaskTimer(self.store, run_id, "resolution", "draft"):
                Crew(agents=[resolution_agent], tasks=[draft_task], process=Process.sequential).kickoff()
            state.resolution = draft_task.output.pydantic
            self.store.snapshot(run_id, state, current_task="resolution")

            validate_task = Task(
                description=VALIDATION_TASK.format(
                    body=ticket.body,
                    draft_response=state.resolution.draft_response,
                    citations=_render_citations(state.resolution.citations),
                    policies=_policies(),
                ),
                expected_output="A ValidationOutput. FAIL requires an actionable critique.",
                agent=validation_agent,
                output_pydantic=ValidationOutput,
            )

            with TaskTimer(self.store, run_id, "validation", "review"):
                Crew(agents=[validation_agent], tasks=[validate_task], process=Process.sequential).kickoff()
            state.validation = validate_task.output.pydantic
            self.store.snapshot(run_id, state, current_task="validation")

            if state.validation.verdict is ValidationVerdict.PASS:
                return

            state.validation_attempts += 1
            self.store.emit(
                run_id,
                EventType.VALIDATION_FAILED,
                agent="validation",
                payload={
                    "attempt": state.validation_attempts,
                    "issues": [i.model_dump(mode="json") for i in state.validation.issues],
                },
            )
            self.store.snapshot(run_id, state)

            if not should_retry_validation(state.validation_attempts):
                # Ladder exhausted. Degrade to a human, never to a best-effort answer.
                raise RecoveryExhausted(
                    f"Validation failed {state.validation_attempts} times: "
                    f"{state.validation.critique}"
                )

            critique = state.validation.critique

    # ------------------------------------------------------------------
    # Segment 3 — Escalation, then the mandatory approval gate
    # ------------------------------------------------------------------

    def _segment_escalate(self, run_id: str, state: WorkflowState, ticket: Ticket) -> None:
        agent = build_escalation_agent(self._t("escalation"))
        age_hours = _age_hours(ticket)

        task = Task(
            description=ESCALATION_TASK.format(
                severity=state.triage.severity.value,
                account_tier=ticket.account_tier,
                age_hours=age_hours,
                sla_hours=ticket.sla_hours,
                reopen_count=ticket.reopen_count,
                message_count=ticket.message_count,
                latest_message=ticket.body,
                action=state.resolution.action.value,
                confidence=state.diagnostic.confidence,
            ),
            expected_output="An EscalationOutput naming only score-moving drivers.",
            agent=agent,
            output_pydantic=EscalationOutput,
        )

        with TaskTimer(self.store, run_id, "escalation", "score_risk"):
            Crew(agents=[agent], tasks=[task], process=Process.sequential).kickoff()

        state.escalation = task.output.pydantic
        self.store.snapshot(run_id, state, current_task="escalation")

        # The unconditional gate. Every customer-facing action stops here.
        if needs_response_approval(state):
            approval = self.gate.request(
                run_id,
                ApprovalKind.RESPONSE_APPROVAL,
                payload={
                    "draft_response": state.resolution.draft_response,
                    "action": state.resolution.action.value,
                    "citations": [c.model_dump(mode="json") for c in state.resolution.citations],
                    "internal_note": state.resolution.internal_note,
                    "escalation": state.escalation.model_dump(mode="json"),
                },
                reason="Customer-facing response requires human approval before send.",
            )
            state.awaiting_approval = True
            self.store.snapshot(run_id, state)
            raise ApprovalRequired(approval.id, ApprovalKind.RESPONSE_APPROVAL)

    # ------------------------------------------------------------------
    # Segment 4 — Execute and report
    # ------------------------------------------------------------------

    def _segment_execute(self, run_id: str, state: WorkflowState, ticket: Ticket) -> None:
        # Structural enforcement. Not a prompt instruction — a check.
        if not self.gate.is_cleared(run_id, ApprovalKind.RESPONSE_APPROVAL):
            raise PermissionError(
                f"Run {run_id} reached execute without an approved RESPONSE_APPROVAL"
            )

        # Send + ticket update go through email_mcp / ticket_db_mcp (Part 7).
        # Both are idempotent on run_id: a retried send must not double-send.
        self.store.emit(
            run_id,
            EventType.TOOL_CALLED,
            agent="resolution",
            tool="email_mcp.send",
            payload={"action": state.resolution.action.value, "idempotency_key": run_id},
        )

        agent = build_reporting_agent(self._t("reporting"))
        self.store.emit(run_id, EventType.RUN_COMPLETED, payload={"reported_by": agent.role})
        self.store.set_status(run_id, RunStatus.COMPLETED)


# --------------------------------------------------------------------------
# Context rendering
# --------------------------------------------------------------------------
# Templates are filled here, never by an LLM. That boundary is what keeps
# retrieved documents and customer text as data rather than instructions.


def _render_evidence(state: WorkflowState) -> str:
    if state.research is None or not state.research.evidence:
        return "(no evidence retrieved)"
    return "\n".join(
        f"- {e.claim} [{e.citation.source} p{e.citation.page} #{e.citation.chunk_id}]"
        for e in state.research.evidence
    )


def _render_citations(citations) -> str:
    if not citations:
        return "(none supplied)"
    return "\n".join(f"- #{c.chunk_id} {c.source} p{c.page} (score {c.score:.2f})" for c in citations)


def _product_areas() -> str:
    """Enterprise context. Replaced by a knowledge-base lookup in Part 5."""
    return "\n".join(
        f"- {a}" for a in ["exports", "billing", "authentication", "integrations", "reporting", "api"]
    )


def _policies() -> str:
    """Enterprise context. Replaced by a knowledge-base lookup in Part 5."""
    return (
        "- Refunds require a manager approval above $500.\n"
        "- Never commit to a roadmap date.\n"
        "- Never disclose other customers' data or internal system detail.\n"
        "- SLA credits are governed by the contract, not by support discretion."
    )


def _age_hours(ticket: Ticket) -> float:
    from datetime import datetime, timezone

    created = ticket.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - created).total_seconds() / 3600