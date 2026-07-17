"""RAG pipeline (Part 6). Documented in docs/RAG.md."""

from rag.embeddings import EMBEDDING_DIM, get_embeddings
from rag.ingestion.chunking import chunk_documents, count_tokens
from rag.ingestion.loaders import SUPPORTED_EXTENSIONS, load
from rag.ingestion.pipeline import delete_document, ingest_file
from rag.retrieval.retriever import RetrievedChunk, Retriever, render_context
from rag.retrieval.vectorstore import get_collection, reset_collection

__all__ = [
    "ingest_file", "delete_document", "load", "SUPPORTED_EXTENSIONS",
    "chunk_documents", "count_tokens", "get_embeddings", "EMBEDDING_DIM",
    "Retriever", "RetrievedChunk", "render_context",
    "get_collection", "reset_collection",
]
