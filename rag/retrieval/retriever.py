"""Vector search and citation support (Part 6).

Returns chunks paired with resolved Citation objects (agents/schemas.py). The
Research Agent cannot attach a citation to a claim unless retrieval hands it one
already resolved, so this module is where the platform's grounding guarantee is
actually made good.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from agents.schemas import Citation
from backend.app.core.config import settings
from backend.app.core.logging import get_logger
from backend.app.models import Chunk
from rag.embeddings import get_embeddings
from rag.retrieval.vectorstore import get_collection

logger = get_logger(__name__)


@dataclass
class RetrievedChunk:
    """A search hit: the text, plus a citation that already resolves."""

    content: str
    citation: Citation
    heading: str | None

    def render(self) -> str:
        """Format for an agent prompt, with provenance inline.

        The citation travels attached to the text rather than in a separate
        list. Given text in one place and sources in another, models cite the
        wrong source — the association has to survive into the context window.
        """
        loc = f"p{self.citation.page}" if self.citation.page else "n/a"
        head = f" — {self.heading}" if self.heading else ""
        return (
            f"[#{self.citation.chunk_id} | {self.citation.source} {loc}{head} | "
            f"score {self.citation.score:.3f}]\n{self.content}"
        )


class Retriever:
    """Dense retrieval over the enterprise knowledge collection."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.collection = get_collection()
        self.embedder = get_embeddings()

    def search(
        self,
        query: str,
        *,
        top_k: int | None = None,
        product_area: str | None = None,
        doc_type: str | None = None,
        min_score: float = 0.0,
    ) -> list[RetrievedChunk]:
        """Search, filtered by metadata, returning resolved citations.

        `product_area` filtering is applied by Chroma *before* the ANN search,
        so top_k is drawn from the scoped subset rather than from the whole
        corpus and then filtered down — the latter returns fewer than top_k
        results and silently starves the agent of evidence.
        """
        k = top_k or settings.retrieval_top_k

        where = self._build_filter(product_area, doc_type)

        result = self.collection.query(
            query_embeddings=[self.embedder.embed_query(query)],
            n_results=k,
            where=where or None,
            include=["documents", "metadatas", "distances"],
        )

        ids = result.get("ids", [[]])[0]
        if not ids:
            logger.info("no hits: query=%r filter=%s", query[:60], where)
            return []

        docs = result["documents"][0]
        metas = result["metadatas"][0]
        distances = result["distances"][0]

        hits: list[RetrievedChunk] = []
        for chunk_id, content, meta, distance in zip(ids, docs, metas, distances, strict=True):
            # Chroma returns cosine *distance*; agents reason about similarity.
            score = 1.0 - float(distance)
            if score < min_score:
                continue

            page = meta.get("page")
            hits.append(
                RetrievedChunk(
                    content=content,
                    heading=meta.get("heading") or None,
                    citation=Citation(
                        doc_id=meta["doc_id"],
                        chunk_id=chunk_id,
                        source=meta["source"],
                        page=page if isinstance(page, int) and page > 0 else None,
                        score=round(score, 4),
                    ),
                )
            )
        return hits

    def resolve(self, chunk_id: str) -> Chunk | None:
        """Fetch a chunk's canonical text by id.

        The Validation Agent uses this to check whether a citation actually says
        what the draft claims it says. That check has to read the stored text,
        not the copy that passed through the drafting agent's context.
        """
        return self.db.get(Chunk, chunk_id)

    @staticmethod
    def _build_filter(product_area: str | None, doc_type: str | None) -> dict | None:
        clauses = []
        # "unknown" means Triage could not classify the ticket. Filtering on it
        # would search only the unclassified corner of the corpus, which is the
        # opposite of what an unclassified ticket needs.
        if product_area and product_area != "unknown":
            clauses.append({"product_area": product_area})
        if doc_type:
            clauses.append({"doc_type": doc_type})

        if not clauses:
            return None
        if len(clauses) == 1:
            return clauses[0]
        return {"$and": clauses}


def render_context(hits: list[RetrievedChunk]) -> str:
    """Render hits for a prompt.

    Says so explicitly when empty. An agent handed a blank context block infers
    a formatting bug and starts improvising; told plainly that retrieval found
    nothing, it reports a knowledge gap, which is the correct behaviour.
    """
    if not hits:
        return "(retrieval returned no results for this query)"
    return "\n\n".join(h.render() for h in hits)
