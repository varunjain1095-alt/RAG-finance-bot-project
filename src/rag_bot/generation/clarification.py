"""Clarification / confusion intent — re-explain prior answer, not fresh retrieval."""

from __future__ import annotations

import re

from rag_bot.generation.serial_explanations import (
    CATALOGS,
    SerialCatalog,
    SerialExplanationState,
    SerialSection,
)

_CLARIFICATION_RE = re.compile(
    r"^(?:i\s+)?(?:don'?t|do\s+not)\s+(?:get|understand|follow)(?:\s+it)?\b|"
    r"^(?:i'?m\s+)?confused\b|"
    r"^what\s+does\s+that\s+mean\b|"
    r"^can\s+you\s+explain\s+(?:that|this)\s+(?:again|more\s+simply)?\b|"
    r"^(?:still\s+)?(?:confused|lost)\b|"
    r"^that\s+doesn'?t\s+make\s+sense\b",
    re.I,
)


def is_clarification_request(question: str) -> bool:
    q = question.strip()
    if not q or len(q.split()) > 20:
        return False
    return bool(_CLARIFICATION_RE.search(q))


def resolve_serial_section_for_clarification(
    serial: SerialExplanationState,
    catalog: SerialCatalog,
) -> SerialSection:
    """Re-explain the section the user most recently received."""
    if serial.delivered_section_ids:
        last_id = serial.delivered_section_ids[-1]
        for section in catalog.sections:
            if section.id == last_id:
                return section
    return catalog.sections[0]


def format_clarification_prompt_block(
    section: SerialSection,
    *,
    user_message: str,
    expected_closing: str | None,
) -> str:
    lines = [
        "## Clarification mode (overrides general answer-length guidance)",
        "The user did not understand your previous explanation.",
        f"Re-explain ONLY this section in simpler plain language: **{section.display_title}**",
        section.prompt_instruction,
        "Use shorter sentences and everyday words; do not introduce new topics.",
        "Do not cover content planned for later sections.",
        "Keep under 120 words and 4 sentences.",
        "Include `Last updated from sources:` and a `Source:` citation line.",
    ]
    if expected_closing:
        lines.append(f"End with exactly: {expected_closing}")
    lines.append(f"User confusion signal: {user_message.strip()}")
    return "\n".join(lines)


def format_non_serial_clarification_block(
    prior_question: str,
    prior_answer: str,
) -> str:
    return (
        "## Clarification mode\n"
        "The user did not understand your previous answer. "
        "Re-explain the factual content below in simpler plain language — "
        "shorter sentences, everyday words, no new topics.\n"
        f"Original question: {prior_question.strip()}\n"
        f"Previous answer to simplify:\n{prior_answer.strip()}\n"
        "Include `Last updated from sources:` and a `Source:` citation line."
    )


def get_catalog_for_serial(serial: SerialExplanationState) -> SerialCatalog | None:
    return CATALOGS.get(serial.topic_id)
