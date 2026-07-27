"""Verify MCPServerAdapter can connect and lists all 11 tools."""

from crewai_tools import MCPServerAdapter

from mcp_server.crew_client import SERVER_PARAMS

with MCPServerAdapter(SERVER_PARAMS) as tools:
    print("Tools available to CrewAI:", [t.name for t in tools])