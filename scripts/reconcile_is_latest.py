"""Reconcile is_latest flags: one latest row per source_url (distinct URLs never compete)."""

import sys

from rag_bot.ingestion.db import get_connection, reconcile_is_latest_flags


def main() -> int:
    with get_connection() as conn:
        groups = reconcile_is_latest_flags(conn)
        conn.commit()
    print(f"is_latest_true_count={groups}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
