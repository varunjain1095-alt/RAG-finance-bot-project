"""Diagnostic SQL CLI — run pre-built queries from diagnostics/.

Examples:
  python scripts/diag.py list
  python scripts/diag.py thumbs_down_review
  python scripts/diag.py operational_health_summary --days 30
  python scripts/diag.py reranking/rerank_latency_outliers --min-latency-ms 800
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

from rag_bot.config import reload_settings
from rag_bot.operations.diagnostics import list_query_names, print_query


def main() -> int:
    parser = argparse.ArgumentParser(description="Run diagnostic SQL queries.")
    parser.add_argument(
        "query_name",
        nargs="?",
        default="list",
        help="Query name (default: list). Example: retrieval/thin_retrieval_refusals",
    )
    parser.add_argument("--days", type=int, default=7, help="Lookback window (default 7)")
    parser.add_argument("--min-latency-ms", type=int, default=600)
    parser.add_argument("--min-delta-chars", type=int, default=80)
    parser.add_argument("--limit", type=int, default=25)
    args = parser.parse_args()

    if args.query_name == "list":
        for name in list_query_names():
            print(name)
        return 0

    reload_settings()
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=args.days)
    params = {
        "start_date": start,
        "end_date": end,
        "min_latency_ms": args.min_latency_ms,
        "min_delta_chars": args.min_delta_chars,
        "limit": args.limit,
    }
    try:
        return print_query(args.query_name, params)
    except KeyError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"diag failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
