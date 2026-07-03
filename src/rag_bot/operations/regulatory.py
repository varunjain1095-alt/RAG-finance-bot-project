"""Load static regulatory templates from templates/regulatory/."""

from pathlib import Path

from rag_bot.config import PROJECT_ROOT

REGULATORY_ROOT = PROJECT_ROOT / "templates" / "regulatory"
UI_DISCLAIMER_PATH = PROJECT_ROOT / "templates" / "ui_disclaimer_snippet.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def load_mandatory_disclaimers() -> str:
    return _read(REGULATORY_ROOT / "mandatory_disclaimers.md")


def load_scope_statements() -> str:
    return _read(REGULATORY_ROOT / "scope_statements.md")


def load_authoritative_links() -> str:
    return _read(REGULATORY_ROOT / "authoritative_links.md")


def load_ui_disclaimer_snippet() -> str:
    return _read(UI_DISCLAIMER_PATH)


def extract_section(markdown: str, heading: str) -> str:
    """Return body text under a ## heading until the next ## heading."""
    lines = markdown.splitlines()
    target = heading.strip().lower()
    collecting = False
    body: list[str] = []
    for line in lines:
        if line.startswith("## "):
            if collecting:
                break
            if line[3:].strip().lower() == target:
                collecting = True
            continue
        if collecting:
            body.append(line)
    return "\n".join(body).strip()


def market_risk_disclaimer() -> str:
    text = extract_section(load_mandatory_disclaimers(), "Market risk (standard mutual fund)")
    return text or "Mutual Fund investments are subject to market risks, read all scheme related documents carefully."


def performance_reference_disclaimer() -> str:
    return extract_section(
        load_mandatory_disclaimers(),
        "Performance reference",
    )


def welcome_scope_line() -> str:
    return extract_section(load_scope_statements(), "Welcome / identity")


def amfi_investor_url() -> str:
    return "https://www.amfiindia.com/investor-corner"


def sebi_charter_url() -> str:
    return "https://investor.sebi.gov.in/"


def sebi_advisor_search_url() -> str:
    return (
        "https://www.sebi.gov.in/sebiweb/other/OtherAction.do"
        "?doRecognisedFpi=yes&intmId=14"
    )


def icici_pru_ter_disclosure_url() -> str:
    """Official ICICI Pru AMC daily/historical TER disclosure page."""
    return (
        "https://www.icicipruamc.com/about-us/financials-&-disclosures"
        "?currentTabFilter=Total+Expense+Ratio"
    )
