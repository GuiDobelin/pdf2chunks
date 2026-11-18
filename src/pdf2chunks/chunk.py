"""Split page text into overlapping, size-bounded chunks that remember their pages."""

import hashlib
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from pdf2chunks.types import Chunk, Page

DEFAULT_MAX_CHARS = 1200
DEFAULT_OVERLAP = 150

_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")
_WHITESPACE = re.compile(r"\s+")
_HEADING_END = re.compile(r"[.!?,;:…。！？]$")
_SENTENCE_BREAK = re.compile(r"(?<=[.!?…。！？])[\"'”’)\]]*\s+")


@dataclass(frozen=True)
class _Unit:
    text: str
    page: int
    sep: str  # what joins this unit to the one before it


def _split_long(text: str, max_chars: int) -> list[str]:
    """Split text longer than ``max_chars`` at sentence ends, then words, then characters."""
    if len(text) <= max_chars:
        return [text]
    pieces: list[str] = []
    for sentence in _sentences(text):
        if len(sentence) <= max_chars:
            pieces.append(sentence)
            continue
        current = ""
        for word in sentence.split(" "):
            while len(word) > max_chars:  # e.g. a URL or a run of characters without spaces
                if current:
                    pieces.append(current)
                    current = ""
                pieces.append(word[:max_chars])
                word = word[max_chars:]
            if not current:
                current = word
            elif len(current) + 1 + len(word) <= max_chars:
                current += " " + word
            else:
                pieces.append(current)
                current = word
        if current:
            pieces.append(current)
    return pieces


def _sentences(text: str) -> list[str]:
    out = []
    start = 0
    for match in _SENTENCE_BREAK.finditer(text):
        out.append(text[start : match.end()].rstrip())
        start = match.end()
    out.append(text[start:])
    return [s for s in out if s]


def _units(pages: Iterable[Page], max_chars: int) -> list[_Unit]:
    units = []
    for page in pages:
        for paragraph in _PARAGRAPH_BREAK.split(page.text):
            paragraph = _WHITESPACE.sub(" ", paragraph).strip()
            if not paragraph:
                continue
            for i, piece in enumerate(_split_long(paragraph, max_chars)):
                units.append(_Unit(piece, page.number, "\n\n" if i == 0 else " "))
    return units


def _is_heading(unit: _Unit) -> bool:
    return unit.sep == "\n\n" and len(unit.text) <= 100 and not _HEADING_END.search(unit.text)


def _length(units: list[_Unit]) -> int:
    return sum(len(u.text) for u in units) + sum(len(u.sep) for u in units[1:])


def chunk_pages(
    pages: Iterable[Page],
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap: int = DEFAULT_OVERLAP,
    source: str = "",
    metadata: Mapping[str, Any] | None = None,
) -> list[Chunk]:
    """Pack paragraphs into chunks of at most ``max_chars`` characters.

    Paragraphs are kept whole when they fit; longer ones are split at sentence ends, then at
    spaces. Each chunk starts with up to ``overlap`` characters of whole sentences from the end
    of the previous chunk, so a fact split across a boundary is still retrievable. Chunk ids
    are stable: the same input always yields the same ids.
    """
    if max_chars < 1:
        raise ValueError("max_chars must be at least 1")
    if not 0 <= overlap < max_chars:
        raise ValueError("overlap must be at least 0 and smaller than max_chars")

    groups: list[list[_Unit]] = []
    current: list[_Unit] = []
    size = 0  # == _length(current), kept up to date instead of recomputed per unit
    for unit in _units(pages, max_chars):
        if current and size + len(unit.sep) + len(unit.text) > max_chars:
            heading = current[-1]
            if (
                len(current) > 1
                and _is_heading(heading)
                and len(heading.text) + len(unit.sep) + len(unit.text) <= max_chars
            ):
                # never end a chunk on a heading: move it to the chunk with its section
                groups.append(current[:-1])
                current = [heading]
            else:
                groups.append(current)
                current = _tail(current, overlap)
            size = _length(current)
            while current and size + len(unit.sep) + len(unit.text) > max_chars:
                dropped = current.pop(0)
                size -= len(dropped.text) + (len(current[0].sep) if current else 0)
        size += len(unit.text) + (len(unit.sep) if current else 0)
        current.append(unit)
    if current:
        groups.append(current)

    base = dict(metadata or {})
    chunks = []
    for index, group in enumerate(groups):
        text = group[0].text + "".join(u.sep + u.text for u in group[1:])
        digest = hashlib.sha256(f"{source}\0{index}\0{text}".encode()).hexdigest()[:16]
        chunks.append(
            Chunk(
                id=digest,
                index=index,
                text=text,
                source=source,
                page_start=min(u.page for u in group),
                page_end=max(u.page for u in group),
                metadata=dict(base),  # one dict per chunk: editing one never leaks
            )
        )
    return chunks


def _tail(units: list[_Unit], overlap: int) -> list[_Unit]:
    """Trailing whole sentences of ``units`` that fit in ``overlap``, never the whole group.

    Units are paragraphs or sentences; when the last fitting unit is a long paragraph, its
    trailing sentences are carried over on their own.
    """
    tail: list[_Unit] = []
    for unit in reversed(units):
        if _length([unit, *tail]) <= overlap:
            tail.insert(0, unit)
            continue
        sentences = _sentences(unit.text)
        kept: list[str] = []
        for sentence in reversed(sentences[1:]):
            if _length([_Unit(" ".join([sentence, *kept]), unit.page, ""), *tail]) > overlap:
                break
            kept.insert(0, sentence)
        if kept:
            tail.insert(0, _Unit(" ".join(kept), unit.page, unit.sep))
        break
    if len(tail) == len(units) and tail == units:
        tail.pop(0)
    return tail
