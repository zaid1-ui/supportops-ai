"""Shared plumbing for the MCP tool ecosystem.

Every tool's real logic is a plain, db-taking function returning ToolResult.
The @mcp.tool() wrapper in each tools/*.py file opens its own session and
calls that function — one implementation, two callers: the standalone
FastMCP server (real protocol) and the evaluation harness (direct call,
no server subprocess needed to test tool correctness in isolation).
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
    """Uniform envelope for every tool's core logic."""

    ok: bool
    data: Any = None
    error: str | None = None

    def to_dict(self) -> dict:
        """Render for the MCP JSON-RPC boundary."""
        return self.model_dump(mode="json", exclude_none=True)


def ok(data: Any) -> ToolResult:
    return ToolResult(ok=True, data=data)


def fail(error: str) -> ToolResult:
    logger.warning("tool failed: %s", error)
    return ToolResult(ok=False, error=error)