import io
import json
import sys

import pytest
from pdfgen import make_pdf

from pdf2chunks import __version__
from pdf2chunks.cli import main, parse_pages

LINE = "Chunking keeps every passage small enough to embed while remembering its page."


def pdf(path, pages=2, title="Guide"):
    path.write_bytes(
        make_pdf([[f"{LINE} Part {n}."] for n in range(1, pages + 1)], info={"Title": title})
    )
    return path


def records(text: str) -> list[dict]:
    return [json.loads(line) for line in text.splitlines()]


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_requires_a_path(capsys):
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2


def test_writes_jsonl_to_stdout(tmp_path, capsys):
    path = pdf(tmp_path / "guide.pdf")
    assert main([str(path), "--max-chars", "100", "--overlap", "0"]) == 0
    rows = records(capsys.readouterr().out)
    assert [(r["page_start"], r["page_end"]) for r in rows] == [(1, 1), (2, 2)]
    assert rows[0]["source"] == str(path)
    assert rows[0]["metadata"] == {"title": "Guide", "page_count": 2}
    assert rows[0]["chars"] == len(rows[0]["text"])


def test_writes_to_a_file(tmp_path, capsys):
    path = pdf(tmp_path / "guide.pdf")
    out = tmp_path / "chunks.jsonl"
    assert main([str(path), "-o", str(out)]) == 0
    assert capsys.readouterr().out == ""
    assert len(records(out.read_text(encoding="utf-8"))) == 1
    assert [p.name for p in tmp_path.iterdir() if p.name.startswith(".")] == []


def test_folders_are_searched_recursively_without_duplicates(tmp_path, capsys):
    pdf(tmp_path / "a.pdf")
    (tmp_path / "sub").mkdir()
    pdf(tmp_path / "sub" / "B.PDF", title="B")
    (tmp_path / ".hidden").mkdir()
    pdf(tmp_path / ".hidden" / "c.pdf")
    (tmp_path / "notes.txt").write_text("not a pdf")
    assert main([str(tmp_path), str(tmp_path / "a.pdf")]) == 0
    sources = [r["source"] for r in records(capsys.readouterr().out)]
    assert sources == [str(tmp_path / "a.pdf"), str(tmp_path / "sub" / "B.PDF")]


def test_empty_folder_warns(tmp_path, capsys):
    assert main([str(tmp_path)]) == 0
    assert "no PDF files" in capsys.readouterr().err


def test_bad_files_are_reported_and_the_rest_still_processed(tmp_path, capsys):
    (tmp_path / "broken.pdf").write_bytes(b"not a pdf")
    good = pdf(tmp_path / "good.pdf")
    assert main([str(tmp_path / "missing.pdf"), str(tmp_path / "broken.pdf"), str(good)]) == 1
    captured = capsys.readouterr()
    assert "missing.pdf: No such file or directory" in captured.err
    assert "broken.pdf: cannot read PDF" in captured.err
    assert len(records(captured.out)) == 1


def test_failed_run_still_writes_the_good_files(tmp_path):
    out = tmp_path / "out.jsonl"
    assert main([str(tmp_path / "missing.pdf"), str(pdf(tmp_path / "ok.pdf")), "-o", str(out)]) == 1
    assert len(records(out.read_text())) == 1


def test_unwritable_output_is_an_error(tmp_path, capsys):
    assert main([str(pdf(tmp_path / "a.pdf")), "-o", str(tmp_path / "nope" / "x.jsonl")]) == 1
    assert "error" in capsys.readouterr().err


def test_pages_option(tmp_path, capsys):
    path = pdf(tmp_path / "guide.pdf", pages=5)
    assert main([str(path), "--pages", "2-3,5", "--max-chars", "100", "--overlap", "0"]) == 0
    assert [r["page_start"] for r in records(capsys.readouterr().out)] == [2, 3, 5]
    assert main([str(path), "--pages", "9"]) == 1
    assert "page 9 does not exist" in capsys.readouterr().err
    assert main([str(path), "--pages", "4-9", "--max-chars", "100", "--overlap", "0"]) == 0
    captured = capsys.readouterr()
    assert [r["page_start"] for r in records(captured.out)] == [4, 5]
    assert "only 2 of the selected pages exist (the PDF has 5)" in captured.err


