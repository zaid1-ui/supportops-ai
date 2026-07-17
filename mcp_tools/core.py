"""Shared plumbing for the MCP tool ecosystem (Part 7).

Every tool is exposed twice from one implementation:

  1. As an MCP server (`mcp_tools/servers/*.py`) — real protocol, stdio
     transport, usable by any MCP client.
  2. As a CrewAI `BaseTool` (`mcp_tools/adapters.py`) — in-process, which is how
     this platform's agents call them.

The implementation is shared rather than duplicated. Two copies of a tool drift,
and the copy the agents use is the one that stops matching its documentation.

Why both: the MCP server is the interoperable contract; in-process adapters are
what agents actually run. Round-tripping every retrieval through a stdio
subprocess would add a process hop per call for no benefit inside a single
deployment.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel

from backend.app.core.logging import get_logger

logger = get_logger(__name__)


class ToolError(Exception):
    """A tool failed in a way the caller should see rather than retry blindly."""


class ToolResult(BaseModel):
    """Uniform envelope for every tool.

    Failures return `ok=False` rather than raising across the MCP boundary,
    because an agent needs to *read* the failure to decide what to do next — a
    stack trace it cannot see teaches it nothing, and a tool that silently
    returns nothing on error is indistinguishable from one that found nothing.
    """

    ok: bool
    data: Any = None
    error: str | None = None

    def to_text(self) -> str:
        """Render for an LLM. Tool output is text at the MCP boundary."""
        if not self.ok:
            return f"TOOL ERROR: {self.error}"
        if isinstance(self.data, str):
            return self.data
        return json.dumps(self.data, indent=2, default=str)


def ok(data: Any) -> ToolResult:
    return ToolResult(ok=True, data=data)


def fail(error: str) -> ToolResult:
    logger.warning("tool failed: %s", error)
    return ToolResult(ok=False, error=error)
