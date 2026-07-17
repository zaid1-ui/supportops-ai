"""User model and roles (Part 10 authentication).

Roles mirror the target users in ARCHITECTURE.md §3. They gate approval
authority: a Tier-1 agent may approve a response, but only a lead may override
a triage classification or publish a report.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base
from backend.app.models.orchestration import utcnow


class Role(str, enum.Enum):
    AGENT = "agent"        # Tier-1. Approves responses.
    ENGINEER = "engineer"  # Tier-2. Handles escalations.
    LEAD = "lead"          # Overrides triage, publishes reports.
    ADMIN = "admin"        # Manages knowledge and users.


# Approval kinds each role may decide. Checked server-side: the frontend hiding
# a button is a UX affordance, not an authorisation boundary.
ROLE_APPROVALS: dict[Role, set[str]] = {
    Role.AGENT: {"response_approval"},
    Role.ENGINEER: {"response_approval", "escalation_review"},
    Role.LEAD: {"response_approval", "escalation_review", "triage_review", "report_approval"},
    Role.ADMIN: {"response_approval", "escalation_review", "triage_review", "report_approval"},
}


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(200))
    hashed_password: Mapped[str] = mapped_column(String(200))
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.AGENT)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    def may_decide(self, approval_kind: str) -> bool:
        return approval_kind in ROLE_APPROVALS.get(self.role, set())
