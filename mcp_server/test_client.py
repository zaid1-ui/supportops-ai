"""Quick manual check that the MCP server responds to tool calls."""

import asyncio
from http import client
from importlib import resources
from fastmcp import Client
from fastmcp.client.transports import StdioTransport

transport = StdioTransport(
    command="python",
    args=["-m", "mcp_server.server"],
    cwd="C:\\Users\\HP\\supportops-ai",
)

async def main():
    async with Client(transport) as client:
        tools = await client.list_tools()
        print("Available tools:", [t.name for t in tools])

        result = await client.call_tool("get_ticket", {"ticket_id": "does-not-exist"})
        print("Result:", result)

        result = await client.call_tool("search_knowledge", {"query": "refund policy"})
        print("search_knowledge:", result.data)

        result = await client.call_tool("draft_email", {"to": "test@example.com", "subject": "Test", "body": "Hello"})
        print("draft_email:", result.data)

        result = await client.call_tool("queue_pressure", {})
        print("queue_pressure:", result.data)

        result = await client.call_tool("render_report", {
            "title": "Test Report",
            "executive_summary": "This is a test.",
        })
        print("render_report:", result.data)

        resources = await client.list_resources()
        print("Resources:", [r.uri for r in resources])
    
        result = await client.read_resource("schema://ticket")
        print("ticket_schema:", result[0].text[:200])

if __name__ == "__main__":
    asyncio.run(main())