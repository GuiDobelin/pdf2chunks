"""Turn raw PDF text into clean paragraphs.

Text extracted from PDFs comes as hard-wrapped lines: words are hyphenated across line breaks,
ligatures appear as single code points, and every page repeats its running header, footer and
page number. The functions here undo that, so chunks contain prose and nothing else.
"""

import math
import re
import statistics
from collections import Counter
from collections.abc import Iterable, Sequence

from pdf2chunks.types import Page

_TRANSLATE = str.maketrans(
    {
        "ﬀ": "ff",
        "ﬁ": "fi",
        "ﬂ": "fl",
        "ﬃ": "ffi",
        "ﬄ": "ffl",
        "ﬅ": "st",
        "ﬆ": "st",
        " ": " ",
        " ": " ",
        " ": " ",
        " ": " ",
        " ": " ",
        "\t": " ",
        "\f": "\n",
        "­": None,  # soft hyphen
        "​": None,  # zero-width space
        "﻿": None,
        "\x00": None,
    }
)
_SPACES = re.compile(r" {2,}")
_HYPHEN_BREAK = re.compile(r"([^\W\d_])-\n([^\W\d_])")
_PAGE_NUMBER = re.compile(
    r"^(?:page\s+|p\.\s*)?[-–—]?\s*\d{1,4}\s*[-–—]?(?:\s*(?:of|/)\s*\d{1,4})?$", re.IGNORECASE
)
_YEAR = re.compile(r"^(?:19|20)\d\d$")  # a bare year on a cover page is content, not a page number
_TRAILING_HYPHEN = re.compile(r"([^\W\d_])-$")
_LEADING_FRAGMENT = re.compile(r"^([^\W\d_]\w*)([.,;:!?)\]]*)(?:[ \n]|$)")
_CJK = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff66-\uff9f]")
_SENTENCE_END = re.compile(r"[.!?:;…][\"'”’)\]]*$")
_LIST_ITEM = re.compile(r"^(?:[•▪◦‣∙·*–—-]\s|\(?\d{1,3}[.)]\s|\(?[a-z][.)]\s)")


