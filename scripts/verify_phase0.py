"""Phase 0 acceptance checks: Postgres connection and pgvector extension."""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load project-root .env before any rag_bot.config import (cwd-independent).
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env", override=True)

import psycopg

from rag_bot.config import get_settings, reload_settings


def _database_url() -> str:
    """Use DATABASE_URL from environment after load_dotenv; align Settings with os.environ."""
    reload_settings()
    env_url = os.environ.get("DATABASE_URL", "").strip()
    settings_url = get_settings().database_url.strip()
    if env_url and env_url != settings_url:
        raise RuntimeError(
            "DATABASE_URL mismatch between os.environ and Settings — "
            f"env={env_url!r} settings={settings_url!r}"
        )
    return env_url or settings_url


def main() -> int:
    errors: list[str] = []

    try:
        database_url = _database_url()
        with psycopg.connect(database_url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.execute(
                    "SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'vector')"
                )
                has_vector = cur.fetchone()[0]
                if not has_vector:
                    errors.append("pgvector extension is not installed")
                cur.execute(
                    "SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname = 'metabase_readonly')"
                )
                has_readonly = cur.fetchone()[0]
                if not has_readonly:
                    errors.append("metabase_readonly role missing")
    except Exception as exc:  # noqa: BLE001 — CLI diagnostic script
        errors.append(f"database connection failed: {exc}")

    if errors:
        for err in errors:
            print(f"FAIL: {err}")
        return 1

    print("PASS: Postgres connected, pgvector enabled, metabase_readonly role present")
    return 0


if __name__ == "__main__":
    sys.exit(main())
