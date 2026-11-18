"""Turn PDFs into JSONL chunks with page numbers and metadata, ready for RAG ingestion."""

from collections.abc import Iterable

from pdf2chunks.chunk import DEFAULT_MAX_CHARS, DEFAULT_OVERLAP, chunk_pages
from pdf2chunks.clean import clean_pages
from pdf2chunks.extract import PdfError, PdfSource, read_pdf
from pdf2chunks.types import Chunk, Document, Page

__version__ = "0.1.0"

__all__ = [
    "Chunk",
    "Document",
    "Page",
    "PdfError",
    "__version__",
    "chunk_document",
    "chunk_pages",
    "clean_pages",
    "pdf_to_chunks",
    "read_pdf",
]


def chunk_document(
    document: Document,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap: int = DEFAULT_OVERLAP,
    clean: bool = True,
) -> list[Chunk]:
    """Clean a document's pages (unless ``clean=False``) and chunk them.

    Every chunk carries the document metadata plus ``page_count``.
    """
    pages = clean_pages(document.pages) if clean else list(document.pages)
    metadata = {**document.metadata, "page_count": document.page_count}
    return chunk_pages(
        pages, max_chars=max_chars, overlap=overlap, source=document.source, metadata=metadata
    )


def pdf_to_chunks(
    src: PdfSource,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap: int = DEFAULT_OVERLAP,
    password: str | None = None,
    pages: Iterable[int] | None = None,
    clean: bool = True,
    source: str | None = None,
) -> list[Chunk]:
    """Read a PDF and return its chunks in one call."""
    document = read_pdf(src, password=password, pages=pages, source=source)
    return chunk_document(document, max_chars=max_chars, overlap=overlap, clean=clean)