@pytest.mark.parametrize(
    ("spec", "expected"), [("1", [1]), ("1-3,7", [1, 2, 3, 7]), ("3, 1-2", [1, 2, 3])]
)
def test_parse_pages(spec, expected):
    assert parse_pages(spec) == expected


@pytest.mark.parametrize("spec", ["", "0", "3-1", "a", "1-", "1,,2", "1-999999"])
def test_parse_pages_rejects_bad_specs(spec):
    import argparse

    with pytest.raises(argparse.ArgumentTypeError):
        parse_pages(spec)


@pytest.mark.parametrize(
    "args",
    [
        ["--max-chars", "0"],
        ["--overlap", "-1"],
        ["--max-chars", "100", "--overlap", "100"],
        ["--max-chars", "ten"],
        ["-", "-"],
    ],
)
def test_invalid_options(tmp_path, args):
    with pytest.raises(SystemExit) as exc:
        main([str(tmp_path / "a.pdf"), *args])
    assert exc.value.code == 2


def test_reads_standard_input(tmp_path, monkeypatch, capsys):
    data = make_pdf([[LINE]])
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(data)))
    assert main(["-"]) == 0
    assert records(capsys.readouterr().out)[0]["source"] == "<stdin>"


def test_raw_keeps_page_numbers(tmp_path, capsys):
    path = tmp_path / "n.pdf"
    path.write_bytes(make_pdf([[LINE, "7"]]))
    main([str(path)])
    assert not records(capsys.readouterr().out)[0]["text"].endswith("7")
    main([str(path), "--raw"])
    assert records(capsys.readouterr().out)[0]["text"].endswith("7")


def test_stats_and_scanned_warning(tmp_path, capsys):
    blank = tmp_path / "scan.pdf"
    blank.write_bytes(make_pdf([[]]))
    assert main([str(blank), str(pdf(tmp_path / "g.pdf")), "--stats"]) == 0
    err = capsys.readouterr().err
    assert "scan.pdf: no extractable text" in err
    assert "g.pdf: 2 pages of 2, 1 chunk, " in err


def test_password_from_environment(tmp_path, monkeypatch, capsys):
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter()
    writer.append(PdfReader(io.BytesIO(make_pdf([[LINE]]))))
    writer.encrypt("pw", algorithm="RC4-128")
    path = tmp_path / "locked.pdf"
    with path.open("wb") as fh:
        writer.write(fh)

    assert main([str(path)]) == 1
    assert "password is required" in capsys.readouterr().err
    monkeypatch.setenv("PDF_PW", "pw")
    assert main([str(path), "--password-env", "PDF_PW"]) == 0
    assert len(records(capsys.readouterr().out)) == 1
    monkeypatch.delenv("PDF_PW")
    with pytest.raises(SystemExit):
        main([str(path), "--password-env", "PDF_PW"])


def test_non_ascii_is_written_as_utf8(tmp_path):
    path = tmp_path / "pt.pdf"
    path.write_bytes(make_pdf([["Informação útil sobre a extração."]]))
    out = tmp_path / "o.jsonl"
    main([str(path), "-o", str(out)])
    assert "Informação útil" in out.read_text(encoding="utf-8")


def test_stdout_is_utf8_whatever_the_locale(tmp_path, monkeypatch):
    path = tmp_path / "pt.pdf"
    path.write_bytes(make_pdf([["Informação útil."]]))
    raw = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(raw, encoding="ascii"))
    assert main([str(path)]) == 0
    assert "Informação útil." in raw.getvalue().decode("utf-8")
    sys.stdout.write("still usable")  # the wrapper was detached, not closed


def test_missing_stdin_is_an_error(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", None)
    assert main(["-"]) == 1
    assert "standard input is not available" in capsys.readouterr().err


def test_output_keeps_the_permissions_of_an_existing_file(tmp_path):
    out = tmp_path / "chunks.jsonl"
    out.write_text("")
    out.chmod(0o600)
    assert main([str(pdf(tmp_path / "a.pdf")), "-o", str(out)]) == 0
    assert (out.stat().st_mode & 0o777) == 0o600
    assert out.read_text()
