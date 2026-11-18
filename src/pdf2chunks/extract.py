"""Read text and metadata out of a PDF with pypdf."""

import io
import os
from collections.abc import Iterable
from pathlib import Path
from typing import BinaryIO

from pypdf import PasswordType, PdfReader

from pdf2chunks.types import Document, Page

PdfSource = str | os.PathLike[str] | bytes | BinaryIO

_METADATA_FIELDS = {
    "title": "title",
    "author": "author",
    "subject": "subject",
    "keywords": "keywords",
    "creator": "creator",
    "producer": "producer",
}


class PdfError(Exception):
    """The PDF could not be opened: it is damaged, not a PDF, or encrypted."""


def read_pdf(
    src: PdfSource,
    *,
    password: str | None = None,
    pages: Iterable[int] | None = None,
    source: str | None = None,
) -> Document:
    """Extract the text of every page (or of the 1-based ``pages`` given) and the metadata.

    ``source`` names the document in the result; it defaults to the path, or ``""`` for bytes
    and streams. A page whose text cannot be extracted is kept with empty text and reported in
    ``Document.warnings`` instead of failing the whole document.
    """
    if source is None:
        source = os.fspath(src) if isinstance(src, (str, os.PathLike)) else ""
    if isinstance(src, (str, os.PathLike)):
        data: BinaryIO = io.BytesIO(Path(src).read_bytes())
    elif isinstance(src, bytes):
        data = io.BytesIO(src)
    else:
        data = src

    try:
        reader = PdfReader(data, strict=False)
        if reader.is_encrypted and reader.decrypt(password or "") == PasswordType.NOT_DECRYPTED:
            raise PdfError(
                "the PDF is encrypted and the password is wrong"
                if password
                else "the PDF is encrypted; a password is required"
            )
        total = len(reader.pages)
    except PdfError:
        raise
    except Exception as exc:  # pypdf raises many exception types on malformed input
        raise PdfError(f"cannot read PDF: {exc}") from exc

    numbers = list(range(1, total + 1)) if pages is None else sorted(set(pages))
    for number in numbers:
        if not 1 <= number <= total:
            raise ValueError(f"page {number} does not exist (the PDF has {total} pages)")

    extracted = []
    warnings = []
    for number in numbers:
        try:
            text = reader.pages[number - 1].extract_text() or ""
        except Exception as exc:
            warnings.append(f"page {number}: text extraction failed: {exc}")
            text = ""
        extracted.append(Page(number=number, text=text))

    return Document(
        source=source,
        pages=tuple(extracted),
        page_count=total,
        metadata=_metadata(reader),
        warnings=tuple(warnings),
    )


def _metadata(reader: PdfReader) -> dict[str, str]:
    try:
        info = reader.metadata
    except Exception:
        return {}
    if info is None:
        return {}
    out = {}
    for key, attr in _METADATA_FIELDS.items():
        try:
            value = getattr(info, attr)
        except Exception:
            continue
        if isinstance(value, str) and value.strip():
            out[key] = value.strip()
    try:
        created = info.creation_date
    except Exception:
        created = None
    if created is not None:
        out["created"] = created.isoformat()
    return out
