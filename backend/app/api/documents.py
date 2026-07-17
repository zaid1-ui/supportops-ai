"""Document routes (Part 10) — upload, list, search, delete."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status

from backend.app.api.deps import CurrentUser, DbSession
from backend.app.core.config import settings
from backend.app.core.logging import get_logger
from backend.app.models import Document
from backend.app.schemas.api import DocumentResponse, SearchHit, SearchResponse
from rag.ingestion.loaders import UnsupportedFileType, detect_type
from rag.ingestion.pipeline import delete_document, ingest_file
from rag.retrieval.retriever import Retriever

router = APIRouter(prefix="/documents", tags=["documents"])
logger = get_logger(__name__)

MAX_UPLOAD_BYTES = 25 * 1024 * 1024


@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
def upload_document(
    db: DbSession,
    user: CurrentUser,
    file: UploadFile = File(...),
    product_area: str = Query("unknown", description="Retrieval scope for this document."),
    version: str | None = Query(None),
) -> DocumentResponse:
    """Ingest a document: validate, store, chunk, embed, index.

    Synchronous. A large PDF will block the request — acceptable at this scale
    and honest about it; the fix is the ingestion worker pool described in
    ARCHITECTURE.md §8.2, not a background task that lies about being done.
    """
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No filename")

    # Validate type before writing anything to disk.
    try:
        detect_type(file.filename)
    except UnsupportedFileType as exc:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc)) from exc

    # Never trust a client-supplied filename as a path. `Path(...).name` strips
    # any directory component, so "../../etc/passwd" cannot escape upload_dir.
    safe_name = Path(file.filename).name
    dest = Path(settings.upload_dir) / f"{uuid.uuid4().hex[:8]}_{safe_name}"
    dest.parent.mkdir(parents=True, exist_ok=True)

    with dest.open("wb") as fh:
        shutil.copyfileobj(file.file, fh, length=1024 * 1024)

    if dest.stat().st_size > MAX_UPLOAD_BYTES:
        dest.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {MAX_UPLOAD_BYTES // 1024 // 1024}MB",
        )

    try:
        doc = ingest_file(db, dest, product_area=product_area, version=version)
    except Exception as exc:
        logger.exception("ingestion failed: %s", safe_name)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Ingestion failed: {exc}"
        ) from exc

    return _to_response(doc)


@router.get("", response_model=list[DocumentResponse])
def list_documents(db: DbSession, user: CurrentUser) -> list[DocumentResponse]:
    docs = db.query(Document).order_by(Document.created_at.desc()).all()
    return [_to_response(d) for d in docs]


@router.get("/search", response_model=SearchResponse)
def search_documents(
    db: DbSession,
    user: CurrentUser,
    q: str = Query(min_length=1, description="Search query."),
    product_area: str | None = Query(None),
    top_k: int = Query(5, ge=1, le=20),
) -> SearchResponse:
    try:
        hits = Retriever(db).search(q, top_k=top_k, product_area=product_area)
    except Exception as exc:
        logger.exception("search failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Knowledge search unavailable: {exc}",
        ) from exc

    return SearchResponse(
        query=q,
        product_area=product_area,
        total=len(hits),
        hits=[
            SearchHit(
                chunk_id=h.citation.chunk_id,
                doc_id=h.citation.doc_id,
                source=h.citation.source,
                page=h.citation.page,
                heading=h.heading,
                score=h.citation.score,
                content=h.content,
            )
            for h in hits
        ],
    )


# response_model=None is required: FastAPI otherwise infers one from the return
# annotation and rejects it, since 204 must not carry a body.
@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def remove_document(doc_id: str, db: DbSession, user: CurrentUser) -> None:
    try:
        delete_document(db, doc_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


def _to_response(doc: Document) -> DocumentResponse:
    return DocumentResponse(
        id=doc.id,
        filename=doc.filename,
        doc_type=doc.doc_type.value,
        product_area=doc.product_area,
        version=doc.version,
        status=doc.status.value,
        chunk_count=doc.chunk_count,
        error=doc.error,
        created_at=doc.created_at,
    )
