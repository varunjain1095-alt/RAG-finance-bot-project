"""Proactive sweep: clear reignition state for sessions past inactivity threshold.

Run via cron, e.g. hourly:
  python scripts/cleanup_expired_sessions.py

Dry-run (count only):
  python scripts/cleanup_expired_sessions.py --dry-run
"""

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

from rag_bot.config import reload_settings
from rag_bot.generation.logging_db import cleanup_expired_sessions
from rag_bot.ingestion.db import apply_migrations


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Clear current_state and session_turn_embeddings for expired sessions.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report how many sessions would be cleared without writing.",
    )
    args = parser.parse_args()

    reload_settings()
    apply_migrations()
    count = cleanup_expired_sessions(dry_run=args.dry_run)
    if args.dry_run:
        print(f"expired_sessions_pending_cleanup={count}")
    else:
        print(f"expired_sessions_cleared={count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
