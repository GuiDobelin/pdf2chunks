from pdf2chunks import Page, clean_pages
from pdf2chunks.clean import dehyphenate, normalize_text, strip_headers_footers, to_paragraphs

PROSE = (
    "Retrieval augmented generation combines a search step with a language model so that\n"
    "answers are grounded in documents the model has never seen during its training run,\n"
    "which makes citations possible and reduces the amount of invented detail in answers.\n"
)


def test_normalize_text_fixes_ligatures_spaces_and_line_endings():
    raw = "eﬃcient  work\r\nsoft­hyphen\t here  \rend"
    assert normalize_text(raw) == "efficient work\nsofthyphen here\nend"


def test_dehyphenate_joins_lowercase_continuations_only():
    assert dehyphenate("an exam-\nple") == "an example"
    assert dehyphenate("Jean-\nPaul") == "Jean-\nPaul"
    assert dehyphenate("COVID-\n19") == "COVID-\n19"
    assert dehyphenate("ger-\nmänisch") == "germänisch"


def test_strip_headers_footers_removes_repeated_lines_and_page_numbers():
    pages = [
        f"ACME Annual Report 2025 · {n}\nBody about {topic}.\nMore on {topic}.\n"
        f"Confidential\nPage {n} of 4"
        for n, topic in enumerate(["sales", "costs", "hiring", "risks"], start=1)
    ]
    out = strip_headers_footers(pages)
    assert out[0] == "Body about sales.\nMore on sales."
    assert all("ACME" not in page and "Page" not in page for page in out)


def test_strip_headers_footers_keeps_repeated_lines_away_from_the_edges():
    pages = ["Title\nIntro\nSee the appendix.\nMore\nEnd"] * 3
    out = strip_headers_footers(pages, edge_lines=1)
    assert out[0] == "Intro\nSee the appendix.\nMore"


def test_strip_headers_footers_stops_at_first_real_line():
    pages = [f"Header\n{word} text\nHeader\n{word} end" for word in ("one", "two", "three")]
    out = strip_headers_footers(pages)
    assert out == [f"{word} text\nHeader\n{word} end" for word in ("one", "two", "three")]


def test_strip_headers_footers_short_documents_only_lose_page_numbers():
    pages = ["Report\nBody one.\n1", "Report\nBody two.\n2"]
    assert strip_headers_footers(pages) == ["Report\nBody one.", "Report\nBody two."]


def test_strip_headers_footers_ignores_blank_lines_at_the_edges():
    pages = ["\n\n- 1 -\nText\n\n", "\n- 2 -\nMore\n"]
    out = strip_headers_footers(pages)
    assert "- 1 -" not in out[0] and "Text" in out[0]


def test_to_paragraphs_uses_blank_lines():
    assert to_paragraphs("one\ntwo\n\nthree") == ["one two", "three"]


def test_to_paragraphs_detects_short_last_lines_and_headings():
    text = "1. Introduction\n" + PROSE + "This is short.\n" + PROSE.rstrip("\n")
    paragraphs = to_paragraphs(text)
    assert paragraphs[0] == "1. Introduction"
    assert paragraphs[1].endswith("This is short.")
    assert paragraphs[2].startswith("Retrieval")
    assert len(paragraphs) == 3


def test_to_paragraphs_starts_list_items_on_their_own():
    text = PROSE + "• first item\n• second item that wraps onto a\nsecond line"
    paragraphs = to_paragraphs(text)
    assert paragraphs[-2:] == ["• first item", "• second item that wraps onto a second line"]


def test_clean_pages_keeps_page_numbers_and_returns_paragraphs():
    pages = [Page(3, "Hy-\nphen-\nated words\n\nnext"), Page(4, "")]
    out = clean_pages(pages)
    assert [p.number for p in out] == [3, 4]
    assert out[0].text == "Hyphenated words\n\nnext"
    assert out[1].text == ""


def test_clean_pages_options_can_be_turned_off():
    pages = [Page(1, "exam-\nple\n7")]
    out = clean_pages(pages, strip_headers=False, join_hyphens=False)
    assert out[0].text == "exam- ple 7"
