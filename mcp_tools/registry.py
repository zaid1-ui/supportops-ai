"""Per-agent tool assignment (Part 7).

Tools are assigned by agent, not handed out globally. Two reasons, and the
second is the important one:

1. Every extra tool is a line in the agent's context and a plausible-looking
   wrong choice. An agent with three relevant tools picks better than one with
   eleven.
2. Capability follows role. The Validation Agent gets `get_chunk` but not
   `search_knowledge`: its job is to check the citations it was handed, not to
   go find better ones. Given search, a validator starts researching, becomes a
   co-author, and stops being an independent check. No agent gets `send_email`
   at all — sending is post-approval and runs outside the crew.
"""

from __future__ import annotations

from crewai.tools import BaseTool
from sqlalchemy.orm import Session

from mcp_tools.adapters import (
    AgentSuccessRatesTool,
    DraftEmailTool,
    FindSimilarTicketsTool,
    GetChunkTool,
    GetTicketTool,
    QueuePressureTool,
    RenderReportTool,
    SearchKnowledgeTool,
    UpdateTicketTool,
    WorkflowStatsTool,
)


def build_tools(db: Session) -> dict[str, list[BaseTool]]:
    """Tools per agent name, matching the assignments in docs/AGENTS.md."""
    return {
        "triage": [
            GetTicketTool(db=db),
            UpdateTicketTool(db=db),
        ],
        "research": [
            SearchKnowledgeTool(db=db),
            FindSimilarTicketsTool(db=db),
        ],
        "diagnostic": [
            SearchKnowledgeTool(db=db),
            QueuePressureTool(db=db),
        ],
        "resolution": [
            SearchKnowledgeTool(db=db),
            DraftEmailTool(),
        ],
        # Verification only. No search — see module docstring.
        "validation": [
            GetChunkTool(db=db),
        ],
        "escalation": [
            GetTicketTool(db=db),
            QueuePressureTool(db=db),
        ],
        "reporting": [
            AgentSuccessRatesTool(db=db),
            WorkflowStatsTool(db=db),
            QueuePressureTool(db=db),
            RenderReportTool(),
        ],
    }


# MCP servers, for `python -m mcp_tools.servers.<name>` and for clients that
# want to speak the protocol rather than call in-process.
MCP_SERVERS = {
    "knowledge": "mcp_tools.servers.knowledge",
    "tickets": "mcp_tools.servers.tickets",
    "email": "mcp_tools.servers.email",
    "analytics": "mcp_tools.servers.analytics",
    "reports": "mcp_tools.servers.reports",
}
