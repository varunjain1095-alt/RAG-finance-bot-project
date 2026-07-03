"""Print operational health summary as markdown."""

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

from rag_bot.config import reload_settings
from rag_bot.operations.diagnostics import run_query


def main() -> int:
    parser = argparse.ArgumentParser(description="Operational health markdown report.")
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()

    reload_settings()
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=args.days)
    columns, rows = run_query(
        "operational_health_summary",
        {"start_date": start, "end_date": end},
    )
    if not rows:
        print("No query traffic in window.")
        return 0

    row = rows[0]
    print(f"# Operational health ({args.days}d window)")
    print()
    print(f"Window: {start.isoformat()} → {end.isoformat()}")
    print()
    for col, val in zip(columns, row, strict=True):
        print(f"- **{col}**: {val}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
