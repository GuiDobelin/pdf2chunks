from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Page:
    """The text of one PDF page; ``number`` is 1-based, as printed in PDF viewers."""

    number: int
    text: str


@dataclass(frozen=True)
class Document:
    """A PDF's extracted pages, document metadata and any per-page extraction problems."""

    source: str
    pages: tuple[Page, ...]
    page_count: int
    metadata: Mapping[str, str] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class Chunk:
    """A piece of a document small enough to embed, with the pages it came from."""

    id: str
    index: int
    text: str
    source: str
    page_start: int
    page_end: int
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """A JSON-serialisable dict, as written to each JSONL line."""
        return {
            "id": self.id,
            "source": self.source,
            "index": self.index,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "chars": len(self.text),
            "text": self.text,
            "metadata": dict(self.metadata),
        }
