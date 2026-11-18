# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-11-18

### Added

- `read_pdf`: per-page text and document metadata via pypdf. It accepts paths, bytes or
  streams, supports passwords and page selection, and turns per-page failures into warnings.
- `clean_pages`: fixes ligatures and odd spaces, joins hyphenated words (also across page
  breaks), removes running headers, footers and page numbers, and reflows lines into
  paragraphs.
- `chunk_pages`: size-bounded chunks with sentence overlap, `page_start`/`page_end` and stable
  ids. Headings are never left at the end of a chunk.
- `pdf2chunks` CLI: files, folders and stdin to JSONL, with `--max-chars`, `--overlap`,
  `--pages`, `--raw`, `--password-env`, `--stats` and atomic `-o` output.
