"""Audit fetch status for active corpus URLs."""

import httpx

from rag_bot.ingestion.fetch import fetch_url
from rag_bot.ingestion.parsers.html import parse_html
from rag_bot.ingestion.parsers.pdf import parse_pdf
from rag_bot.ingestion.sources import SOURCE_ENTRIES

URLS = [e.source_url for e in SOURCE_ENTRIES]


def main() -> None:
    for url in URLS:
        try:
            content, ctype = fetch_url(url)
            raw_len = len(content)
            if ctype and "pdf" in ctype.lower() or url.lower().endswith(".pdf"):
                md, _ = parse_pdf(content)
            else:
                md, _ = parse_html(content, url)
            extracted = len(md)
            snippet = md.strip()[:120].replace("\n", " ").replace(",", ";")
            print(f"{url}, HTTP 200; extracted={extracted}, raw={raw_len}, snippet={snippet!r}")
        except httpx.HTTPStatusError as exc:
            print(f"{url}, HTTP {exc.response.status_code}, {len(exc.response.content)}")
        except Exception as exc:  # noqa: BLE001
            print(f"{url}, {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
