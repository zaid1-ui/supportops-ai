"""MCP tool ecosystem (Part 7).

Named `mcp_tools`, not `mcp`: the assessment's suggested structure uses `mcp/`,
but that shadows the MCP SDK's own top-level package. With the repo root on
sys.path, `import mcp` inside this project resolves here instead of to the SDK,
and `from mcp.server import Server` fails with ModuleNotFoundError. Renaming the
directory is the only fix that keeps both importable.
"""

from mcp_tools.core import ToolError, ToolResult, fail, ok
from mcp_tools.registry import MCP_SERVERS, build_tools

__all__ = ["build_tools", "MCP_SERVERS", "ToolResult", "ToolError", "ok", "fail"]
