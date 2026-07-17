"""Ingestion pipeline (Part 6): load -> chunk -> embed -> index.

Chunks land in two places: ChromaDB (vectors, for similarity) and the `chunks`
table (text and provenance, for citation resolution). Both writes must succeed
or the document is marked FAILED — a half-indexed document is worse than an
absent one, because retrieval returns hits whose citations cannot be resolved
and the Validation Agent then fails drafts for reasons the author cannot fix.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from backend.app.core.logging import get_logger
from backend.app.models import Chunk, Document, IngestStatus
from rag.embeddings import get_embeddings
from rag.ingestion.chunking import chunk_documents
from rag.ingestion.loaders import detect_type, load
from rag.retrieval.vectorstore import get_collection

logger = get_logger(__name__)

EMBED_BATCH_SIZE = 100


class IngestionError(Exception):
    pass


def ingest_file(
    db: Session,
    path: str | Path,
    *,
    product_area: str = "unknown",
    version: str | None = None,
) -> Document:
    """Ingest one file end to end. Returns the indexed Document."""
    path = Path(path)
    doc = Document(
        id=str(uuid.uuid4()),
        filename=path.name,
        path=str(path),
        doc_type=detect_type(path),
        product_area=product_area,
        version=version,
        status=IngestStatus.PENDING,
    )
    db.add(doc)
    db.commit()

    try:
        # -- load + chunk ------------------------------------------------
        doc.status = IngestStatus.CHUNKING
        db.commit()

        loaded = load(path)
        if not loaded or not any(d.page_content.strip() for d in loaded):
            raise IngestionError(
                f"{path.name} produced no extractable text. "
                "If it is a scanned PDF it needs OCR before ingestion."
            )

        pieces = chunk_documents(loaded)
        if not pieces:
            raise IngestionError(f"{path.name} produced no chunks")

        # -- persist chunks (citation targets) ---------------------------
        rows: list[Chunk] = []
        for i, piece in enumerate(pieces):
            rows.append(
                Chunk(
                    id=str(uuid.uuid4()),
                    document_id=doc.id,
                    content=piece.page_content,
                    ordinal=i,
                    page=piece.metadata.get("page"),
                    heading=piece.metadata.get("heading"),
                    token_count=piece.metadata.get("token_count", 0),
                )
            )
        db.add_all(rows)
        db.commit()

        # -- embed + index -----------------------------------------------
        doc.status = IngestStatus.EMBEDDING
        db.commit()

        embedder = get_embeddings()
        collection = get_collection()

        for start in range(0, len(rows), EMBED_BATCH_SIZE):
            batch = rows[start : start + EMBED_BATCH_SIZE]
            vectors = embedder.embed_documents([c.content for c in batch])
            collection.add(
                ids=[c.id for c in batch],
                embeddings=vectors,
                documents=[c.content for c in batch],
                # Metadata drives query-time filtering. Chroma rejects None, so
                # absent values become "" rather than being omitted.
                metadatas=[
                    {
                        "doc_id": doc.id,
                        "chunk_id": c.id,
                        "source": doc.filename,
                        "product_area": doc.product_area,
                        "doc_type": doc.doc_type.value,
                        "page": c.page if c.page is not None else -1,
                        "heading": c.heading or "",
                        "version": doc.version or "",
                    }
                    for c in batch
                ],
            )

        doc.chunk_count = len(rows)
        doc.status = IngestStatus.INDEXED
        db.commit()
        logger.info("indexed %s: %d chunks", doc.filename, doc.chunk_count)
        return doc

    except Exception as exc:
        db.rollback()
        doc.status = IngestStatus.FAILED
        doc.error = str(exc)
        db.commit()
        logger.exception("ingestion failed for %s", path.name)
        raise


def delete_document(db: Session, doc_id: str) -> None:
    """Remove a document from both stores.

    Chroma first. If the DB delete fails afterwards the orphan is a chunk row
    with no vector — invisible to retrieval, therefore harmless. The reverse
    order leaves a vector with no resolvable citation, which retrieval *will*
    return and no reviewer can verify.
    """
    doc = db.get(Document, doc_id)
    if doc is None:
        raise LookupError(f"No such document: {doc_id}")

    chunk_ids = [c.id for c in doc.chunks]
    if chunk_ids:
        get_collection().delete(ids=chunk_ids)

    db.delete(doc)  # cascade drops chunks
    db.commit()
