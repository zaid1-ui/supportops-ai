"""Report routes — Lead only (role differentiation).

The Lead is the operational decision-maker: publishing reports to stakeholders
is their call. These routes are gated with require_role(Role.LEAD), separate
from the Admin's platform-management domain.

Reports are markdown files rendered by the Reporting Agent / MCP render_report
tool into data/reports/. This layer lists them and drives the publish (the
REPORT_APPROVAL gate) action.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, status

from backend.app.api.deps import DbSession, LeadUser
from backend.app.core.config import settings
from backend.app.schemas.api import PublishReportRequest, ReportFile

router = APIRouter(prefix="/reports", tags=["reports"])

REPORT_DIR = Path(settings.upload_dir).parent / "reports"


def _report_dir() -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    return REPORT_DIR


@router.get("", response_model=list[ReportFile])
def list_reports(db: DbSession, _: LeadUser) -> list[ReportFile]:
    """List generated reports on disk. Lead only."""
    out: list[ReportFile] = []
    for path in sorted(_report_dir().glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
        out.append(
            ReportFile(
                filename=path.name,
                size_bytes=path.stat().st_size,
                modified_at=datetime.fromtimestamp(path.stat().st_mtime),
            )
        )
    return out


@router.post("/publish", response_model=ReportFile)
def publish_report(
    payload: PublishReportRequest, db: DbSession, _: LeadUser
) -> ReportFile:
    """Mark a report as published to stakeholders. Lead only.

    The filename is treated as untrusted input (it could come from the LLM
    classification of a report title), so only the basename is used and it must
    reference a file that already exists in the reports directory.
    """
    safe_name = Path(payload.filename).name
    path = _report_dir() / safe_name
    if not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"No such report: {safe_name}"
        )

    # A real deployment would record the publish in the events/approvals tables.
    # For now, the publish action simply confirms the report exists and is
    # readable, and returns its canonical metadata.
    return ReportFile(
        filename=safe_name,
        size_bytes=path.stat().st_size,
        modified_at=datetime.fromtimestamp(path.stat().st_mtime),
        published=True,
    )
