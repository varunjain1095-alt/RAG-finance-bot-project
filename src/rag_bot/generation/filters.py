"""Pre-retrieval input filters: PII, out-of-scope, no-performance."""

import re

from rag_bot.generation.types import FilterResult, FilterResultKind

_PAN_RE = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b", re.IGNORECASE)
_AADHAAR_RE = re.compile(
    r"\b\d{4}[\s-]\d{4}[\s-]\d{4}\b"
    r"|\baadhaar\s*(?:is|no|number|#)?\s*[:#]?\s*\d{12}\b",
    re.I,
)
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE_RE = re.compile(
    r"(?:\+91[\s-]?)?[6-9]\d{9}\b|(?:\+91[\s-]?)?\d{10}\b"
)
_OTP_RE = re.compile(r"\b(?:otp|one[- ]time password)\s*(?:is|:)?\s*\d{4,8}\b", re.I)
_ACCOUNT_RE = re.compile(
    r"\b(?:account|acct|a/c)\s*(?:no|number|#)?\s*[:#]?\s*\d{9,18}\b",
    re.I,
)

_OOS_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.I)
    for p in [
        r"\bshould\s+i\b",
        r"\brecommend\b",
        r"\bgood\s+investment\b",
        r"\bis\s+this\s+scheme\s+right\s+for\s+me\b",
        r"\bwhich\s+fund\s+is\s+better\b",
        r"\bwill\s+the\s+market\b",
        r"\bwhere\s+should\s+i\s+invest\b",
        r"\brebalance\s+my\s+portfolio\b",
        r"\bhow\s+should\s+i\s+save\s+tax\b",
        r"\bwhat\s+%\s+should\s+be\s+in\s+equity\b",
        r"\bwill\s+this\s+fund\s+go\s+up\b",
        r"\bi\s+have\s+\d+\s*(?:lakhs?|lacs?|crores?).{0,30}where\s+should\s+i\s+invest",
        r"\bbest\b.*\bmutual\s+funds?\b.*\binvest",
        r"\bbest\b.*\b(?:fund|mutual\s+fund)\b.*\binvest",
    ]
)

_INVESTMENT_RECOMMENDATION_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.I)
    for p in [
        r"\bbest\b.*\bmutual\s+funds?\b.*\binvest",
        r"\bbest\b.*\b(?:fund|mutual\s+fund)\b.*\binvest",
    ]
)

_PERFORMANCE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.I)
    for p in [
        r"\b(?:annual|average)\s+return\b",
        r"\b\d+\s*-?\s*year\s+return\b",
        r"\bcagr\b",
        r"\bperformance\b",
        r"\byield\b",
        r"\bgain\b",
        r"\bannualized\b",
        r"\balpha\b",
        r"\bbeta\b",
        r"\boutperform\b",
        r"\bhow\s+much\s+did\b.*\bearn\b",
        r"\bcompare\s+returns\b",
        r"\bwhat\s+return\s+will\s+i\s+get\b",
        r"\bhow\s+did\s+the\s+fund\s+perform\b",
        r"\bhow\s+did\b.*\bperform(?:ed|ance)?\b",
        r"\bperform(?:ed|ance)?\b",
        r"\breturns?\s+of\b",
        r"\breturns?\s+for\b",
    ]
)

_FACTUAL_INDICATORS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.I)
    for p in [
        r"\bexpense\s+ratio\b",
        r"\bexit\s+load\b",
        r"\bter\b",
        r"\block[- ]?in\b",
        r"\bminimum\s+sip\b",
        r"\bnav\b",
        r"\briskometer\b",
        r"\bbenchmark\b",
        r"\btax\s+benefit\b",
        r"\b80c\b",
        r"\bobjective\b",
        r"\bwhat\s+is\s+elss\b",
    ]
)


def detect_pii(text: str) -> str | None:
    if _PAN_RE.search(text):
        return "pan"
    if _AADHAAR_RE.search(text):
        return "aadhaar"
    if _EMAIL_RE.search(text):
        return "email"
    if _ACCOUNT_RE.search(text):
        return "account_number"
    if _OTP_RE.search(text):
        return "otp"
    if _PHONE_RE.search(text):
        return "phone"
    return None


def _matches_any(text: str, patterns: tuple[re.Pattern[str], ...]) -> bool:
    return any(p.search(text) for p in patterns)


def is_mixed_factual_advisory(text: str) -> bool:
    return _matches_any(text, _OOS_PATTERNS) and _matches_any(text, _FACTUAL_INDICATORS)


def is_investment_recommendation_request(text: str) -> bool:
    return _matches_any(text, _INVESTMENT_RECOMMENDATION_PATTERNS)


def run_input_filters(text: str) -> FilterResult:
    pii_type = detect_pii(text)
    if pii_type:
        return FilterResult(kind=FilterResultKind.PII, pii_type=pii_type)

    if is_mixed_factual_advisory(text):
        return FilterResult(kind=FilterResultKind.MIXED, detection_method="rule")

    if _matches_any(text, _OOS_PATTERNS):
        return FilterResult(kind=FilterResultKind.OUT_OF_SCOPE, detection_method="rule")

    if _matches_any(text, _PERFORMANCE_PATTERNS):
        return FilterResult(kind=FilterResultKind.NO_PERFORMANCE, detection_method="rule")

    return FilterResult(kind=FilterResultKind.PASS)
