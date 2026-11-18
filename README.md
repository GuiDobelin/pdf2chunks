# pdf2chunks

**Turn PDFs into JSONL chunks with page numbers and metadata, ready for RAG ingestion**

[![CI](https://github.com/GuiDobelin/pdf2chunks/actions/workflows/ci.yml/badge.svg)](https://github.com/GuiDobelin/pdf2chunks/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

<!-- TODO: one paragraph on the problem this solves and who it is for. -->

```text
$ pdf2chunks --help
```

## Install

```bash
pip install "git+https://github.com/GuiDobelin/pdf2chunks"
```

## Usage

### CLI

```bash
pdf2chunks ...
```

### Python

```python
import pdf2chunks
```

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
ruff check . && ruff format --check .
```

## Ecosystem

Part of a set of small tools around [citerag](https://github.com/GuiDobelin/citerag), a self-hostable
RAG API that answers questions about your documents with verifiable citations.

## License

[MIT](LICENSE)
