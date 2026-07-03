"""Structured refusal messages for retrieval (Phase 2)."""

from rag_bot.retrieval.schemes import (
    AMC_FACTSHEET_DIRECTORY_URL,
    CANONICAL_SCHEMES,
    SCHEME_FACTSHEET_URLS,
)


def scope_refusal_message(out_of_scope_label: str | None = None) -> str:
    scheme_list = "\n".join(f"- {name}" for name in CANONICAL_SCHEMES)
    oos_line = ""
    if out_of_scope_label:
        oos_line = (
            f"I can only answer factual questions about four ICICI Prudential schemes. "
            f"Your question appears to refer to **{out_of_scope_label}**, which is outside that scope.\n\n"
        )
    return (
        f"{oos_line}"
        "I provide factual information only — not investment advice — for these schemes:\n"
        f"{scheme_list}\n\n"
        "For official documents on other funds, see the AMC factsheet directory: "
        f"{AMC_FACTSHEET_DIRECTORY_URL}"
    )


def clarification_message(suggested_scheme: str) -> str:
    return (
        f"Did you mean **{suggested_scheme}**? "
        "Please confirm the scheme or rephrase your question so I can retrieve the right factsheet data."
    )


def thin_retrieval_message() -> str:
    return (
        "I couldn't find a clear answer to that in my sources.\n\n"
        "If your question is about one of our four covered schemes, try rephrasing "
        "(for example, use 'expense ratio' instead of 'annual fee', or name the scheme explicitly).\n\n"
        "For official scheme documents, see the AMC factsheet directory: "
        f"{AMC_FACTSHEET_DIRECTORY_URL}"
    )


def no_data_for_scheme_message(scheme_name: str) -> str:
    factsheet_url = SCHEME_FACTSHEET_URLS.get(
        scheme_name, AMC_FACTSHEET_DIRECTORY_URL
    )
    return (
        f"I don't have enough source text in the corpus to answer that for **{scheme_name}**.\n\n"
        "Please check the latest official factsheet for scheme-specific figures and rules: "
        f"{factsheet_url}"
    )
