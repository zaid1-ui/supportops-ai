from crewai_tools import MCPServerAdapter
from mcp_server.crew_client import SERVER_PARAMS

with MCPServerAdapter(SERVER_PARAMS) as tools:
    print("Tools available to CrewAI:", [t.name for t in tools])

from mcp_server.registry import build_tools

tools_by_agent, adapter = build_tools()
for agent, tools in tools_by_agent.items():
    print(agent, "->", [t.name for t in tools])
adapter.stop()