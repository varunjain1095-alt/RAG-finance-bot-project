"""Parse ICICI Prudential TER CSV — one markdown block per scheme (latest date)."""

import csv
from datetime import datetime
from pathlib import Path

# Canonical scheme_name (source list) → exact CSV Scheme Name column value.
IN_SCOPE_TER_SCHEMES: dict[str, str] = {
    "ICICI Prudential Large Cap Fund": "ICICI Prudential Large Cap Fund (erstwhile Bluechip Fund)",
    "ICICI Prudential Flexicap Fund": "ICICI Prudential Flexicap Fund",
    "ICICI Prudential ELSS Tax Saver Fund": "ICICI Prudential ELSS Tax Saver Fund",
    "ICICI Prudential Balanced Advantage Fund": "ICICI Prudential Balanced Advantage Fund",
}

_COLS = [
    "scheme_name",
    "date",
    "regular_ber",
    "regular_brokerage",
    "regular_transaction",
    "regular_statutory",
    "regular_ter",
    "direct_ber",
    "direct_brokerage",
    "direct_transaction",
    "direct_statutory",
    "direct_ter",
]


def _parse_date(value: str) -> datetime:
    return datetime.strptime(value.strip(), "%d/%m/%Y")


def _row_dict(row: list[str]) -> dict[str, str] | None:
    if len(row) < 12:
        return None
    scheme = row[0].strip()
    if not scheme or scheme.startswith("Total Expense"):
        return None
    return {
        "scheme_name": scheme,
        "date": row[1].strip(),
        "regular_ber": row[2].strip(),
        "regular_brokerage": row[3].strip(),
        "regular_transaction": row[4].strip(),
        "regular_statutory": row[5].strip(),
        "regular_ter": row[6].strip(),
        "direct_ber": row[7].strip(),
        "direct_brokerage": row[8].strip(),
        "direct_transaction": row[9].strip(),
        "direct_statutory": row[10].strip(),
        "direct_ter": row[11].strip(),
    }


def _format_plan(label: str, ber: str, brokerage: str, txn: str, statutory: str, ter: str) -> str:
    if ter.upper() == "NA" or not ter:
        return f"### {label}\nNot applicable for this scheme.\n"
    return (
        f"### {label}\n"
        f"- Base Expense Ratio (BER): {ber}\n"
        f"- Brokerage cost: {brokerage}\n"
        f"- Transaction cost: {txn}\n"
        f"- Statutory levies (incl. GST): {statutory}\n"
        f"- **Total TER: {ter}**\n"
    )


def ter_markdown_for_scheme(csv_path: Path, csv_scheme_name: str) -> tuple[str, str]:
    """Return (as_of_date DD/MM/YYYY, markdown) for the latest row of csv_scheme_name."""
    latest: dict[str, str] | None = None
    latest_dt: datetime | None = None

    with csv_path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh)
        for _ in range(2):
            next(reader, None)
        for row in reader:
            parsed = _row_dict(row)
            if not parsed or parsed["scheme_name"] != csv_scheme_name:
                continue
            dt = _parse_date(parsed["date"])
            if latest_dt is None or dt > latest_dt:
                latest_dt = dt
                latest = parsed

    if not latest:
        raise ValueError(f"No TER rows found for CSV scheme: {csv_scheme_name}")

    canonical = next(
        (k for k, v in IN_SCOPE_TER_SCHEMES.items() if v == csv_scheme_name),
        csv_scheme_name,
    )
    as_of = latest["date"]
    body = (
        f"# Total Expense Ratio — {canonical}\n\n"
        f"Source: ICICI Prudential AMC daily TER disclosure. As of **{as_of}** (latest in June 2026 file).\n\n"
        + _format_plan(
            "Regular Plan",
            latest["regular_ber"],
            latest["regular_brokerage"],
            latest["regular_transaction"],
            latest["regular_statutory"],
            latest["regular_ter"],
        )
        + "\n"
        + _format_plan(
            "Direct Plan",
            latest["direct_ber"],
            latest["direct_brokerage"],
            latest["direct_transaction"],
            latest["direct_statutory"],
            latest["direct_ter"],
        )
    )
    return as_of, body


def ter_parent_chunk(csv_path: Path, csv_scheme_name: str):
    """Single parent-sized TER summary (one chunk per scheme, latest values)."""
    from rag_bot.ingestion.chunking import ChunkUnit, ParentChunkData
    from rag_bot.operations.regulatory import icici_pru_ter_disclosure_url

    as_of, markdown = ter_markdown_for_scheme(csv_path, csv_scheme_name)
    heading = f"Total Expense Ratio as of {as_of}"
    return ParentChunkData(
        text=markdown.strip(),
        section_heading=heading,
        children=[ChunkUnit(text=markdown.strip(), section_heading=heading)],
        citation_url=icici_pru_ter_disclosure_url(),
        scheme_name=next(
            (k for k, v in IN_SCOPE_TER_SCHEMES.items() if v == csv_scheme_name),
            None,
        ),
    )
