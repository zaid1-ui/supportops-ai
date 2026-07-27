"""Quick manual check that the MCP server responds to tool calls."""

import asyncio
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

if __name__ == "__main__":
    asyncio.run(main())