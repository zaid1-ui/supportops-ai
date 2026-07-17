"""Document loaders for PDF, DOCX, TXT (Part 6).

Each loader returns LangChain Documents carrying a `page` in metadata where the
format has one. Page numbers are load-bearing: a citation without one points at
a whole document, which a human reviewer cannot check in the time they have.
"""

from __future__ import annotations

from pathlib import Path

from langchain_community.document_loaders import (
    Docx2txtLoader,
    PyPDFLoader,
    TextLoader,
)
from langchain_core.documents import Document as LCDocument

from backend.app.models import DocType

SUPPORTED_EXTENSIONS = {".pdf": DocType.PDF, ".docx": DocType.DOCX, ".txt": DocType.TXT}


class UnsupportedFileType(Exception):
    pass


def detect_type(path: str | Path) -> DocType:
    suffix = Path(path).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise UnsupportedFileType(
            f"{suffix or '(no extension)'} is not supported. "
            f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )
    return SUPPORTED_EXTENSIONS[suffix]


def load(path: str | Path) -> list[LCDocument]:
    """Load a file into LangChain Documents.

    PDF yields one Document per page (PyPDFLoader sets `page`, zero-based —
    normalised to one-based here so citations match what a human sees in a
    viewer). DOCX and TXT have no pagination, so page stays None rather than
    being faked.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)

    doc_type = detect_type(path)

    if doc_type is DocType.PDF:
        docs = PyPDFLoader(str(path)).load()
        for d in docs:
            zero_based = d.metadata.get("page")
            d.metadata["page"] = (zero_based + 1) if isinstance(zero_based, int) else None
        return docs

    if doc_type is DocType.DOCX:
        docs = Docx2txtLoader(str(path)).load()
    else:
        docs = TextLoader(str(path), encoding="utf-8").load()

    for d in docs:
        d.metadata["page"] = None
    return docs
