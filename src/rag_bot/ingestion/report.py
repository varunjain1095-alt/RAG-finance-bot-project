"""Generate ingestion_report.md from pipeline results."""

from datetime import datetime, timezone
from pathlib import Path

from rag_bot.ingestion.pipeline import DocumentResult, ParseStatus


def write_ingestion_report(
    results: list[DocumentResult],
    output_path: Path,
    *,
    known_limitations: list[str] | None = None,
) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Ingestion Report",
        "",
        f"**Generated:** {now}",
        f"**Documents processed:** {len(results)}",
        "",
        "## Summary",
        "",
        f"- success: {sum(1 for r in results if r.status == ParseStatus.SUCCESS)}",
        f"- partial: {sum(1 for r in results if r.status == ParseStatus.PARTIAL)}",
        f"- failed: {sum(1 for r in results if r.status == ParseStatus.FAILED)}",
        "",
        "## Per-document results",
        "",
        "| # | Source name | source_type | scheme | Status | Char count | Parent chunks | Child chunks | Notes |",
        "|---|-------------|-------------|--------|--------|------------|---------------|--------------|-------|",
    ]

    for i, r in enumerate(results, start=1):
        scheme = r.entry.scheme_name or "—"
        notes = r.error or "; ".join(r.warnings) if (r.error or r.warnings) else "—"
        notes = notes.replace("|", "\\|")
        lines.append(
            f"| {i} | {r.entry.source_name} | {r.entry.source_type} | {scheme} | "
            f"{r.status.value} | {r.char_count} | {r.parent_count} | {r.child_count} | {notes} |"
        )

    lines.extend(
        [
            "",
            "## URLs",
            "",
        ]
    )
    for i, r in enumerate(results, start=1):
        lines.append(f"{i}. [{r.entry.source_name}]({r.entry.source_url}) — **{r.status.value}**")

    if known_limitations:
        lines.extend(["", "## Known limitations", "",])
        for item in known_limitations:
            lines.append(f"- {item}")

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
