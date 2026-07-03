"""Load ingestion URLs from the authoritative source list markdown."""

from dataclasses import dataclass
from pathlib import Path
import re


@dataclass(frozen=True)
class SourceEntry:
    source_name: str
    source_type: str
    source_url: str
    scheme_name: str | None
    authority_level: str
    date_version: str
    local_path: str | None = None
    ter_csv_scheme: str | None = None
    structured_tabular: bool = False
    combined_factsheet: bool = False


# Ingestion corpus (matches source_list.md).
SOURCE_ENTRIES: list[SourceEntry] = [
    SourceEntry(
        "ICICI Pru Large Cap — digital factsheet",
        "factsheet",
        "https://digitalfactsheet.icicipruamc.com/fact/icici-prudential-large-cap-fund.php",
        "ICICI Prudential Large Cap Fund",
        "factsheet",
        "2026-03",
    ),
    SourceEntry(
        "AMC combined monthly factsheet PDF (Mar 2026)",
        "factsheet",
        "https://digitalfactsheet.icicipruamc.com/fact/pdf/fund-factsheet-for-march-2026.pdf",
        None,
        "factsheet",
        "2026-03",
        combined_factsheet=True,
    ),
    SourceEntry(
        "ICICI Pru Flexicap — digital factsheet",
        "factsheet",
        "https://digitalfactsheet.icicipruamc.com/fact/icici-prudential-flexicap-fund.php",
        "ICICI Prudential Flexicap Fund",
        "factsheet",
        "2026-03",
    ),
    SourceEntry(
        "ICICI Pru ELSS Tax Saver — digital factsheet",
        "factsheet",
        "https://digitalfactsheet.icicipruamc.com/fact/icici-prudential-elss-tax-saver-fund.php",
        "ICICI Prudential ELSS Tax Saver Fund",
        "factsheet",
        "2026-03",
    ),
    SourceEntry(
        "ICICI Pru Balanced Advantage — digital factsheet",
        "factsheet",
        "https://digitalfactsheet.icicipruamc.com/fact/icici-prudential-balanced-advantage-fund.php",
        "ICICI Prudential Balanced Advantage Fund",
        "factsheet",
        "2026-03",
    ),
    SourceEntry(
        "AMFI — Introduction to Mutual Funds",
        "AMFI",
        "https://www.amfiindia.com/investor/knowledge-center-info?zoneName=IntroductionMutualFunds",
        None,
        "amfi",
        "2026-06",
    ),
    SourceEntry(
        "AMFI — Investor Corner hub",
        "AMFI",
        "https://www.amfiindia.com/investor",
        None,
        "amfi",
        "2026-06",
    ),
    SourceEntry(
        "SEBI — Investor Charter",
        "SEBI",
        "https://investor.sebi.gov.in/Investor-charter.html",
        None,
        "sebi",
        "2026-06",
    ),
    SourceEntry(
        "ICICI Bank — MF FAQs (scheme & tax guidance)",
        "AMC_page",
        "corpus:icici-bank-faqs-jun2026",
        None,
        "amc_knowledge_centre",
        "2026-06",
        local_path="corpus/FAQs.md",
    ),
    SourceEntry(
        "ICICI Pru — TER Jun 2026 — Large Cap",
        "factsheet",
        "corpus:ter-jun2026-large-cap",
        "ICICI Prudential Large Cap Fund",
        "factsheet",
        "2026-06",
        local_path="corpus/TotalExpenseRatioJun2026.csv",
        ter_csv_scheme="ICICI Prudential Large Cap Fund (erstwhile Bluechip Fund)",
        structured_tabular=True,
    ),
    SourceEntry(
        "ICICI Pru — TER Jun 2026 — Flexicap",
        "factsheet",
        "corpus:ter-jun2026-flexicap",
        "ICICI Prudential Flexicap Fund",
        "factsheet",
        "2026-06",
        local_path="corpus/TotalExpenseRatioJun2026.csv",
        ter_csv_scheme="ICICI Prudential Flexicap Fund",
        structured_tabular=True,
    ),
    SourceEntry(
        "ICICI Pru — TER Jun 2026 — ELSS Tax Saver",
        "factsheet",
        "corpus:ter-jun2026-elss",
        "ICICI Prudential ELSS Tax Saver Fund",
        "factsheet",
        "2026-06",
        local_path="corpus/TotalExpenseRatioJun2026.csv",
        ter_csv_scheme="ICICI Prudential ELSS Tax Saver Fund",
        structured_tabular=True,
    ),
    SourceEntry(
        "ICICI Pru — TER Jun 2026 — Balanced Advantage",
        "factsheet",
        "corpus:ter-jun2026-balanced-advantage",
        "ICICI Prudential Balanced Advantage Fund",
        "factsheet",
        "2026-06",
        local_path="corpus/TotalExpenseRatioJun2026.csv",
        ter_csv_scheme="ICICI Prudential Balanced Advantage Fund",
        structured_tabular=True,
    ),
]


def load_sources_from_markdown(path: Path) -> list[SourceEntry]:
    """Validate authoritative markdown contains the same ingestion URLs."""
    text = path.read_text(encoding="utf-8")
    found = set(re.findall(r"https://[^\s|*)]+", text))
    found.update(re.findall(r"corpus:[^\s|*)]+", text))
    expected = {e.source_url for e in SOURCE_ENTRIES}
    missing = expected - found
    if missing:
        raise ValueError(f"Source list missing expected URLs: {sorted(missing)}")
    return list(SOURCE_ENTRIES)
