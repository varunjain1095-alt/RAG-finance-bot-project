"""Run Phase 1 ingestion against the authoritative source list."""

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
from rag_bot.ingestion.pipeline import run_ingestion
from rag_bot.ingestion.report import write_ingestion_report

DEFAULT_SOURCE_LIST = PROJECT_ROOT / "source_list.md"


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest corpus from source_list.md")
    parser.add_argument(
        "--source-list",
        type=Path,
        default=DEFAULT_SOURCE_LIST,
        help="Path to authoritative source list markdown",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=PROJECT_ROOT / "ingestion_report.md",
        help="Output path for ingestion report",
    )
    parser.add_argument(
        "--no-clear",
        action="store_true",
        help="Do not wipe corpus before ingest (for partial re-ingest)",
    )
    parser.add_argument(
        "--only-urls",
        nargs="+",
        help="Re-ingest only these source URLs (implies --no-clear)",
    )
    args = parser.parse_args()

    if not args.source_list.exists():
        print(f"FAIL: source list not found: {args.source_list}")
        return 1

    reload_settings()
    only_urls = set(args.only_urls) if args.only_urls else None
    clear_first = not args.no_clear and only_urls is None
    if only_urls is not None and not args.no_clear:
        clear_first = False

    results = run_ingestion(
        args.source_list,
        clear_corpus_first=clear_first,
        only_urls=only_urls,
    )
    write_ingestion_report(results, args.report)

    failed = sum(1 for r in results if r.status.value == "failed")
    print(f"Ingestion complete. Report: {args.report}")
    print(f"success={sum(1 for r in results if r.status.value == 'success')}, "
          f"partial={sum(1 for r in results if r.status.value == 'partial')}, "
          f"failed={failed}")
    return 0 if failed < len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
