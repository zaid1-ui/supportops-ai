"""MCP client used by CrewAI agents to reach the standalone MCP server.

This replaces mcp_tools/adapters.py: agents no longer import tool logic
directly, they connect to mcp_server/server.py as a subprocess over stdio
and call tools through the protocol.
"""

from __future__ import annotations

from mcp import StdioServerParameters

SERVER_PARAMS = StdioServerParameters(
    command="python",
    args=["-m", "mcp_server.server"],
    env=None,  # inherits parent process env
)