"""MCP client used by CrewAI agents to reach the standalone MCP server.

This replaces mcp_tools/adapters.py: agents no longer import tool logic
directly, they connect to mcp_server/server.py through the protocol,
either as a stdio subprocess (server spawned per-segment) or over SSE
(server already running independently, e.g. `python -m mcp_server.server`
with MCP_TRANSPORT=sse in its own terminal). Which one is used is decided
by config.transport, so the two-line diff in AGENT_TOOL_NAMES / registry.py
doesn't need to know or care which transport is active.
"""

from __future__ import annotations

from mcp import StdioServerParameters

from mcp_server.config import config

if config.transport == "sse":
    # Dict form is what MCPServerAdapter expects for a server reached over
    # SSE — it does not spawn a process, it connects to one already running.
    SERVER_PARAMS: StdioServerParameters | dict = {
        "url": f"http://{config.sse_host}:{config.sse_port}/sse"
    }
else:
    SERVER_PARAMS = StdioServerParameters(
        command="python",
        args=["-m", "mcp_server.server"],
        env=None,  # inherits parent process env
    )