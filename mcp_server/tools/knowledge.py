"""Knowledge retrieval MCP tools.

Wraps the RAG retriever. The Research Agent's grounding guarantee is only
as good as what this returns — every citation downstream originates here.
"""

from __future__ import annotations

from backend.app.core.database import SessionLocal
from rag.retrieval.retriever import Retriever


def register_knowledge_tools(mcp):
    @mcp.tool()
    def search_knowledge(
        query: str,
        product_area: str | None = None,
        top_k: int = 5,
    ) -> dict:
        """Search the enterprise knowledge base. Returns text chunks with
        citations (chunk_id, source, page, score). Scope with product_area
        when known. Returning no results is a valid outcome — reformulate
        once before concluding a knowledge gap.
        """
        if not query or not query.strip():
            return {"ok": False, "error": "query is empty"}

        db = SessionLocal()
        try:
            try:
                hits = Retriever(db).search(query, top_k=top_k, product_area=product_area)
            except Exception as exc:  # noqa: BLE001
                # Chroma down. Report it rather than returning [] — an empty
                # result is indistinguishable from a genuine knowledge gap.
                return {"ok": False, "error": f"knowledge search unavailable: {exc}"}

            if not hits:
                return {
                    "ok": True,
                    "data": {
                        "results": [],
                        "note": (
                            "No results. If the query used the customer's wording, "
                            "retry with the product's own terminology before "
                            "concluding a knowledge gap."
                        ),
                    },
                }

            return {
                "ok": True,
                "data": {
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
                },
            }
        finally:
            db.close()

    @mcp.tool()
    def get_chunk(chunk_id: str) -> dict:
        """Fetch a chunk's canonical stored text by id. Use this to verify
        that a citation actually says what a draft claims it says.
        """
        db = SessionLocal()
        try:
            chunk = Retriever(db).resolve(chunk_id)
            if chunk is None:
                return {"ok": False, "error": f"no such chunk: {chunk_id}"}
            return {
                "ok": True,
                "data": {
                    "chunk_id": chunk.id,
                    "content": chunk.content,
                    "page": chunk.page,
                    "heading": chunk.heading,
                    "document_id": chunk.document_id,
                },
            }
        finally:
            db.close()