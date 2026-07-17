"""Report Generation MCP server (Part 7).

Renders a ReportingOutput to markdown and writes it to the outputs directory.
Used by the Reporting Agent.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import mcp.types as types
from mcp.server import Server

from backend.app.core.config import settings
from mcp_tools.core import ToolResult, fail, ok

TOOL_RENDER = "render_report"

REPORT_DIR = Path(settings.upload_dir).parent / "reports"

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")


def _safe_name(title: str) -> str:
    """Filename from a title.

    The title is LLM-generated and therefore untrusted: unsanitised, a title of
    "../../etc/passwd" is a path traversal. Everything outside the allowlist is
    collapsed to a dash.
    """
    stem = _UNSAFE.sub("-", title.strip())[:60].strip("-") or "report"
    return f"{stem}-{uuid.uuid4().hex[:8]}.md"


def render_report(
    title: str,
    executive_summary: str,
    sections: list[dict],
    recommendations: list[str] | None = None,
    citations: list[dict] | None = None,
) -> ToolResult:
    """Render a report to markdown and write it to disk."""
    if not title.strip():
        return fail("title is empty")
    if not executive_summary.strip():
        return fail("executive_summary is empty")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    parts = [f"# {title}", f"*Generated {now} — SupportOps AI*", "", "## Executive Summary", executive_summary]

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
        return fail(f"could not write report: {exc}")

    return ok({"path": str(path), "title": title, "bytes": len(markdown), "markdown": markdown})


server = Server("supportops-reports")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name=TOOL_RENDER,
            description="Render a report to markdown and write it to the reports directory.",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "executive_summary": {"type": "string"},
                    "sections": {"type": "array", "items": {"type": "object"}},
                    "recommendations": {"type": "array", "items": {"type": "string"}},
                    "citations": {"type": "array", "items": {"type": "object"}},
                },
                "required": ["title", "executive_summary"],
            },
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    if name == TOOL_RENDER:
        result = render_report(
            arguments["title"],
            arguments["executive_summary"],
            arguments.get("sections", []),
            arguments.get("recommendations"),
            arguments.get("citations"),
        )
    else:
        result = fail(f"unknown tool: {name}")
    return [types.TextContent(type="text", text=result.to_text())]


async def main() -> None:
    from mcp.server.stdio import stdio_server

    async with stdio_server() as (r, w):
        await server.run(r, w, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
