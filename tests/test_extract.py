import io

import pytest
from pdfgen import make_pdf
from pypdf import PdfReader, PdfWriter

from pdf2chunks import PdfError, chunk_document, pdf_to_chunks, read_pdf

TOPICS = ["Ingestion", "Retrieval", "Generation", "Evaluation"]
BODY = [
    "systems need clean input: every chunk of a document should contain the",
    "prose of the document and nothing else, so that the embedding of the chunk is not",
    "dominated by running headers, page numbers or words broken by hyphen-",
]


def report(pages: int = 3) -> bytes:
    return make_pdf(
        [
            [
                "Internal Report",
                f"{TOPICS[n - 1]} in self-hosted retrieval",
                *BODY,
                f"ation in the {TOPICS[n - 1].lower()} step.",
                f"Page {n} of {pages}",
            ]
            for n in range(1, pages + 1)
        ],
        info={"Title": "Quarterly report", "Author": "Ana Souza", "CreationDate": "D:20250102"},
    )


def encrypt(data: bytes, password: str) -> bytes:
    writer = PdfWriter()
    writer.append(PdfReader(io.BytesIO(data)))
    writer.encrypt(password, algorithm="RC4-128")
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def test_read_pdf_returns_pages_and_metadata(tmp_path):
    path = tmp_path / "report.pdf"
    path.write_bytes(report())
    doc = read_pdf(path)
    assert doc.source == str(path)
    assert doc.page_count == 3
    assert [p.number for p in doc.pages] == [1, 2, 3]
    assert "Internal Report" in doc.pages[0].text
    assert doc.metadata["title"] == "Quarterly report"
    assert doc.metadata["author"] == "Ana Souza"
    assert doc.metadata["created"].startswith("2025-01-02")
    assert doc.warnings == ()


def test_read_pdf_accepts_bytes_and_streams():
    data = report()
    assert read_pdf(data).source == ""
    assert read_pdf(io.BytesIO(data), source="mem.pdf").source == "mem.pdf"


def test_read_pdf_selected_pages():
    doc = read_pdf(report(), pages=[3, 1, 3])
    assert [p.number for p in doc.pages] == [1, 3]
    assert doc.page_count == 3
    with pytest.raises(ValueError, match="page 4"):
        read_pdf(report(), pages=[4])


def test_read_pdf_without_metadata():
    assert read_pdf(make_pdf([["hi"]])).metadata == {}


def test_non_ascii_text_survives():
    doc = read_pdf(make_pdf([["Ação e café à beira-mar"]]))
    assert "Ação e café à beira-mar" in doc.pages[0].text


@pytest.mark.parametrize("data", [b"", b"not a pdf at all", b"%PDF-1.4\n garbage"])
def test_garbage_raises_pdf_error(data):
    with pytest.raises(PdfError, match="cannot read PDF"):
        read_pdf(data)


def test_encrypted_pdf_needs_the_password():
    data = encrypt(report(), "s3cret")
    with pytest.raises(PdfError, match="password is required"):
        read_pdf(data)
    with pytest.raises(PdfError, match="password is wrong"):
        read_pdf(data, password="nope")
    assert "Internal Report" in read_pdf(data, password="s3cret").pages[0].text


def test_failing_page_becomes_a_warning(monkeypatch):
    from pypdf import PageObject

    original = PageObject.extract_text
    calls = {"n": 0}

    def flaky(self, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise KeyError("/Font")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(PageObject, "extract_text", flaky)
    doc = read_pdf(report())
    assert doc.pages[1].text == ""
    assert doc.warnings == ("page 2: text extraction failed: '/Font'",)


def test_pdf_to_chunks_end_to_end():
    chunks = pdf_to_chunks(report(), source="report.pdf", max_chars=400, overlap=0)
    assert [(c.page_start, c.page_end) for c in chunks] == [(1, 1), (2, 2), (3, 3)]
    text = chunks[0].text
    assert "Internal Report" not in text and "Page 1" not in text
    assert "hyphenation in the ingestion step." in text
    assert chunks[0].metadata == {
        "title": "Quarterly report",
        "author": "Ana Souza",
        "created": chunks[0].metadata["created"],
        "page_count": 3,
    }


def test_chunk_document_without_cleaning_keeps_raw_text():
    doc = read_pdf(report())
    raw = chunk_document(doc, clean=False, max_chars=5000)
    assert "Internal Report" in raw[0].text
    assert "hyphen- ation" in raw[0].text
