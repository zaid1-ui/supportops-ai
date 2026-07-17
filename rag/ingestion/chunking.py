"""Chunking strategy (Part 6). Justified in docs/RAG.md.

RecursiveCharacterTextSplitter, 800 tokens / 120 overlap, splitting on
paragraph boundaries before sentence boundaries before words.
"""

from __future__ import annotations

import re
from functools import lru_cache

import tiktoken
from langchain_core.documents import Document as LCDocument
from langchain_text_splitters import RecursiveCharacterTextSplitter

from backend.app.core.config import settings

# Ordered most- to least-preferred. The splitter only falls to the next
# separator when a chunk still exceeds the limit, so a paragraph survives
# intact whenever it fits.
SEPARATORS = ["\n\n", "\n", ". ", "? ", "! ", "; ", ", ", " ", ""]

# Markdown ATX headings and common runbook headers.
_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$", re.MULTILINE)


@lru_cache
def _encoder() -> tiktoken.Encoding:
    """Lazy, cached.

    tiktoken downloads the BPE table on first use and caches it on disk. Built
    at module scope this would put a network call in the import path, so any
    importer — including the test suite and `--help` — would fail without
    egress. Deferring it means only code that actually counts tokens pays.
    """
    return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(_encoder().encode(text))


def _nearest_heading(text: str, chunk_start: int, chunk_end: int) -> str | None:
    """The heading governing a chunk.

    Searches up to the chunk's *end*, not its start. A chunk usually opens with
    the heading it belongs under — the splitter breaks on "\\n\\n", so headings
    land at chunk boundaries — and searching only up to `chunk_start` therefore
    finds nothing for exactly the chunks whose heading is most obvious.

    Imperfect where a chunk ends just after a new heading: the tail gets
    labelled with a heading that governs almost none of it. Rare, and the
    citation still carries page and source, so a reviewer can still locate it.
    """
    last = None
    for m in _HEADING.finditer(text[:chunk_end]):
        last = m.group(2).strip()
    return last


def chunk_documents(
    docs: list[LCDocument],
    *,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> list[LCDocument]:
    """Split loaded documents into embedding-sized chunks.

    Length is measured in tokens, not characters. The embedding model has a
    token limit, and character-based splitting silently over- or under-fills
    depending on the text — code and tables tokenise very differently to prose.
    """
    size = chunk_size or settings.chunk_size
    overlap = chunk_overlap or settings.chunk_overlap

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=size,
        chunk_overlap=overlap,
        length_function=count_tokens,
        separators=SEPARATORS,
        keep_separator=True,
    )

    out: list[LCDocument] = []
    for doc in docs:
        pieces = splitter.split_text(doc.page_content)
        cursor = 0
        for piece in pieces:
            found = doc.page_content.find(piece, cursor)
            position = found if found != -1 else cursor
            cursor = position + len(piece)

            meta = dict(doc.metadata)
            meta["heading"] = _nearest_heading(doc.page_content, position, cursor)
            meta["token_count"] = count_tokens(piece)
            out.append(LCDocument(page_content=piece, metadata=meta))

    return out
