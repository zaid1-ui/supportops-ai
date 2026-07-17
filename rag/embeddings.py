"""Embedding model (Part 6). Selection justified in docs/RAG.md.

Two providers, chosen by EMBEDDING_PROVIDER:

  local  — fastembed running BAAI/bge-small-en-v1.5 on CPU via ONNX. No key, no
           network at query time, and no data leaves the machine. ONNX rather
           than sentence-transformers, so this does not drag in ~2GB of torch.
  openai — text-embedding-3-small.

This is a separate choice from the LLM provider on purpose: xAI/Grok exposes no
public embeddings endpoint, so a Grok deployment still needs an embedding source
and `local` is the one that needs no second account.

Changing provider changes the vector space. Vectors from different models are
not comparable, so a switch requires re-indexing:  python -m scripts.reindex
"""

from __future__ import annotations

from functools import lru_cache

from langchain_core.embeddings import Embeddings

from backend.app.core.config import settings

# bge-small-en-v1.5 -> 384, text-embedding-3-small -> 1536.
_DIMS = {"BAAI/bge-small-en-v1.5": 384, "text-embedding-3-small": 1536,
         "text-embedding-3-large": 3072}


@lru_cache
def get_embeddings() -> Embeddings:
    """Cached: the client is stateless, and fastembed loads a model on init."""
    provider = settings.embedding_provider.lower()

    if provider == "local":
        from langchain_community.embeddings import FastEmbedEmbeddings

        return FastEmbedEmbeddings(model_name=settings.embedding_model)

    if provider == "openai":
        from langchain_openai import OpenAIEmbeddings

        return OpenAIEmbeddings(model=settings.embedding_model, api_key=settings.openai_api_key)

    raise ValueError(
        f"Unknown EMBEDDING_PROVIDER {provider!r}. Use 'local' or 'openai'."
    )


def embedding_dim() -> int:
    return _DIMS.get(settings.embedding_model, 384)
