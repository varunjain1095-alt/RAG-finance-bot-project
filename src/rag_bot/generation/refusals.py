"""Static refusal templates for filter short-circuits."""

from rag_bot.operations.regulatory import (
    amfi_investor_url,
    market_risk_disclaimer,
    performance_reference_disclaimer,
    sebi_charter_url,
)
from rag_bot.retrieval.schemes import (
    AMC_FACTSHEET_DIRECTORY_URL,
    CANONICAL_SCHEMES,
    SCHEME_FACTSHEET_URLS,
    detect_scheme,
)

AMFI_INVESTOR_URL = amfi_investor_url()
SEBI_CHARTER_URL = sebi_charter_url()


def pii_refusal_message(pii_type: str) -> str:
    label = pii_type.replace("_", " ")
    return (
        f"I noticed your message may contain {label}. "
        "For your privacy and safety, I can't process queries containing personal information. "
        "Please rephrase your question without including PAN, Aadhaar, account numbers, "
        "OTP codes, email addresses, or phone numbers."
    )


def investment_recommendation_refusal_message() -> str:
    return (
        "The bot does not provide advice on which specific funds you should purchase. "
        "For investment decisions, consult a SEBI-registered investment advisor.\n\n"
        f"Investor education: {AMFI_INVESTOR_URL}\n"
        f"SEBI investor charter: {SEBI_CHARTER_URL}"
    )


def out_of_scope_refusal_message(user_question: str) -> str:
    schemes = "\n".join(f"- {s}" for s in CANONICAL_SCHEMES)
    return (
        f"You asked: \"{user_question[:200]}\"\n\n"
        "I provide factual information about ICICI Prudential mutual fund schemes — "
        "not investment advice, portfolio recommendations, or predictions.\n\n"
        f"Covered schemes:\n{schemes}\n\n"
        "For general investor education, see AMFI: " + AMFI_INVESTOR_URL + "\n"
        "For investor rights and grievances, see SEBI: " + SEBI_CHARTER_URL + "\n\n"
        "You can ask a factual version (for example, expense ratio, exit load, or lock-in rules)."
    )


def no_performance_refusal_message(user_question: str) -> str:
    detection = detect_scheme(user_question)
    scheme = detection.scheme_name
    if scheme and scheme in SCHEME_FACTSHEET_URLS:
        factsheet_url = SCHEME_FACTSHEET_URLS[scheme]
        scheme_line = f"**{scheme}** factsheet: {factsheet_url}"
    else:
        factsheet_url = AMC_FACTSHEET_DIRECTORY_URL
        scheme_line = f"AMC factsheet directory: {factsheet_url}"

    return (
        f"You asked about performance or returns — I don't quote or compute performance figures.\n\n"
        f"Official scheme documents are here: {scheme_line}\n\n"
        f"{performance_reference_disclaimer()}\n"
        f"{market_risk_disclaimer()}\n\n"
        "I can share non-performance facts such as expense ratio, exit load, fund category, "
        "minimum SIP, or lock-in period if you ask specifically."
    )


def runaway_fallback_message(factsheet_url: str, date_version: str) -> str:
    return (
        "I have detailed information about this, but the full answer would be unusually long. "
        f"For complete details, see the official factsheet: {factsheet_url}\n\n"
        f"Last updated from sources: {date_version}"
    )


def citation_fallback_refusal(primary_url: str, source_name: str, date_version: str) -> str:
    return (
        "I found relevant information but could not format a verified citation from my sources. "
        f"Please refer to the official source directly: {primary_url}\n\n"
        f"Last updated from sources: {date_version}\n"
        f"Source: [{source_name}, {date_version}]({primary_url})"
    )


def clarification_followup_message() -> str:
    return (
        "I'm not sure which part is unclear. "
        "Can you tell me what's confusing — for example a term I used, "
        "or the step you want me to walk through again?"
    )
