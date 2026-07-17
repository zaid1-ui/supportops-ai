"""Knowledge base models.

Chunks are stored here as well as in ChromaDB, on purpose. Chroma holds the
vectors and answers "what is similar to this query"; this table answers "what
exactly did chunk #abc123 say, and where did it come from". Citations resolve
against this, so a citation stays meaningful even if the collection is rebuilt
with different embeddings — which is what makes the Validation Agent's check on
whether a citation actually says what it is claimed to say possible at all.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.database import Base
from backend.app.models.orchestration import utcnow


class DocType(str, enum.Enum):
    PDF = "pdf"
    DOCX = "docx"
    TXT = "txt"


class IngestStatus(str, enum.Enum):
    PENDING = "pending"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    INDEXED = "indexed"
    FAILED = "failed"


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    filename: Mapped[str] = mapped_column(String(500))
    path: Mapped[str] = mapped_column(String(1000))
    doc_type: Mapped[DocType] = mapped_column(Enum(DocType))

    # Retrieval scoping metadata. product_area matters most: the Research Agent
    # filters on it, so a wrong value silently shrinks the searchable corpus.
    product_area: Mapped[str] = mapped_column(String(100), default="unknown", index=True)
    version: Mapped[str | None] = mapped_column(String(50), nullable=True)

    status: Mapped[IngestStatus] = mapped_column(Enum(IngestStatus), default=IngestStatus.PENDING)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    chunks: Mapped[list[Chunk]] = relationship(back_populates="document", cascade="all, delete-orphan")


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_id: Mapped[str] = mapped_column(String(36), ForeignKey("documents.id"), index=True)

    content: Mapped[str] = mapped_column(Text)
    ordinal: Mapped[int] = mapped_column(Integer)  # position within the document

    # Citation targets. Without page and heading a citation says "somewhere in
    # this 200-page PDF", which no reviewer can verify.
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    heading: Mapped[str | None] = mapped_column(String(500), nullable=True)

    token_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    document: Mapped[Document] = relationship(back_populates="chunks")
