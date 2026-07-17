"""Re-embed every indexed document into a fresh Chroma collection.

Required after changing EMBEDDING_PROVIDER or EMBEDDING_MODEL: vectors from
different models occupy different spaces and are not comparable, so the old
collection would return confident nonsense rather than fail.

This is a re-index, not a re-ingest — chunk text and provenance already live in
the `chunks` table, so nothing is re-parsed and citations keep resolving.

Usage:  python -m scripts.reindex
"""

from __future__ import annotations

import sys

from backend.app.core.config import settings
from backend.app.core.database import SessionLocal, init_db
from backend.app.models import Document, IngestStatus
from rag.embeddings import get_embeddings
from rag.retrieval.vectorstore import get_collection, reset_collection

BATCH = 100


def main() -> int:
    init_db()
    db = SessionLocal()
    try:
        docs = db.query(Document).filter(Document.status == IngestStatus.INDEXED).all()
        if not docs:
            print("Nothing indexed. Upload documents first.")
            return 0

        print(f"Re-indexing {len(docs)} document(s) with "
              f"{settings.embedding_provider}:{settings.embedding_model}")
        reset_collection()
        embedder = get_embeddings()
        collection = get_collection()

        total = 0
        for doc in docs:
            chunks = sorted(doc.chunks, key=lambda c: c.ordinal)
            for start in range(0, len(chunks), BATCH):
                batch = chunks[start : start + BATCH]
                vectors = embedder.embed_documents([c.content for c in batch])
                collection.add(
                    ids=[c.id for c in batch],
                    embeddings=vectors,
                    documents=[c.content for c in batch],
                    metadatas=[
                        {
                            "doc_id": doc.id, "chunk_id": c.id, "source": doc.filename,
                            "product_area": doc.product_area, "doc_type": doc.doc_type.value,
                            "page": c.page if c.page is not None else -1,
                            "heading": c.heading or "", "version": doc.version or "",
                        }
                        for c in batch
                    ],
                )
                total += len(batch)
            print(f"  {doc.filename}: {len(chunks)} chunks")

        print(f"Done. {total} chunks re-indexed.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
