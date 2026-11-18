"""Regenerate examples/handbook.pdf, the small PDF used in the README.

python scripts/make_example.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from pdfgen import make_pdf  # noqa: E402

HEADER = "Acme Engineering Handbook"
PAGES = [
    [
        "1. On-call basics",
        "Every service has a primary and a secondary on-call engineer. The primary",
        "acknowledges a page within five minutes and opens an incident channel; the",
        "secondary takes over if there is no acknowledgement after fifteen minutes.",
        "Handover happens every Monday at 10:00 and is recorded in the rota.",
        "2. Severity levels",
        "SEV1 means customers cannot use the product. SEV2 means a degraded experi-",
        "ence for many customers. SEV3 covers everything that can wait for the next",
        "working day.",
    ],
    [
        "3. Postmortems",
        "A postmortem is written for every SEV1 and SEV2 incident within five work-",
        "ing days. It is blameless: it describes what the system allowed to happen,",
        "not who made a mistake. Action items get an owner and a due date.",
        "4. Deploy freezes",
        "There are no deploys on Fridays after 15:00 or during the last two weeks of",
        "December, except for fixes to an open SEV1 or SEV2 incident.",
    ],
]


def main() -> None:
    total = len(PAGES)
    pages = [[HEADER, "", *lines, "", f"Page {n} of {total}"] for n, lines in enumerate(PAGES, 1)]
    data = make_pdf(pages, info={"Title": "Engineering Handbook", "Author": "Acme Platform Team"})
    (ROOT / "examples" / "handbook.pdf").write_bytes(data)


if __name__ == "__main__":
    main()
