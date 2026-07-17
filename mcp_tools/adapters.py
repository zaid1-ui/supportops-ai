"""CrewAI adapters over the MCP tools (Part 7).

Each adapter wraps an MCP tool implementation as a CrewAI `BaseTool`. The
implementation is shared with the MCP server — this layer only handles argument
schemas and result rendering.

Sessions are injected at construction. Building a session inside `_run` would
open one per tool call and leak them under retry; injecting means a run's tool
calls share the request's transaction and are visible to each other.
"""

from __future__ import annotations

from typing import Any

from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from mcp_tools.core import ToolResult
from mcp_tools.servers import analytics, email, knowledge, reports, tickets


# --------------------------------------------------------------------------
# Argument schemas
# --------------------------------------------------------------------------


class SearchKnowledgeArgs(BaseModel):
    query: str = Field(description="What to search for.")
    product_area: str | None = Field(default=None, description="Scope. Omit if unknown.")
    top_k: int = Field(default=5, description="Number of chunks to return.")


class GetChunkArgs(BaseModel):
    chunk_id: str = Field(description="Chunk id to fetch.")


class GetTicketArgs(BaseModel):
    ticket_id: str


class SimilarTicketsArgs(BaseModel):
    product_area: str | None = None
    intent: str | None = None
    limit: int = 5


class UpdateTicketArgs(BaseModel):
    ticket_id: str
    updates: dict = Field(description="Writable: intent, severity, product_area, queue.")


class DraftEmailArgs(BaseModel):
    to: str
    subject: str
    body: str


class AgentStatsArgs(BaseModel):
    since_hours: int = 168


class QueueArgs(BaseModel):
    pass


class RenderReportArgs(BaseModel):
    title: str
    executive_summary: str
    sections: list[dict] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    citations: list[dict] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Adapters
# --------------------------------------------------------------------------


class _DbTool(BaseTool):
    """Base for tools needing a session."""

    db: Any = None

    def _render(self, result: ToolResult) -> str:
        return result.to_text()


class SearchKnowledgeTool(_DbTool):
    name: str = "search_knowledge"
    description: str = (
        "Search the enterprise knowledge base. Returns text chunks with citations "
        "(chunk_id, source, page, score). Scope with product_area when known. "
        "Returning no results is a valid outcome — reformulate once before "
        "concluding a knowledge gap."
    )
    args_schema: type[BaseModel] = SearchKnowledgeArgs

    def _run(self, query: str, product_area: str | None = None, top_k: int = 5) -> str:
        return self._render(
            knowledge.search_knowledge(self.db, query, product_area=product_area, top_k=top_k)
        )


class GetChunkTool(_DbTool):
    name: str = "get_chunk"
    description: str = (
        "Fetch a chunk's canonical stored text by id. Use this to verify that a "
        "citation actually says what a draft claims it says."
    )
    args_schema: type[BaseModel] = GetChunkArgs

    def _run(self, chunk_id: str) -> str:
        return self._render(knowledge.get_chunk(self.db, chunk_id))


class GetTicketTool(_DbTool):
    name: str = "get_ticket"
    description: str = "Fetch a ticket by id, with its classification and SLA fields."
    args_schema: type[BaseModel] = GetTicketArgs

    def _run(self, ticket_id: str) -> str:
        return self._render(tickets.get_ticket(self.db, ticket_id))


class FindSimilarTicketsTool(_DbTool):
    name: str = "find_similar_tickets"
    description: str = (
        "Find previously RESOLVED tickets with the same product area or intent. "
        "Open tickets are excluded — an unresolved ticket is not precedent."
    )
    args_schema: type[BaseModel] = SimilarTicketsArgs

    def _run(self, product_area: str | None = None, intent: str | None = None, limit: int = 5) -> str:
        return self._render(
            tickets.find_similar_tickets(self.db, product_area=product_area, intent=intent, limit=limit)
        )


class UpdateTicketTool(_DbTool):
    name: str = "update_ticket"
    description: str = (
        "Write a classification back to a ticket. Writable fields: intent, severity, "
        "product_area, queue. Ticket status is not agent-writable."
    )
    args_schema: type[BaseModel] = UpdateTicketArgs

    def _run(self, ticket_id: str, updates: dict) -> str:
        return self._render(tickets.update_ticket(self.db, ticket_id, updates))


class DraftEmailTool(BaseTool):
    name: str = "draft_email"
    description: str = (
        "Compose an email. Does NOT send — sending requires human approval and is "
        "not available to you."
    )
    args_schema: type[BaseModel] = DraftEmailArgs

    def _run(self, to: str, subject: str, body: str) -> str:
        return email.draft_email(to, subject, body).to_text()


class AgentSuccessRatesTool(_DbTool):
    name: str = "agent_success_rates"
    description: str = "Per-agent task success rates over a time window."
    args_schema: type[BaseModel] = AgentStatsArgs

    def _run(self, since_hours: int = 168) -> str:
        return self._render(analytics.agent_success_rates(self.db, since_hours))


class WorkflowStatsTool(_DbTool):
    name: str = "workflow_stats"
    description: str = "Workflow run counts and completion rates by status."
    args_schema: type[BaseModel] = AgentStatsArgs

    def _run(self, since_hours: int = 168) -> str:
        return self._render(analytics.workflow_stats(self.db, since_hours))


class QueuePressureTool(_DbTool):
    name: str = "queue_pressure"
    description: str = (
        "Open tickets bucketed by SLA proximity (breached / at_risk / healthy), "
        "with the at-risk list."
    )
    args_schema: type[BaseModel] = QueueArgs

    def _run(self) -> str:
        return self._render(analytics.queue_pressure(self.db))


class RenderReportTool(BaseTool):
    name: str = "render_report"
    description: str = "Render a report to markdown and write it to the reports directory."
    args_schema: type[BaseModel] = RenderReportArgs

    def _run(
        self,
        title: str,
        executive_summary: str,
        sections: list[dict] | None = None,
        recommendations: list[str] | None = None,
        citations: list[dict] | None = None,
    ) -> str:
        return reports.render_report(
            title, executive_summary, sections or [], recommendations, citations
        ).to_text()
