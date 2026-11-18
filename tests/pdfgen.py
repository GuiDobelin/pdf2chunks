"""Build tiny, valid PDFs in memory so the tests need no binary fixtures."""


def _escape(line: str) -> str:
    out = []
    for byte in line.encode("cp1252"):
        char = chr(byte)
        if char in "()\\":
            out.append("\\" + char)
        elif 32 <= byte < 127:
            out.append(char)
        else:
            out.append(f"\\{byte:03o}")
    return "".join(out)


def make_pdf(pages: list[list[str]], *, info: dict[str, str] | None = None) -> bytes:
    """Return a PDF with one page per item; each page is a list of text lines.

    An empty string in a page's lines leaves a blank line (a paragraph gap).
    """
    objects: list[bytes] = []

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    catalog = add(b"")  # filled in below, once the page tree exists
    tree = add(b"")
    font = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    kids = []
    for lines in pages:
        ops = ["BT", "/F1 11 Tf", "14 TL", "72 760 Td"]
        for line in lines:
            if line:
                ops.append(f"({_escape(line)}) Tj")
            ops.append("T*")
        ops.append("ET")
        stream = "\n".join(ops).encode("latin-1")
        content = add(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream))
        kids.append(
            add(
                b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 612 792] "
                b"/Resources << /Font << /F1 %d 0 R >> >> /Contents %d 0 R >>"
                % (tree, font, content)
            )
        )
    refs = " ".join(f"{k} 0 R" for k in kids).encode()
    objects[tree - 1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (refs, len(kids))
    objects[catalog - 1] = b"<< /Type /Catalog /Pages %d 0 R >>" % tree
    info_ref = None
    if info:
        entries = " ".join(f"/{key} ({_escape(value)})" for key, value in info.items())
        info_ref = add(f"<< {entries} >>".encode("latin-1"))

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (number, body)
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    trailer = b"/Size %d /Root %d 0 R" % (len(objects) + 1, catalog)
    if info_ref:
        trailer += b" /Info %d 0 R" % info_ref
    out += b"trailer\n<< %s >>\nstartxref\n%d\n%%%%EOF\n" % (trailer, xref)
    return bytes(out)
