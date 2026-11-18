import pytest

from pdf2chunks import Page, chunk_pages


def sentences(n: int, page: int = 1) -> str:
    return " ".join(f"Sentence {i} on page {page} is here." for i in range(n))


def test_short_document_is_one_chunk():
    chunks = chunk_pages([Page(1, "Hello world.")], source="a.pdf", metadata={"title": "T"})
    assert len(chunks) == 1
    chunk = chunks[0]
    assert (chunk.text, chunk.page_start, chunk.page_end, chunk.index) == ("Hello world.", 1, 1, 0)
    assert chunk.to_dict() == {
        "id": chunk.id,
        "source": "a.pdf",
        "index": 0,
        "page_start": 1,
        "page_end": 1,
        "chars": 12,
        "text": "Hello world.",
        "metadata": {"title": "T"},
    }


def test_chunks_respect_max_chars_and_split_at_sentences():
    chunks = chunk_pages([Page(1, sentences(40))], max_chars=200, overlap=0)
    assert len(chunks) > 1
    assert all(len(c.text) <= 200 for c in chunks)
    assert all(c.text.endswith("here.") for c in chunks)
    assert " ".join(c.text for c in chunks) == sentences(40)


def test_overlap_repeats_whole_trailing_sentences():
    chunks = chunk_pages([Page(1, sentences(20))], max_chars=200, overlap=80)
    for prev, nxt in zip(chunks, chunks[1:], strict=False):
        shared = next(k for k in range(80, 0, -1) if prev.text.endswith(nxt.text[:k]))
        assert 29 <= shared <= 80  # at least one whole sentence, never more than the overlap
        assert nxt.text[shared - 1] == "."
        assert len(nxt.text) <= 200


def test_paragraphs_are_kept_together_and_separated_by_blank_lines():
    text = "First paragraph.\n\nSecond paragraph."
    assert chunk_pages([Page(1, text)])[0].text == text


def test_chunks_track_page_ranges_across_pages():
    pages = [Page(1, sentences(3, 1)), Page(2, sentences(3, 2)), Page(5, sentences(3, 5))]
    chunks = chunk_pages(pages, max_chars=250, overlap=0)
    assert [(c.page_start, c.page_end) for c in chunks] == [(1, 2), (5, 5)]
    single = chunk_pages(pages, max_chars=5000)
    assert (single[0].page_start, single[0].page_end) == (1, 5)


def test_overlap_from_previous_page_counts_in_page_start():
    pages = [Page(1, sentences(4, 1)), Page(2, sentences(4, 2))]
    chunks = chunk_pages(pages, max_chars=200, overlap=60)
    page_two = [c for c in chunks if "page 2" in c.text]
    assert any(c.page_start == 1 for c in page_two)


def test_long_words_are_hard_split():
    url = "https://example.com/" + "x" * 250
    chunks = chunk_pages([Page(1, f"See {url} now.")], max_chars=100, overlap=0)
    assert all(len(c.text) <= 100 for c in chunks)
    assert "".join(c.text.replace(" ", "") for c in chunks) == f"See{url}now."


def test_empty_pages_give_no_chunks():
    assert chunk_pages([Page(1, ""), Page(2, "  \n\n ")]) == []


def test_ids_are_stable_and_unique():
    pages = [Page(1, "Same text.\n\n" * 5)]
    first = chunk_pages(pages, max_chars=12, overlap=0, source="a.pdf")
    second = chunk_pages(pages, max_chars=12, overlap=0, source="a.pdf")
    other = chunk_pages(pages, max_chars=12, overlap=0, source="b.pdf")
    assert [c.id for c in first] == [c.id for c in second]
    assert len({c.id for c in first}) == len(first) == 5
    assert {c.id for c in first}.isdisjoint(c.id for c in other)


@pytest.mark.parametrize(("max_chars", "overlap"), [(0, 0), (100, 100), (100, -1)])
def test_invalid_sizes_are_rejected(max_chars, overlap):
    with pytest.raises(ValueError):
        chunk_pages([Page(1, "x")], max_chars=max_chars, overlap=overlap)


def test_metadata_is_copied():
    meta = {"title": "T"}
    chunk = chunk_pages([Page(1, "x")], metadata=meta)[0]
    meta["title"] = "changed"
    assert chunk.metadata == {"title": "T"}


def test_each_chunk_has_its_own_metadata_dict():
    chunks = chunk_pages([Page(1, "One. " * 50)], max_chars=20, overlap=0, metadata={"a": 1})
    chunks[0].metadata["a"] = 2
    assert chunks[1].metadata == {"a": 1}


def test_large_chunks_with_many_sentences():
    text = " ".join(f"S{i}." for i in range(20_000))
    chunks = chunk_pages([Page(1, text)], max_chars=50_000, overlap=100)
    assert len(chunks) == 3
    assert all(len(c.text) <= 50_000 for c in chunks)
    assert chunks[-1].text.endswith("S19999.")


def test_chunks_do_not_end_on_a_heading():
    text = sentences(5) + "\n\n2. Next section\n\n" + sentences(5)
    chunks = chunk_pages([Page(1, text)], max_chars=200, overlap=60)
    assert not any(c.text.endswith("Next section") for c in chunks)
    assert any(c.text.startswith("2. Next section\n\nSentence 0") for c in chunks)


def test_a_heading_that_cannot_move_stays_and_no_text_is_lost():
    text = "Aa.\n\nBb.\n\nShort title\n\n" + "x" * 45
    chunks = chunk_pages([Page(1, text)], max_chars=50, overlap=0)
    joined = " ".join(c.text for c in chunks)
    assert "Short title" in joined and "x" * 45 in joined
    many = "\n\n".join(f"Heading {i}" for i in range(30))
    out = chunk_pages([Page(1, many)], max_chars=40, overlap=10)
    assert all(f"Heading {i}" in " ".join(c.text for c in out) for i in range(30))
