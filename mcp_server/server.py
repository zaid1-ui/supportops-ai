"""Standalone FastMCP server for SupportOps AI."""

from __future__ import annotations

from fastmcp import FastMCP

from mcp_server.config import config
from mcp_server.tools.tickets import register_ticket_tools
from mcp_server.tools.knowledge import register_knowledge_tools
from mcp_server.tools.email import register_email_tools
from mcp_server.tools.analytics import register_analytics_tools
from mcp_server.tools.reports import register_report_tools
from mcp_server.resources.schemas import register_schema_resources
from mcp_server.prompts.templates import register_prompt_templates

mcp = FastMCP(config.server_name)
register_ticket_tools(mcp)
register_knowledge_tools(mcp)
register_email_tools(mcp)
register_analytics_tools(mcp)
register_report_tools(mcp)
register_schema_resources(mcp)
register_prompt_templates(mcp)

if __name__ == "__main__":
    if config.transport == "sse":
        mcp.run(transport="sse", host=config.sse_host, port=config.sse_port)
    else:
        mcp.run(transport="stdio")