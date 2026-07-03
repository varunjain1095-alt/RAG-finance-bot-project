"""Scheme tagging for AMC combined monthly factsheet PDFs (multi-scheme, single document)."""

import re

from rag_bot.ingestion.chunking import ParentChunkData, chunk_markdown
from rag_bot.retrieval.schemes import (
    BALANCED_ADVANTAGE,
    CANONICAL_SCHEMES,
    ELSS,
    FLEXICAP,
    LARGE_CAP,
)

PERFORMANCE_DETAILS_RE = re.compile(
    r"performance details provided herein are of\s+"
    r"(ICICI Prudential\s+.+?Fund)\s*\.?",
    re.IGNORECASE,
)

PAGE_HEADER_RE = re.compile(r"^##\s+Page\s+\d+\s*$", re.MULTILINE | re.IGNORECASE)

SCHEME_ALIASES: dict[str, str] = {
    "icici prudential large cap fund": LARGE_CAP,
    "icici prudential flexicap fund": FLEXICAP,
    "icici prudential elss tax saver fund": ELSS,
    "icici prudential balanced advantage fund": BALANCED_ADVANTAGE,
}

FACTSHEET_MARKERS: tuple[str, ...] = tuple(
    marker.lower()
    for marker in (
        "application amount for fresh subscription",
        "performance details provided herein",
        "min.addl.investment",
        "nav (as on",
        "sip returns",
        "minimum redemption",
        "total expense ratio",
    )
)


def _split_pages(markdown: str) -> list[tuple[str, str]]:
    matches = list(PAGE_HEADER_RE.finditer(markdown))
    if not matches:
        return [("Document", markdown.strip())]

    pages: list[tuple[str, str]] = []
    if matches[0].start() > 0:
        preamble = markdown[:matches[0].start()].strip()
        if preamble:
            pages.append(("Preamble", preamble))

    for index, match in enumerate(matches):
        heading = match.group(0).replace("#", "").strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        body = markdown[start:end].strip()
        pages.append((heading, body))
    return pages


def _normalize_scheme(detected: str) -> str | None:
    key = re.sub(r"\s+", " ", detected.strip().lower())
    if key in SCHEME_ALIASES:
        return SCHEME_ALIASES[key]
    for canonical in CANONICAL_SCHEMES:
        if canonical.lower() in key:
            return canonical
    return None


def _detect_scheme_from_text(text: str) -> str | None:
    match = PERFORMANCE_DETAILS_RE.search(text)
    if not match:
        return None
    return _normalize_scheme(match.group(1))


def _count_scheme_mentions(text: str) -> dict[str, int]:
    lower = text.lower()
    return {scheme: lower.count(scheme.lower()) for scheme in CANONICAL_SCHEMES}


def _is_index_like(text: str) -> bool:
    counts = _count_scheme_mentions(text)
    return sum(1 for count in counts.values() if count > 0) >= 3


def _is_factsheet_page(text: str) -> bool:
    lower = text.lower()
    return any(marker in lower for marker in FACTSHEET_MARKERS)


def assign_scheme_for_page(
    text: str,
    sticky_scheme: str | None,
) -> tuple[str | None, str | None]:
    """Return (scheme for this page, updated sticky scheme for continuations)."""
    detected = _detect_scheme_from_text(text)
    if detected:
        return detected, detected

    if _is_index_like(text):
        return None, None

    if sticky_scheme and _is_factsheet_page(text):
        return sticky_scheme, sticky_scheme

    return None, sticky_scheme


def chunk_combined_factsheet_markdown(markdown: str) -> list[ParentChunkData]:
    """Chunk combined factsheet markdown with per-page scheme_name tagging."""
    all_parents: list[ParentChunkData] = []
    sticky_scheme: str | None = None

    for heading, body in _split_pages(markdown):
        page_text = f"{heading}\n{body}".strip()
        scheme, sticky_scheme = assign_scheme_for_page(page_text, sticky_scheme)

        if heading in {"Document", "Preamble"}:
            page_md = body
        else:
            page_md = f"## {heading}\n\n{body}"

        for parent in chunk_markdown(page_md):
            parent.scheme_name = scheme
            all_parents.append(parent)

    return all_parents
