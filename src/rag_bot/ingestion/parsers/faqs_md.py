"""Split ICICI Bank FAQs.md into sections keyed by embedded citation URLs."""

import re
from pathlib import Path

_CITATION_RE = re.compile(
    r"(?:\*\*)?CITATION\s+LINK(?:\*\*)?\s*:?\s*(?:\*\*)?"
    r"(?:\[?\*?\*?)?(https://[^\s\*\]\)]+)",
    re.IGNORECASE,
)


def _strip_bold(text: str) -> str:
    return re.sub(r"\*+", "", text).strip()


def _section_heading(body: str) -> str:
    for line in body.splitlines():
        cleaned = _strip_bold(line.strip())
        if len(cleaned) >= 12 and not cleaned.lower().startswith("citation"):
            return cleaned[:120]
    return "FAQ section"


def split_faqs_by_citation(markdown: str) -> list[tuple[str, str, str]]:
    """Return (citation_url, section_heading, section_markdown) for each block."""
    lines = markdown.splitlines()
    sections: list[tuple[str, str, str]] = []
    current_url: str | None = None
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_lines, current_url
        body = "\n".join(current_lines).strip()
        if current_url and body:
            sections.append((current_url, _section_heading(body), body))
        current_lines = []

    for line in lines:
        match = _CITATION_RE.search(line)
        if match:
            flush()
            current_url = match.group(1).rstrip("*").rstrip(")")
            continue
        if current_url is not None:
            current_lines.append(line)

    flush()
    return sections


def load_faqs_sections(path: Path) -> list[tuple[str, str, str]]:
    text = path.read_text(encoding="utf-8")
    return split_faqs_by_citation(text)
