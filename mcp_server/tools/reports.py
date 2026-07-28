"""Report generation MCP tools.

Renders a report to markdown and writes it to the reports directory.
Used by the Reporting Agent.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from backend.app.core.config import settings

REPORT_DIR = Path(settings.upload_dir).parent / "reports"

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")


def _safe_name(title: str) -> str:
    """Filename from a title.

    The title is LLM-generated and therefore untrusted: unsanitised, a title
    of "../../etc/passwd" is a path traversal. Everything outside the
    allowlist is collapsed to a dash.
    """
    stem = _UNSAFE.sub("-", title.strip())[:60].strip("-") or "report"
    return f"{stem}-{uuid.uuid4().hex[:8]}.md"


def register_report_tools(mcp):
    @mcp.tool()
    def render_report(
        title: str,
        executive_summary: str,
        sections: list[dict] | None = None,
        recommendations: list[str] | None = None,
        citations: list[dict] | None = None,
    ) -> dict:
        """Render a report to markdown and write it to disk."""
        if not title.strip():
            return {"ok": False, "error": "title is empty"}
        if not executive_summary.strip():
            return {"ok": False, "error": "executive_summary is empty"}

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        parts = [
            f"# {title}",
            f"*Generated {now} — SupportOps AI*",
            "",
            "## Executive Summary",
            executive_summary,
        ]

        for s in sections or []:
            parts += ["", f"## {s.get('title', 'Section')}", s.get("body", "")]

        if recommendations:
            parts += ["", "## Recommendations"]
            parts += [f"{i}. {r}" for i, r in enumerate(recommendations, 1)]

        if citations:
            parts += ["", "## Sources"]
            for c in citations:
                page = f" p{c['page']}" if c.get("page") else ""
                parts.append(f"- `{c.get('chunk_id', '?')}` — {c.get('source', 'unknown')}{page}")

        markdown = "\n".join(parts)

        try:
            REPORT_DIR.mkdir(parents=True, exist_ok=True)
            path = REPORT_DIR / _safe_name(title)
            path.write_text(markdown, encoding="utf-8")
        except OSError as exc:
            return {"ok": False, "error": f"could not write report: {exc}"}

        return {
            "ok": True,
            "data": {"path": str(path), "title": title, "bytes": len(markdown), "markdown": markdown},
        }