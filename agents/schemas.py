"""Typed handoff contracts between agents.

Every agent task declares one of these as `output_pydantic`. Agents therefore
hand each other schema-validated objects rather than free text, which is what
makes the failure modes in docs/AGENTS.md detectable instead of silent.
"""

from enum import Enum

from typing import Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------
# Enumerations
# --------------------------------------------------------------------------


class Severity(str, Enum):
    S1 = "S1"  # Total outage / data loss. Immediate escalation.
    S2 = "S2"  # Major feature broken, no workaround.
    S3 = "S3"  # Feature degraded, workaround exists.
    S4 = "S4"  # Question, cosmetic issue, feature request.


class Intent(str, Enum):
    BUG_REPORT = "bug_report"
    HOW_TO = "how_to"
    BILLING = "billing"
    ACCOUNT_ACCESS = "account_access"
    FEATURE_REQUEST = "feature_request"
    COMPLAINT = "complaint"
    OTHER = "other"


class Queue(str, Enum):
    TIER_1 = "tier_1"
    TIER_2 = "tier_2"
    BILLING = "billing"
    ENGINEERING = "engineering"


class ActionType(str, Enum):
    REPLY_ONLY = "reply_only"
    REPLY_AND_CLOSE = "reply_and_close"
    REQUEST_INFO = "request_info"
    ESCALATE = "escalate"


class ValidationVerdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# --------------------------------------------------------------------------
# Shared value objects
# --------------------------------------------------------------------------


class Citation(BaseModel):
    """A pointer back to the retrieved chunk that supports a claim."""

    doc_id: str = Field(description="Source document identifier.")
    chunk_id: str = Field(description="Identifier of the retrieved chunk.")
    source: str = Field(description="Human-readable document name.")
    page: Optional[int] = Field(default=None, description="Page number where applicable.")
    score: float = Field(description="Retrieval relevance score.")


class Evidence(BaseModel):
    """One retrieved fact plus its provenance."""

    claim: str = Field(description="A single factual statement drawn from the source.")
    citation: Citation


# --------------------------------------------------------------------------
# Agent outputs
# --------------------------------------------------------------------------


class TriageOutput(BaseModel):
    """Triage Agent → classification and routing decision."""

    intent: Intent
    severity: Severity
    product_area: str = Field(description="Product area the ticket concerns.")
    queue: Queue
    summary: str = Field(description="One-sentence restatement of the customer's problem.")
    confidence: float = Field(ge=0.0, le=1.0, description="Self-reported classification confidence.")
    reasoning: str = Field(description="Why this classification was chosen.")


class ResearchOutput(BaseModel):
    """Research Agent → grounded evidence, or an explicit admission of none."""

    evidence: list[Evidence] = Field(default_factory=list)
    similar_ticket_ids: list[str] = Field(default_factory=list)
    knowledge_gap: bool = Field(
        description="True when the knowledge base contains no answer. Never guess instead."
    )
    gap_description: Optional[str] = Field(
        default=None, description="What the knowledge base is missing, when knowledge_gap is True."
    )


class DiagnosticOutput(BaseModel):
    """Diagnostic Agent → root-cause hypothesis."""

    hypothesis: str = Field(description="Most probable root cause.")
    supporting_evidence: list[Citation] = Field(default_factory=list)
    alternatives_considered: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    missing_information: list[str] = Field(
        default_factory=list, description="What the customer must supply to confirm the hypothesis."
    )


class ResolutionOutput(BaseModel):
    """Resolution Agent → proposed action and drafted customer reply."""

    action: ActionType
    draft_response: str = Field(description="Customer-facing reply text.")
    citations: list[Citation] = Field(default_factory=list)
    internal_note: str = Field(description="Context for the human reviewer, never sent to the customer.")
    policy_refs: list[str] = Field(
        default_factory=list, description="Policy identifiers relied on, e.g. refund rules."
    )


class ValidationIssue(BaseModel):
    """One specific defect found by the Validation Agent."""

    category: str = Field(description="groundedness | policy | completeness | tone | safety")
    detail: str = Field(description="What is wrong.")
    offending_text: Optional[str] = Field(default=None, description="The span at fault.")


class ValidationOutput(BaseModel):
    """Validation Agent → the quality gate verdict."""

    verdict: ValidationVerdict
    grounded: bool = Field(description="Every factual claim traces to a supplied citation.")
    policy_compliant: bool
    complete: bool = Field(description="Addresses every question the customer asked.")
    issues: list[ValidationIssue] = Field(default_factory=list)
    critique: Optional[str] = Field(
        default=None, description="Actionable revision instruction fed back to the Resolution Agent."
    )


class EscalationOutput(BaseModel):
    """Escalation Agent → risk score and routing."""

    risk_level: RiskLevel
    risk_score: float = Field(ge=0.0, le=1.0)
    drivers: list[str] = Field(description="Factors raising the risk, most significant first.")
    escalate: bool
    target_queue: Optional[Queue] = Field(default=None)
    rationale: str


class ReportSection(BaseModel):
    title: str
    body: str


class ReportingOutput(BaseModel):
    """Reporting Agent → a rendered report."""

    title: str
    executive_summary: str
    sections: list[ReportSection]
    recommendations: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Workflow state
# --------------------------------------------------------------------------


class WorkflowState(BaseModel):
    """Authoritative run state, snapshotted to workflow_runs.state after each task.

    Passed through CrewAI task context so agents never free-text at each other.
    """

    run_id: str
    ticket_id: Optional[str] = None
    triage: Optional[TriageOutput] = None
    research: Optional[ResearchOutput] = None
    diagnostic: Optional[DiagnosticOutput] = None
    resolution: Optional[ResolutionOutput] = None
    validation: Optional[ValidationOutput] = None
    escalation: Optional[EscalationOutput] = None
    report: Optional[ReportingOutput] = None
    validation_attempts: int = 0
    awaiting_approval: bool = False
