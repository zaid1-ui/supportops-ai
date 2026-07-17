"""Embedding model (Part 6). Selection justified in docs/RAG.md."""

from __future__ import annotations

from functools import lru_cache

from langchain_openai import OpenAIEmbeddings

from backend.app.core.config import settings

# text-embedding-3-small. 1536 dimensions.
EMBEDDING_DIM = 1536


@lru_cache
def get_embeddings() -> OpenAIEmbeddings:
    """Cached — the client is stateless and rebuilding it per call is waste."""
    return OpenAIEmbeddings(
        model=settings.embedding_model,
        api_key=settings.openai_api_key,
    )
