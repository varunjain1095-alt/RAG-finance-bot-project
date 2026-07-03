"""Hard-coded scheme detection — no LLM."""

import re
from dataclasses import dataclass
from enum import Enum


LARGE_CAP = "ICICI Prudential Large Cap Fund"
FLEXICAP = "ICICI Prudential Flexicap Fund"
ELSS = "ICICI Prudential ELSS Tax Saver Fund"
BALANCED_ADVANTAGE = "ICICI Prudential Balanced Advantage Fund"

CANONICAL_SCHEMES: tuple[str, ...] = (
    LARGE_CAP,
    FLEXICAP,
    ELSS,
    BALANCED_ADVANTAGE,
)

AMC_FACTSHEET_DIRECTORY_URL = (
    "https://www.icicipruamc.com/mutual-funds"
)

SCHEME_FACTSHEET_URLS: dict[str, str] = {
    LARGE_CAP: "https://digitalfactsheet.icicipruamc.com/fact/icici-prudential-large-cap-fund.php",
    FLEXICAP: "https://digitalfactsheet.icicipruamc.com/fact/icici-prudential-flexicap-fund.php",
    ELSS: "https://digitalfactsheet.icicipruamc.com/fact/icici-prudential-elss-tax-saver-fund.php",
    BALANCED_ADVANTAGE: (
        "https://digitalfactsheet.icicipruamc.com/fact/icici-prudential-balanced-advantage-fund.php"
    ),
}

# Longer / more specific patterns first.
_IN_SCOPE_VARIANTS: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(pattern, re.IGNORECASE), scheme)
    for pattern, scheme in [
        (r"icici\s+prudential\s+large\s+cap(?:\s+fund)?", LARGE_CAP),
        (r"erstwhile\s+blue\s*chip", LARGE_CAP),
        (r"large\s+cap(?:\s+fund)?", LARGE_CAP),
        (r"icici\s+prudential\s+flexi\s*cap(?:\s+fund)?", FLEXICAP),
        (r"flexi\s*cap(?:\s+fund)?", FLEXICAP),
        (r"icici\s+prudential\s+elss", ELSS),
        (r"elss(?:\s+tax\s+saver)?(?:\s+fund)?", ELSS),
        (r"tax\s+saver(?:\s+fund)?", ELSS),
        (r"icici\s+prudential\s+balanced\s+advantage", BALANCED_ADVANTAGE),
        (r"balanced\s+advantage(?:\s+fund)?", BALANCED_ADVANTAGE),
        (r"\bblue\s*chip(?:\s+fund)?\b", LARGE_CAP),
    ]
)

_OUT_OF_SCOPE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(pattern, re.IGNORECASE), label)
    for pattern, label in [
        (r"\bus\s+blue\s*chip", "US Bluechip Equity Fund"),
        (r"\bhdfc\b", "HDFC"),
        (r"\bnippon\b", "Nippon India Mutual Fund"),
        (r"\bsbi\s+(?:mutual\s+)?fund", "SBI Mutual Fund"),
        (r"\baxis\s+(?:mutual\s+)?fund", "Axis Mutual Fund"),
        (r"\bkotak\s+(?:mutual\s+)?fund", "Kotak Mutual Fund"),
    ]
)

# Plausible in-scope typos → clarification (not silent wrong filter).
_CLARIFICATION_TYPOS: dict[str, str] = {
    "bluchip": LARGE_CAP,
    "bluechp": LARGE_CAP,
    "bluechpi": LARGE_CAP,
    "flexcap": FLEXICAP,
    "flexicp": FLEXICAP,
    "elsss": ELSS,
    "balanced advantge": BALANCED_ADVANTAGE,
}


class SchemeDetectionKind(str, Enum):
    NO_SCHEME = "no_scheme"
    MATCHED = "matched"
    OUT_OF_SCOPE = "out_of_scope"
    CLARIFICATION = "clarification"


@dataclass(frozen=True)
class SchemeDetection:
    kind: SchemeDetectionKind
    scheme_name: str | None = None
    out_of_scope_label: str | None = None
    clarification_scheme: str | None = None


def _find_in_scope_scheme(query: str) -> str | None:
    for pattern, scheme in _IN_SCOPE_VARIANTS:
        if pattern.search(query):
            return scheme
    return None


def _find_out_of_scope(query: str) -> str | None:
    for pattern, label in _OUT_OF_SCOPE_PATTERNS:
        if pattern.search(query):
            return label
    return None


def _find_clarification_typo(query: str) -> str | None:
    lowered = query.lower()
    for typo, scheme in _CLARIFICATION_TYPOS.items():
        if typo in lowered:
            return scheme
    return None


def detect_scheme(query: str) -> SchemeDetection:
    """Detect scheme filter from query text. No LLM."""
    in_scope = _find_in_scope_scheme(query)
    out_of_scope = _find_out_of_scope(query)

    if out_of_scope and in_scope:
        return SchemeDetection(
            kind=SchemeDetectionKind.OUT_OF_SCOPE,
            out_of_scope_label=out_of_scope,
            scheme_name=in_scope,
        )

    if out_of_scope:
        return SchemeDetection(
            kind=SchemeDetectionKind.OUT_OF_SCOPE,
            out_of_scope_label=out_of_scope,
        )

    if in_scope:
        return SchemeDetection(kind=SchemeDetectionKind.MATCHED, scheme_name=in_scope)

    clarification_scheme = _find_clarification_typo(query)
    if clarification_scheme:
        return SchemeDetection(
            kind=SchemeDetectionKind.CLARIFICATION,
            clarification_scheme=clarification_scheme,
        )

    return SchemeDetection(kind=SchemeDetectionKind.NO_SCHEME)
