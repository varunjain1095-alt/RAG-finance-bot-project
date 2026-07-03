"""Run parameterized diagnostic SQL against query_logs."""

from __future__ import annotations

import csv
import io
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from rag_bot.config import PROJECT_ROOT
from rag_bot.ingestion.db import get_connection

DIAGNOSTICS_ROOT = PROJECT_ROOT / "diagnostics"

DEFAULT_PARAMS: dict[str, Any] = {
    "min_latency_ms": 600,
    "min_delta_chars": 80,
    "limit": 25,
}


def discover_queries() -> dict[str, Path]:
    """Map query name (path without .sql) to file path."""
    queries: dict[str, Path] = {}
    for path in sorted(DIAGNOSTICS_ROOT.rglob("*.sql")):
        rel = path.relative_to(DIAGNOSTICS_ROOT)
        name = str(rel.with_suffix("")).replace("\\", "/")
        queries[name] = path
    return queries


def default_time_window(days: int = 7) -> dict[str, datetime]:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    return {"start_date": start, "end_date": end}


def run_query(
    name: str,
    params: dict[str, Any] | None = None,
) -> tuple[list[str], list[tuple[Any, ...]]]:
    queries = discover_queries()
    if name not in queries:
        raise KeyError(f"Unknown diagnostic query: {name}")

    sql = queries[name].read_text(encoding="utf-8")
    merged = {**default_time_window(), **DEFAULT_PARAMS}
    if params:
        merged.update(params)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, merged)
            columns = [desc[0] for desc in cur.description or []]
            rows = cur.fetchall()
    return columns, rows


def format_results(columns: list[str], rows: list[tuple[Any, ...]]) -> str:
    if not columns:
        return "No columns returned."
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(columns)
    for row in rows:
        writer.writerow(row)
    return output.getvalue().strip()


def print_query(name: str, params: dict[str, Any] | None = None) -> int:
    columns, rows = run_query(name, params)
    print(format_results(columns, rows))
    return 0


def list_query_names() -> list[str]:
    return sorted(discover_queries().keys())
