"""Per-agent tool assignment, backed by the standalone MCP server.

Replaces mcp_tools/registry.py. Same reasoning as before, now enforced at
the transport boundary instead of by import discipline:

1. Every extra tool is a line in the agent's context and a plausible-looking
   wrong choice. An agent with three relevant tools picks better than one
   with eleven.
2. Capability follows role. The Validation Agent gets `get_chunk` but not
   `search_knowledge`: its job is to check the citations it was handed, not
   go find better ones. No agent gets `send_email` — sending is
   post-approval and runs outside the crew.

Each call opens its own MCPServerAdapter (and therefore its own server
subprocess). Call build_tools() once per crew segment, not per task.
"""

from __future__ import annotations

from crewai_tools import MCPServerAdapter

from mcp_server.crew_client import SERVER_PARAMS

AGENT_TOOL_NAMES: dict[str, tuple[str, ...]] = {
    "triage": ("get_ticket", "update_ticket"),
    "research": ("search_knowledge", "find_similar_tickets"),
    "diagnostic": ("search_knowledge", "queue_pressure"),
    "resolution": ("search_knowledge", "draft_email"),
    # Verification only. No search — see module docstring.
    "validation": ("get_chunk",),
    "escalation": ("get_ticket", "queue_pressure"),
    "reporting": ("agent_success_rates", "workflow_stats", "queue_pressure", "render_report"),
}


def build_tools() -> tuple[dict[str, list], MCPServerAdapter]:
    """Connect to the MCP server once, return per-agent filtered tool lists.

    Returns (tools_by_agent, adapter). Caller owns the adapter's lifecycle —
    call adapter.stop() when the segment is done, or use it as a context
    manager wrapping the whole segment.
    """
    adapter = MCPServerAdapter(SERVER_PARAMS)
    all_tools = {t.name: t for t in adapter.tools}

    tools_by_agent = {
        agent: [all_tools[name] for name in names if name in all_tools]
        for agent, names in AGENT_TOOL_NAMES.items()
    }
    return tools_by_agent, adapter