"""Verify schema_migrations tracking and that re-apply is a no-op."""

import sys

from rag_bot.ingestion.db import apply_migrations, get_connection


def main() -> int:
    first = apply_migrations()
    second = apply_migrations()

    with get_connection() as conn:
        rows = conn.execute(
            "SELECT migration_name FROM schema_migrations ORDER BY migration_name"
        ).fetchall()
        child_count = conn.execute("SELECT COUNT(*) FROM child_chunks").fetchone()[0]
        parent_count = conn.execute("SELECT COUNT(*) FROM parent_chunks").fetchone()[0]
        embed_type = conn.execute(
            """
            SELECT format_type(a.atttypid, a.atttypmod)
            FROM pg_attribute a
            JOIN pg_class c ON a.attrelid = c.oid
            JOIN pg_namespace n ON c.relnamespace = n.oid
            WHERE n.nspname = 'public'
              AND c.relname = 'child_chunks'
              AND a.attname = 'embedding'
              AND NOT a.attisdropped
            """
        ).fetchone()

    print(f"first_apply_new={first}")
    print(f"second_apply_new={second}")
    print(f"schema_migrations={[r[0] for r in rows]}")
    print(f"child_chunks={child_count} parent_chunks={parent_count}")
    print(f"embedding_type={embed_type[0] if embed_type else None}")

    if second:
        print("FAIL: second apply_migrations() ran destructive migrations again")
        return 1
    if "002_embedding_768.sql" not in [r[0] for r in rows]:
        print("FAIL: 002 not recorded in schema_migrations")
        return 1
    print("OK: migrations idempotent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
