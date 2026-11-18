import argparse
import contextlib
import io
import json
import os
import re
import stat
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import TextIO

from pdf2chunks import PdfError, __version__, chunk_document, read_pdf
from pdf2chunks.chunk import DEFAULT_MAX_CHARS, DEFAULT_OVERLAP

_RANGE = re.compile(r"^(\d+)(?:-(\d+))?$")


def parse_pages(spec: str) -> list[int]:
    """Parse a 1-based page selection such as ``1-3,7``."""
    pages: set[int] = set()
    for part in spec.replace(" ", "").split(","):
        match = _RANGE.match(part)
        if not match:
            raise argparse.ArgumentTypeError(f"invalid page selection {spec!r} (try 1-3,7)")
        start = int(match.group(1))
        end = int(match.group(2) or start)
        if start < 1 or end < start:
            raise argparse.ArgumentTypeError(f"invalid page range {part!r}")
        if end - start > 100_000:
            raise argparse.ArgumentTypeError(f"page range {part!r} is too large")
        pages.update(range(start, end + 1))
    return sorted(pages)


def _int_at_least(minimum: int):
    def parse(value: str) -> int:
        try:
            number = int(value)
        except ValueError:
            raise argparse.ArgumentTypeError(f"expected an integer, got {value!r}") from None
        if number < minimum:
            raise argparse.ArgumentTypeError(f"must be at least {minimum}")
        return number

    return parse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pdf2chunks",
        description=(
            "Turn PDFs into JSONL chunks with page numbers and metadata, ready for RAG ingestion. "
            "Writes one JSON object per chunk."
        ),
    )
    parser.add_argument(
        "paths",
        nargs="+",
        metavar="PATH",
        help="PDF files or folders (searched recursively for *.pdf); - reads standard input",
    )
    parser.add_argument("-o", "--output", default="-", help="write JSONL here (default: stdout)")
    parser.add_argument(
        "--max-chars",
        type=_int_at_least(1),
        default=DEFAULT_MAX_CHARS,
        help=f"maximum characters per chunk (default: {DEFAULT_MAX_CHARS})",
    )
    parser.add_argument(
        "--overlap",
        type=_int_at_least(0),
        default=DEFAULT_OVERLAP,
        help=f"characters of trailing sentences repeated in the next chunk "
        f"(default: {DEFAULT_OVERLAP})",
    )
    parser.add_argument(
        "--pages", type=parse_pages, help="only these 1-based pages, e.g. 1-3,7 (default: all)"
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="skip cleaning (keep headers, footers, page numbers and hyphenation)",
    )
    parser.add_argument(
        "--password-env",
        metavar="VAR",
        help="read the password for encrypted PDFs from this environment variable",
    )
    parser.add_argument(
        "--stats", action="store_true", help="print pages, chunks and characters per file to stderr"
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def _expand(paths: list[str]) -> Iterator[str]:
    """Yield each input, replacing folders by the PDFs inside them, without duplicates."""
    seen: set[str] = set()
    for raw in paths:
        path = Path(raw)
        if raw != "-" and path.is_dir():
            found = sorted(
                p
                for p in path.rglob("*")
                if p.suffix.lower() == ".pdf"
                and p.is_file()
                and not any(part.startswith(".") for part in p.relative_to(path).parts)
            )
            candidates = [str(p) for p in found]
            if not candidates:
                print(f"pdf2chunks: warning: no PDF files in {raw}", file=sys.stderr)
        else:
            candidates = [raw]
        for candidate in candidates:
            key = candidate if candidate == "-" else os.path.realpath(candidate)
            if key not in seen:
                seen.add(key)
                yield candidate


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _write_lines(out: TextIO, chunks) -> None:
    for chunk in chunks:
        out.write(json.dumps(chunk.to_dict(), ensure_ascii=False) + "\n")


def _process(args: argparse.Namespace, out: TextIO, password: str | None) -> int:
    failures = 0
    for path in _expand(args.paths):
        name = "<stdin>" if path == "-" else path
        try:
            if path == "-" and sys.stdin is None:
                raise OSError("standard input is not available")
            src = sys.stdin.buffer.read() if path == "-" else path
            # in a batch, a short PDF yields the selected pages it has instead of failing
            document = read_pdf(
                src, password=password, pages=args.pages, source=name, ignore_missing_pages=True
            )
        except (PdfError, ValueError, OSError) as exc:
            reason = exc.strerror if isinstance(exc, OSError) and exc.strerror else exc
            print(f"pdf2chunks: error: {name}: {reason}", file=sys.stderr)
            failures += 1
            continue
        if args.pages and len(document.pages) < len(args.pages):
            print(
                f"pdf2chunks: warning: {name}: only {len(document.pages)} of the selected pages "
                f"exist (the PDF has {document.page_count})",
                file=sys.stderr,
            )
        for warning in document.warnings:
            print(f"pdf2chunks: warning: {name}: {warning}", file=sys.stderr)
        chunks = chunk_document(
            document, max_chars=args.max_chars, overlap=args.overlap, clean=not args.raw
        )
        if not chunks and document.pages:
            print(
                f"pdf2chunks: warning: {name}: no extractable text "
                "(a scanned PDF? OCR is not supported)",
                file=sys.stderr,
            )
        _write_lines(out, chunks)
        out.flush()
        if args.stats:
            chars = sum(len(c.text) for c in chunks)
            print(
                f"{name}: {_plural(len(document.pages), 'page')} of {document.page_count}, "
                f"{_plural(len(chunks), 'chunk')}, {_plural(chars, 'character')}",
                file=sys.stderr,
            )
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.overlap >= args.max_chars:
        parser.error("--overlap must be smaller than --max-chars")
    if args.paths.count("-") > 1:
        parser.error("standard input (-) can only be read once")
    password = None
    if args.password_env:
        password = os.environ.get(args.password_env)
        if password is None:
            parser.error(f"environment variable {args.password_env} is not set")

    if args.output == "-":
        # Always UTF-8, whatever the console or locale encoding (e.g. cp1252 on Windows).
        buffer = getattr(sys.stdout, "buffer", None)
        out = (
            io.TextIOWrapper(buffer, encoding="utf-8", newline="\n", line_buffering=False)
            if buffer is not None
            else sys.stdout
        )
        try:
            return _process(args, out, password)
        except BrokenPipeError:
            # The reader (e.g. `| head`) is gone, which is not an error. Point stdout at devnull
            # so the flush at interpreter exit does not complain again.
            with contextlib.suppress(OSError, ValueError, AttributeError):
                os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
            return 0
        finally:
            if out is not sys.stdout:
                with contextlib.suppress(OSError, ValueError):
                    out.flush()
                out.detach()  # leave sys.stdout usable

    # Write to a temporary file next to the target and rename it at the end, so a failed or
    # interrupted run never leaves a half-written JSONL behind.
    target = Path(args.output)
    try:
        fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".tmp")
    except OSError as exc:
        print(f"pdf2chunks: error: {args.output}: {exc.strerror or exc}", file=sys.stderr)
        return 1
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as out:
            status = _process(args, out, password)
        try:  # keep the permissions of a file being replaced
            mode = stat.S_IMODE(os.stat(target).st_mode)
        except FileNotFoundError:
            mode = 0o666 & ~_umask()
        os.chmod(tmp, mode)
        os.replace(tmp, target)
    except OSError as exc:
        print(f"pdf2chunks: error: {args.output}: {exc.strerror or exc}", file=sys.stderr)
        status = 1
    finally:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
    return status


def _umask() -> int:
    mask = os.umask(0)
    os.umask(mask)
    return mask


if __name__ == "__main__":
    raise SystemExit(main())
