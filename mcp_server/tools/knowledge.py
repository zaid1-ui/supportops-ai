"""Knowledge retrieval MCP tools.

Core logic is db-taking plain functions — callable directly by the
evaluation harness. register_knowledge_tools wraps each for the standalone
MCP server.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from backend.app.core.database import SessionLocal
from mcp_server.core import ToolResult, fail, ok
from rag.retrieval.retriever import Retriever


def search_knowledge(
    db: Session,
    query: str,
    product_area: str | None = None,
    top_k: int = 5,
) -> ToolResult:
    if not query or not query.strip():
        return fail("query is empty")

    try:
        hits = Retriever(db).search(query, top_k=top_k, product_area=product_area)
    except Exception as exc:  # noqa: BLE001
        return fail(f"knowledge search unavailable: {exc}")

    if not hits:
        return ok(
            {
                "results": [],
                "note": (
                    "No results. If the query used the customer's wording, "
                    "retry with the product's own terminology before "
                    "concluding a knowledge gap."
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


def register_knowledge_tools(mcp):
    @mcp.tool(name="search_knowledge")
    def search_knowledge_tool(
        query: str,
        product_area: str | None = None,
        top_k: int = 5,
    ) -> dict:
        """Search the enterprise knowledge base. Returns cited text chunks."""
        db = SessionLocal()
        try:
            return search_knowledge(db, query, product_area, top_k).to_dict()
        finally:
            db.close()

    @mcp.tool(name="get_chunk")
    def get_chunk_tool(chunk_id: str) -> dict:
        """Fetch a chunk's canonical stored text by id, to verify a citation."""
        db = SessionLocal()
        try:
            return get_chunk(db, chunk_id).to_dict()
        finally:
            db.close()