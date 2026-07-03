"""Retry embedding from corpus parsed_text (no fetch/parse unless staging)."""

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
from rag_bot.ingestion.pipeline import run_embedding_retry

# Smallest first to reduce rate-limit pressure before large jobs.
DEFAULT_URLS = [
    "https://digitalfactsheet.icicipruamc.com/fact/icici-prudential-elss-tax-saver-fund.php",
    "https://investor.sebi.gov.in/Investor-charter.html",
    "https://digitalfactsheet.icicipruamc.com/fact/pdf/fund-factsheet-for-march-2026.pdf",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Retry Voyage embed from DB parsed_text")
    parser.add_argument(
        "--source-list",
        type=Path,
        default=PROJECT_ROOT / "source_list.md",
    )
    parser.add_argument("--urls", nargs="+", default=DEFAULT_URLS)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--batch-pause", type=float, default=2.5)
    parser.add_argument(
        "--stage-missing",
        action="store_true",
        help="Fetch+parse into DB when parsed_text missing (embed failed before write)",
    )
    args = parser.parse_args()

    reload_settings()
    url_list = list(args.urls)
    results = run_embedding_retry(
        args.source_list,
        set(url_list),
        allow_stage_missing=args.stage_missing,
        embed_batch_size=args.batch_size,
        embed_batch_pause_seconds=args.batch_pause,
        url_order=url_list,
    )

    for r in results:
        print(
            f"{r.entry.source_url}, {r.status.value}, "
            f"chars={r.char_count}, parents={r.parent_count}, children={r.child_count}, "
            f"error={r.error or ''}"
        )

    failed = sum(1 for r in results if r.status.value == "failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
