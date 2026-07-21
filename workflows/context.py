"""Context engineering (Part 5). Strategy documented in docs/CONTEXT_ENGINEERING.md.

Five sources, assembled under a token budget, in priority order:

    task       current workflow state          — never dropped
    user       role and permissions            — never dropped
    enterprise retrieved documents + policy    — compressed, then truncated
    long_term  resolved tickets, past outcomes — dropped first
    short_term recent conversation turns       — compressed to a summary

The budget is the point. Without one, context assembly is "concatenate
everything and hope," which fails silently: the model receives a prompt that
overflows, the provider truncates from wherever it likes, and the piece that
gets cut is invisible. Cutting deliberately, worst-first, is the whole job.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from agents.schemas import WorkflowState
from backend.app.core.logging import get_logger
from backend.app.models import Role, Ticket, TicketStatus, User
from rag.ingestion.chunking import count_tokens
from rag.retrieval.retriever import Retriever, render_context

logger = get_logger(__name__)


# Priority order, lowest value = dropped last. Task and user context are
# structural: an agent without them does not know what it is doing or for whom,
# so trimming them produces confident work on the wrong problem.
PRIORITY = ["task", "user", "enterprise", "long_term", "short_term"]

# Leaves room for the response and for CrewAI's own scaffolding, which is not
# free. Sized for a 128k-context model with deliberate slack.
DEFAULT_BUDGET = 8_000


@dataclass
class ContextBlock:
    name: str
    content: str
    tokens: int = 0
    compressed: bool = False

    def __post_init__(self) -> None:
        self.tokens = count_tokens(self.content)


@dataclass
class AssembledContext:
    blocks: list[ContextBlock] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)
    total_tokens: int = 0

    def render(self) -> str:
        """Delimited blocks. The tags are the injection boundary.

        Retrieved documents and customer text are data. Wrapping each block and
        naming it means a document containing "ignore previous instructions"
        arrives as the contents of <enterprise>, not as a new instruction.
        """
        return "\n\n".join(f"<{b.name}>\n{b.content}\n</{b.name}>" for b in self.blocks)


class ContextEngine:
    """Assembles agent context from the five sources under a token budget."""

    def __init__(self, db: Session, budget: int = DEFAULT_BUDGET) -> None:
        self.db = db
        self.budget = budget

    # -- sources ---------------------------------------------------------

    def task_context(self, state: WorkflowState) -> ContextBlock:
        """Where the workflow is right now."""
        lines = [f"run_id: {state.run_id}", f"ticket_id: {state.ticket_id}"]
        if state.triage:
            lines.append(
                f"classified: {state.triage.intent.value} / {state.triage.severity.value} / "
                f"{state.triage.product_area} (confidence {state.triage.confidence:.2f})"
            )
        if state.research:
            lines.append(
                f"evidence: {len(state.research.evidence)} claims, "
                f"knowledge_gap={state.research.knowledge_gap}"
            )
        if state.diagnostic:
            lines.append(f"hypothesis: {state.diagnostic.hypothesis} "
                         f"(confidence {state.diagnostic.confidence:.2f})")
        if state.validation_attempts:
            lines.append(f"validation attempts so far: {state.validation_attempts}")
        return ContextBlock("task", "\n".join(lines))

    def user_context(self, user: User | None) -> ContextBlock:
        """Who is reviewing, and what they are allowed to decide.

        Included because it changes what an agent should write, not only what
        the UI shows: a draft going to a Tier-1 agent should not assume the
        engineering context a Tier-2 reviewer has.
        """
        if user is None:
            return ContextBlock("user", "reviewer: unassigned (write for a Tier-1 agent)")
        approvals = {
            Role.AGENT: "responses",
            Role.ENGINEER: "responses, escalations",
            Role.LEAD: "responses, escalations, triage overrides, reports",
            Role.ADMIN: "all",
        }.get(user.role, "responses")
        return ContextBlock(
            "user",
            f"reviewer: {user.full_name} ({user.role.value})\nmay approve: {approvals}",
        )

    def enterprise_context(
        self, query: str, *, product_area: str | None = None, top_k: int = 5
    ) -> ContextBlock:
        """Retrieved documents plus standing policy.

        Retrieval failure is reported, not swallowed. An empty enterprise block
        is indistinguishable from a genuine knowledge gap, and the Research
        Agent would report a gap that does not exist.
        """
        try:
            hits = Retriever(self.db).search(query, top_k=top_k, product_area=product_area)
            body = render_context(hits)
        except Exception as exc:  # noqa: BLE001
            logger.warning("enterprise context retrieval failed: %s", exc)
            body = f"(retrieval unavailable: {exc} — do not answer from general knowledge)"
        return ContextBlock("enterprise", f"{body}\n\n--- policy ---\n{POLICIES}")

    def long_term_context(self, product_area: str | None, intent: str | None) -> ContextBlock:
        """Resolved tickets with the same shape. Historical outcomes."""
        stmt = select(Ticket).where(Ticket.status == TicketStatus.RESOLVED)
        if product_area and product_area != "unknown":
            stmt = stmt.where(Ticket.product_area == product_area)
        if intent:
            stmt = stmt.where(Ticket.intent == intent)
        rows = self.db.execute(stmt.limit(5)).scalars().all()
        if not rows:
            return ContextBlock("long_term", "(no comparable resolved tickets)")
        return ContextBlock(
            "long_term",
            "\n".join(f"- [{t.id}] {t.subject} ({t.severity}) — resolved" for t in rows),
        )

    def short_term_context(self, turns: list[str]) -> ContextBlock:
        """Recent conversation. Compressed on the way in when long.

        Support threads are repetitive — the customer restates the problem each
        message. Keeping the first turn and the last three preserves the
        original complaint and the current state, which is where the
        information actually is.
        """
        if not turns:
            return ContextBlock("short_term", "(no prior turns)")
        if len(turns) <= 4:
            return ContextBlock("short_term", "\n".join(turns))
        kept = [turns[0], f"[... {len(turns) - 4} intermediate turns omitted ...]", *turns[-3:]]
        block = ContextBlock("short_term", "\n".join(kept))
        block.compressed = True
        return block

    # -- assembly --------------------------------------------------------

    def assemble(self, blocks: list[ContextBlock]) -> AssembledContext:
        """Fit blocks into the budget: compress, then drop, worst-first.

        Two passes, in this order on purpose. Compressing a low-priority block
        may save enough to keep a high-priority one whole, so compression is
        tried before anything is dropped. Only when compression is not enough
        does a block get cut, and the cut is recorded.
        """
        ordered = sorted(blocks, key=lambda b: PRIORITY.index(b.name) if b.name in PRIORITY else 99)
        total = sum(b.tokens for b in ordered)
        dropped: list[str] = []

        if total > self.budget:
            # Pass 1 — compress from the bottom of the priority list up.
            for block in reversed(ordered):
                if total <= self.budget:
                    break
                if block.name in ("task", "user"):
                    continue  # structural; compressing these corrupts the run
                saved = self._compress(block)
                total -= saved

        if total > self.budget:
            # Pass 2 — drop, lowest priority first.
            for block in reversed(list(ordered)):
                if total <= self.budget:
                    break
                if block.name in ("task", "user"):
                    continue
                ordered.remove(block)
                dropped.append(block.name)
                total -= block.tokens

        if dropped:
            # Never silent. A prompt assembled from less than it asked for is a
            # degradation, and Part 12 counts degradations.
            logger.warning("context budget exceeded; dropped: %s", ", ".join(dropped))

        return AssembledContext(blocks=ordered, dropped=dropped, total_tokens=total)

    @staticmethod
    def _compress(block: ContextBlock) -> int:
        """Truncate a block to its head. Returns tokens saved.

        Head, not tail: retrieval returns results ranked by relevance, so the
        top of the enterprise block is the best evidence. Truncating the tail
        loses the weakest matches, which is the correct thing to lose.

        No LLM summarisation here — that would add a model call, latency, and a
        second thing that can hallucinate, inside the code path whose whole job
        is keeping the context faithful.
        """
        if block.compressed:
            return 0
        before = block.tokens
        keep = block.content[: int(len(block.content) * 0.5)]
        block.content = keep.rsplit("\n", 1)[0] + "\n[... truncated to fit context budget ...]"
        block.tokens = count_tokens(block.content)
        block.compressed = True
        return before - block.tokens


POLICIES = """\
- Refunds above $500 require manager approval.
- Never commit to a roadmap date.
- Never disclose other customers' data or internal system detail.
- SLA credits are governed by the contract, not by support discretion."""
