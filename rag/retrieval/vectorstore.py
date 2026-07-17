"""ChromaDB persistent client (Part 6).

PersistentClient, not a server: no container to run, and the reproducible setup
the assessment asks for stays at one `pip install`.
"""

from __future__ import annotations

from functools import lru_cache

import chromadb
from chromadb.config import Settings as ChromaSettings

from backend.app.core.config import settings


@lru_cache
def get_client() -> chromadb.ClientAPI:
    return chromadb.PersistentClient(
        path=settings.chroma_dir,
        settings=ChromaSettings(anonymized_telemetry=False, allow_reset=True),
    )


def get_collection():
    """The enterprise knowledge collection.

    Cosine distance, not Chroma's L2 default. The embeddings are normalised, so
    cosine is the metric the model was trained against; L2 would rank by a
    geometry the vectors do not encode.
    """
    return get_client().get_or_create_collection(
        name=settings.chroma_collection,
        metadata={"hnsw:space": "cosine"},
    )


def reset_collection() -> None:
    """Drop and recreate. Used by the ingestion script and the eval harness."""
    client = get_client()
    try:
        client.delete_collection(settings.chroma_collection)
    except Exception:  # noqa: BLE001 — absent collection is not an error here
        pass
    client.get_or_create_collection(
        name=settings.chroma_collection,
        metadata={"hnsw:space": "cosine"},
    )
