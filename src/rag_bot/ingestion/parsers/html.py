"""HTML parsing — Trafilatura primary, BeautifulSoup fallback."""

import logging
import re

import trafilatura
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def _normalize_markdown(text: str) -> str:
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_html(content: bytes, url: str) -> tuple[str, list[str]]:
    warnings: list[str] = []
    html = content.decode("utf-8", errors="replace")

    extracted = trafilatura.extract(
        html,
        url=url,
        output_format="markdown",
        include_tables=True,
        include_links=False,
    )
    if extracted and len(extracted.strip()) > 200:
        return _normalize_markdown(extracted), warnings

    warnings.append("trafilatura_fallback_to_beautifulsoup")
    soup = BeautifulSoup(html, "lxml")
    main = soup.select_one("main") or soup.select_one("article") or soup.body
    if not main:
        return "", warnings

    parts: list[str] = []
    for el in main.find_all(["h1", "h2", "h3", "h4", "p", "li", "table"]):
        name = el.name
        text = el.get_text(" ", strip=True)
        if not text:
            continue
        if name == "h1":
            parts.append(f"# {text}")
        elif name == "h2":
            parts.append(f"## {text}")
        elif name == "h3":
            parts.append(f"### {text}")
        elif name == "h4":
            parts.append(f"#### {text}")
        elif name == "li":
            parts.append(f"- {text}")
        else:
            parts.append(text)

    markdown = _normalize_markdown("\n\n".join(parts))
    if len(markdown) < 100:
        warnings.append("low_html_extract")
    return markdown, warnings
