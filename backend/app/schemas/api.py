"""Request and response schemas (Part 10 validation).

Pydantic models are the API contract. Every request body is validated before a
handler runs, and every response is declared, so the OpenAPI schema at /docs is
generated from the same source of truth the code enforces.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field


# ---- auth ----------------------------------------------------------------


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in_minutes: int


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    role: str


# ---- agents --------------------------------------------------------------


class AgentInfo(BaseModel):
    name: str
    role: str
    goal: str
    tier: str
    tools: list[str]
    max_iter: int
    allow_delegation: bool


class AgentExecuteRequest(BaseModel):
    agent: str = Field(description="Agent name from GET /agents.")
    task: str = Field(min_length=1, description="Task instruction for the agent.")
    context: dict[str, Any] = Field(default_factory=dict)


class AgentExecuteResponse(BaseModel):
    agent: str
    output: str
    duration_ms: float


# ---- documents -----------------------------------------------------------


class DocumentResponse(BaseModel):
    id: str
    filename: str
    doc_type: str
    product_area: str
    version: str | None
    status: str
    chunk_count: int
    error: str | None
    created_at: datetime


class SearchHit(BaseModel):
    chunk_id: str
    doc_id: str
    source: str
    page: int | None
    heading: str | None
    score: float
    content: str


class SearchResponse(BaseModel):
    query: str
    product_area: str | None
    hits: list[SearchHit]
    # Explicit rather than inferred from an empty list: the caller must be able
    # to tell "nothing matched" from "the filter excluded everything".
    total: int


# ---- workflows -----------------------------------------------------------


class WorkflowRunRequest(BaseModel):
    workflow: str = Field(description="Workflow name from GET /workflows.")
    ticket_id: str


class WorkflowRunResponse(BaseModel):
    run_id: str
    workflow: str
    status: str
    # Populated when the run paused at a gate, so the caller knows what to do
    # next without polling to discover it.
    awaiting_approval_id: str | None = None


class EventResponse(BaseModel):
    event_type: str
    agent: str | None
    task: str | None
    tool: str | None
    payload: dict
    duration_ms: float | None
    created_at: datetime


class WorkflowStatusResponse(BaseModel):
    run_id: str
    workflow: str
    status: str
    ticket_id: str | None
    current_task: str | None
    error: str | None
    state: dict
    events: list[EventResponse]
    started_at: datetime
    completed_at: datetime | None


# ---- approvals (Part 9) --------------------------------------------------


class ApprovalResponse(BaseModel):
    id: str
    run_id: str
    kind: str
    status: str
    reason: str
    payload: dict
    decided_by: str | None
    decided_at: datetime | None
    created_at: datetime


class ApprovalDecision(BaseModel):
    status: Literal["approved", "rejected", "edited"]
    edited_payload: dict | None = None
    feedback: str | None = None


# ---- metrics (Part 12) ---------------------------------------------------


class MetricsResponse(BaseModel):
    workflow_completion_rate: float
    agent_success_rates: dict[str, float]
    tool_usage: dict[str, int]
    failure_rate: float
    approval_rate: float
    total_runs: int
    runs_by_status: dict[str, int]


# ---- errors --------------------------------------------------------------


class ErrorDetail(BaseModel):
    code: str = Field(description="Stable machine-readable code. Switch on this, not on message.")
    message: str
    details: dict = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    """Every error from this API has this shape. See core/errors.py."""

    error: ErrorDetail
