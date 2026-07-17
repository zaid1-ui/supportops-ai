"""Knowledge Retrieval MCP server (Part 7).

Wraps the RAG retriever (Part 6). The single most important tool in the
platform: the Research Agent's grounding guarantee is only as good as what this
returns, and every citation downstream originates here.
"""

from __future__ import annotations

import asyncio

import mcp.types as types
from mcp.server import Server
from sqlalchemy.orm import Session

from mcp_tools.core import ToolResult, fail, ok
from rag.retrieval.retriever import Retriever

TOOL_SEARCH = "search_knowledge"
TOOL_GET_CHUNK = "get_chunk"


# -- implementation ------------------------------------------------------


def search_knowledge(
    db: Session,
    query: str,
    *,
    product_area: str | None = None,
    top_k: int = 5,
) -> ToolResult:
    """Search enterprise knowledge. Returns chunks with resolved citations."""
    if not query or not query.strip():
        return fail("query is empty")
    try:
        hits = Retriever(db).search(query, top_k=top_k, product_area=product_area)
    except Exception as exc:  # noqa: BLE001
        # Chroma down. Report it rather than returning [] — an empty result is
        # indistinguishable from a genuine knowledge gap, and the Research Agent
        # would report a gap that does not exist.
        return fail(f"knowledge search unavailable: {exc}")

    if not hits:
        return ok(
            {
                "results": [],
                "note": (
                    "No results. If the query used the customer's wording, retry with "
                    "the product's own terminology before concluding a knowledge gap."
                ),
            }
        )

    return ok(
        {
            "results": [
                {
                    "chunk_id": h.citation.chunk_id,
                    "content": h.content,
                    "source": h.citation.source,
                    "page": h.citation.page,
                    "heading": h.heading,
                    "score": h.citation.score,
                    "doc_id": h.citation.doc_id,
                }
                for h in hits
            ]
        }
    )


def get_chunk(db: Session, chunk_id: str) -> ToolResult:
    """Fetch a chunk's canonical stored text.

    The Validation Agent uses this to check that a citation says what a draft
    claims. It must read the stored text, not the copy that passed through the
    drafting agent's context — otherwise it only verifies self-consistency.
    """
    chunk = Retriever(db).resolve(chunk_id)
    if chunk is None:
        return fail(f"no such chunk: {chunk_id}")
    return ok(
        {
            "chunk_id": chunk.id,
            "content": chunk.content,
            "page": chunk.page,
            "heading": chunk.heading,
            "document_id": chunk.document_id,
        }
    )


# -- MCP server ----------------------------------------------------------

server = Server("supportops-knowledge")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name=TOOL_SEARCH,
            description=(
                "Search the enterprise knowledge base. Returns text chunks with "
                "citations. Scope with product_area when known."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query."},
                    "product_area": {
                        "type": "string",
                        "description": "Scope retrieval. Omit if unknown.",
                    },
                    "top_k": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name=TOOL_GET_CHUNK,
            description="Fetch a chunk's canonical text by id, to verify a citation.",
            inputSchema={
                "type": "object",
                "properties": {"chunk_id": {"type": "string"}},
                "required": ["chunk_id"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    from backend.app.core.database import SessionLocal

    db = SessionLocal()
    try:
        if name == TOOL_SEARCH:
            result = search_knowledge(
                db,
                arguments["query"],
                product_area=arguments.get("product_area"),
                top_k=arguments.get("top_k", 5),
            )
        elif name == TOOL_GET_CHUNK:
            result = get_chunk(db, arguments["chunk_id"])
        else:
            result = fail(f"unknown tool: {name}")
    finally:
        db.close()

    return [types.TextContent(type="text", text=result.to_text())]


async def main() -> None:
    from mcp.server.stdio import stdio_server

    async with stdio_server() as (r, w):
        await server.run(r, w, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