def normalize_text(text: str) -> str:
    """Fix ligatures and odd spaces, unify line endings and trim every line."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").translate(_TRANSLATE)
    return "\n".join(_SPACES.sub(" ", line).strip() for line in text.split("\n"))


def dehyphenate(text: str) -> str:
    """Join words split across lines: ``exam-\\nple`` becomes ``example``.

    Only a hyphen between two letters, followed by a lowercase letter, is removed, so
    ``Jean-\\nPaul`` and ``COVID-\\n19`` keep theirs.
    """

    def join(match: re.Match[str]) -> str:
        left, right = match.group(1), match.group(2)
        return left + right if right.islower() else match.group(0)

    return _HYPHEN_BREAK.sub(join, text)


def _edge_key(line: str) -> str:
    return re.sub(r"\d+", "#", line.casefold())


def strip_headers_footers(
    texts: Sequence[str], *, edge_lines: int = 2, min_ratio: float = 0.5, min_pages: int = 3
) -> list[str]:
    """Remove running headers, footers and page numbers from a document's pages.

    A line is removed when it sits within ``edge_lines`` of the top or bottom of its page and
    either looks like a page number ("12", "Page 3 of 10", "- 4 -") or repeats, ignoring
    digits, at an edge of at least ``min_ratio`` of the pages. Repetition is only judged for
    documents with at least ``min_pages`` pages; shorter ones only lose page numbers.
    """
    if edge_lines < 1:
        return list(texts)
    pages = [text.split("\n") for text in texts]
    edges: list[tuple[list[int], list[int]]] = []
    counts: Counter[str] = Counter()
    for lines in pages:
        filled = [i for i, line in enumerate(lines) if line.strip()]
        top, bottom = filled[:edge_lines], filled[::-1][:edge_lines]
        edges.append((top, bottom))
        counts.update({_edge_key(lines[i]) for i in top + bottom})

    threshold = max(2, math.ceil(min_ratio * len(pages)))
    repeated = (
        {key for key, n in counts.items() if n >= threshold} if len(pages) >= min_pages else set()
    )

    def removable(line: str) -> bool:
        stripped = line.strip()
        is_number = bool(_PAGE_NUMBER.match(stripped)) and not _YEAR.match(stripped)
        return is_number or _edge_key(line) in repeated

    out = []
    for lines, (top, bottom) in zip(pages, edges, strict=True):
        drop = set()
        for side in (top, bottom):
            for i in side:  # stop at the first line that is real content
                if not removable(lines[i]):
                    break
                drop.add(i)
        out.append("\n".join(line for i, line in enumerate(lines) if i not in drop))
    return out


def to_paragraphs(text: str) -> list[str]:
    """Reflow hard-wrapped lines into paragraphs.

    Blank lines always end a paragraph. Without them (the usual case for extracted PDF text),
    a line ends a paragraph when it is clearly shorter than the page's typical line and either
    ends a sentence or is followed by a line that starts with a capital letter or digit, which
    catches headings. List items always start a new paragraph.
    """
    lines = text.split("\n")
    long_lines = [len(line) for line in lines if len(line) >= 20]
    typical = statistics.median(long_lines) if len(long_lines) >= 3 else None

    paragraphs: list[str] = []
    current: list[str] = []

    def flush() -> None:
        if current:
            joined = current[0]
            for line in current[1:]:
                joined += _line_joiner(joined, line) + line
            paragraphs.append(joined)
            current.clear()

    for i, line in enumerate(lines):
        if not line:
            flush()
            continue
        if _LIST_ITEM.match(line):
            flush()
        current.append(line)
        if typical is None:
            continue
        nxt = next((n for n in lines[i + 1 :] if n), "")
        short = len(line) < 0.8 * typical
        if short and (
            _SENTENCE_END.search(line) or (len(line) < 0.6 * typical and _starts_block(nxt))
        ):
            flush()
    flush()
    return paragraphs


def _line_joiner(before: str, after: str) -> str:
    """No space after a kept hyphen (``COVID-`` + ``19``) or between CJK characters."""
    if re.search(r"\w-$", before):
        return ""
    if _CJK.match(before[-1]) and _CJK.match(after[0]):
        return ""
    return " "


def join_page_breaks(texts: Sequence[str]) -> list[str]:
    """Move the second half of a word hyphenated across a page break onto the earlier page."""
    out = list(texts)
    for i in range(len(out) - 1):
        end = _TRAILING_HYPHEN.search(out[i].rstrip())
        match = _LEADING_FRAGMENT.match(out[i + 1].lstrip())
        if not end or not match or not match.group(1)[0].islower():
            continue
        out[i] = out[i].rstrip()[:-1] + match.group(1) + match.group(2)
        out[i + 1] = out[i + 1].lstrip()[match.end() :]
    return out


def _starts_block(line: str) -> bool:
    return bool(line) and (line[0].isupper() or line[0].isdigit() or bool(_LIST_ITEM.match(line)))


def clean_pages(
    pages: Iterable[Page], *, strip_headers: bool = True, join_hyphens: bool = True
) -> list[Page]:
    """Clean every page; each returned page holds paragraphs separated by blank lines.

    Header and footer detection only sees the pages passed in, so clean a whole document
    (or a large part of it) rather than one or two pages at a time.
    """
    pages = list(pages)
    texts = [normalize_text(page.text) for page in pages]
    if strip_headers:
        texts = strip_headers_footers(texts)
    if join_hyphens:
        texts = [dehyphenate(text) for text in texts]
        # only pages that really follow each other can share a broken word
        runs: list[list[int]] = []
        for i, page in enumerate(pages):
            if runs and pages[runs[-1][-1]].number + 1 == page.number:
                runs[-1].append(i)
            else:
                runs.append([i])
        for run in runs:
            for i, text in zip(run, join_page_breaks([texts[i] for i in run]), strict=True):
                texts[i] = text
    return [
        Page(number=page.number, text="\n\n".join(to_paragraphs(text)))
        for page, text in zip(pages, texts, strict=True)
    ]
