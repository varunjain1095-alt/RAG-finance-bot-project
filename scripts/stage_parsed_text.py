"""Insert parsed_text into source_documents when embed failed before DB write."""

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
_PRESERVE_ENV_KEYS = ("DATABASE_URL", "ANTHROPIC_API_KEY", "VOYAGE_API_KEY", "ANTHROPIC_MODEL")
_preserved_env = {key: os.environ[key] for key in _PRESERVE_ENV_KEYS if os.environ.get(key)}
load_dotenv(PROJECT_ROOT / ".env", override=True)
for key, value in _preserved_env.items():
    os.environ[key] = value

from rag_bot.config import reload_settings
from rag_bot.ingestion.db import get_connection, get_parsed_text, insert_document
from rag_bot.ingestion.fetch import fetch_url
from rag_bot.ingestion.pipeline import _parse_content
from rag_bot.ingestion.sources import load_sources_from_markdown


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage parsed_text row (no embed)")
    parser.add_argument("--source-list", type=Path, default=PROJECT_ROOT / "source_list.md")
    parser.add_argument("--urls", nargs="+", required=True)
    args = parser.parse_args()

    reload_settings()
    entries = [e for e in load_sources_from_markdown(args.source_list) if e.source_url in set(args.urls)]

    with get_connection() as conn:
        for entry in entries:
            existing = get_parsed_text(conn, entry.source_url)
            if existing and existing.strip():
                print(f"SKIP {entry.source_url} (parsed_text already in DB, len={len(existing)})")
                continue
            content, content_type = fetch_url(entry.source_url)
            markdown, _ = _parse_content(content, entry.source_url, content_type)
            insert_document(conn, entry, markdown)
            conn.commit()
            print(f"STAGED {entry.source_url} parsed_len={len(markdown)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
