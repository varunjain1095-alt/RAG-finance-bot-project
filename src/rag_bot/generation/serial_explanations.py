"""Multi-turn serial delivery for broad conceptual explainers."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from rag_bot.generation.citations import is_broad_conceptual_question, parse_citation_block

SERIAL_RUNAWAY_WORD_LIMIT = 120
SERIAL_RUNAWAY_SENTENCE_LIMIT = 4

# Per-section "do not mention" hints to reduce scope drift into later serial sections.
_SECTION_FORBIDDEN_INSTRUCTIONS: dict[str, dict[str, str]] = {
    "mutual_funds_intro": {
        "what_it_is": (
            "Do NOT mention in this section: units, NAV, fee distribution mechanics, "
            "SEBI, Indian Trust Act, trust structure, or regulation — those belong to "
            "later sections."
        ),
        "key_mechanics": (
            "Do NOT mention in this section: diversification rationale, low-cost access "
            "benefits, trust/SEBI structure, or holding-period guidance — those belong "
            "to later sections."
        ),
        "why_invest": (
            "Do NOT mention in this section: trust structure, SEBI regulation details, "
            "or holding-period / patience guidance — those belong to later sections."
        ),
        "structure_regulation": (
            "Do NOT mention in this section: holding-period or patience guidance for "
            "equity funds — that belongs to the final section."
        ),
    },
    "sip_intro": {
        "what_it_is": (
            "Do NOT mention in this section: auto-debit mechanics, NAV purchase details, "
            "SIP types (top-up/flexible/perpetual), minimum amounts, or planning steps — "
            "those belong to later sections."
        ),
        "how_it_works": (
            "Do NOT mention in this section: SIP types, affordability features, or "
            "pre-investment planning — those belong to later sections."
        ),
        "types_of_sip": (
            "Do NOT mention in this section: minimum investment limits, contribution "
            "caps, or fund-selection planning — those belong to later sections."
        ),
        "features_and_affordability": (
            "Do NOT mention in this section: investment objective planning, fund "
            "selection, or performance review — those belong to the final section."
        ),
    },
}

def get_section_forbidden_instruction(catalog_id: str, section_id: str) -> str | None:
    return _SECTION_FORBIDDEN_INSTRUCTIONS.get(catalog_id, {}).get(section_id)


_SECTION_SCOPE_MARKERS: dict[str, dict[str, list[str]]] = {
    "mutual_funds_intro": {
        "key_mechanics": [
            r"\bnav\b",
            r"net asset value",
            r"\bunits?\b",
            r"capital gains?",
            r"proportionat",
            r"prevailing",
            r"after expenses",
        ],
        "why_invest": [
            r"diversif",
            r"low cost",
            r"capital markets?",
        ],
        "structure_regulation": [
            r"\bsebi\b",
            r"trust act",
            r"\b1882\b",
            r"regulated",
            r"trust structure",
            r"fees? (?:funds? )?(?:can )?charge",
        ],
        "important_note": [
            r"holding period",
            r"patience",
            r"18\s*[-–]?\s*24",
            r"24\s*months?",
        ],
    },
    "sip_intro": {
        "how_it_works": [
            r"auto[- ]?debit",
            r"purchase of fund units",
            r"flexibility to adjust",
        ],
        "types_of_sip": [
            r"top[- ]?up",
            r"flexible sip",
            r"perpetual",
        ],
        "features_and_affordability": [
            r"minimum investment",
            r"contribution limits?",
            r"rupee cost averaging",
        ],
        "before_you_start": [
            r"investment objective",
            r"fund selection",
            r"performance review",
            r"fund house selection",
        ],
    },
}

_AFFIRMATIVE_RE = re.compile(
    r"^(?:yes|yeah|yep|sure|ok|okay|please|go ahead|continue|tell me more|sure thing|y)\b",
    re.I,
)
_DECLINE_RE = re.compile(r"^(?:no|nope|not now|skip|stop)\b", re.I)

_TOPIC_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "mutual_funds_intro",
        re.compile(
            r"\b(?:explain\s+mutual\s+funds?|what (?:is|are) (?:a |an )?mutual\s+funds?)\b",
            re.I,
        ),
    ),
    (
        "sip_intro",
        re.compile(
            r"\b(?:"
            r"explain\s+sips?"
            r"|what (?:is|are) (?:a |an )?(?:systematic investment plan|sips?)"
            r"|systematic investment plans?"
            r"|how sip investing works"
            r"|how (?:does|do) (?:a )?sip"
            r")\b",
            re.I,
        ),
    ),
)


@dataclass(frozen=True)
class FollowUpTopic:
    label: str
    catalog_id: str | None = None
    suggested_question: str | None = None


@dataclass(frozen=True)
class SerialSection:
    id: str
    display_title: str
    prompt_instruction: str
    offer_next: str | None = None


@dataclass
class SerialCatalog:
    topic_id: str
    sections: list[SerialSection]
    follow_up_topics: list[FollowUpTopic] = field(default_factory=list)


@dataclass
class SerialExplanationState:
    topic_id: str
    anchor_question: str
    status: str  # active | completed | declined | aborted
    delivered_section_ids: list[str] = field(default_factory=list)
    retrieved_parent_ids: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> SerialExplanationState:
        return cls(
            topic_id=data["topic_id"],
            anchor_question=data["anchor_question"],
            status=data.get("status", "active"),
            delivered_section_ids=list(data.get("delivered_section_ids") or []),
            retrieved_parent_ids=list(data.get("retrieved_parent_ids") or []),
        )

    def to_dict(self) -> dict:
        return {
            "topic_id": self.topic_id,
            "anchor_question": self.anchor_question,
            "status": self.status,
            "delivered_section_ids": self.delivered_section_ids,
            "retrieved_parent_ids": self.retrieved_parent_ids,
        }


CATALOGS: dict[str, SerialCatalog] = {
    "mutual_funds_intro": SerialCatalog(
        topic_id="mutual_funds_intro",
        sections=[
            SerialSection(
                id="what_it_is",
                display_title="What it is",
                prompt_instruction=(
                    "Explain what a mutual fund is: pooled money from many investors, "
                    "professional management, and investment in equities, bonds, and other "
                    "instruments — only from retrieved sources."
                ),
                offer_next="Would you like me to run through the key mechanics?",
            ),
            SerialSection(
                id="key_mechanics",
                display_title="Key mechanics",
                prompt_instruction=(
                    "Explain units, NAV, how returns are distributed to investors after fees, "
                    "and the fee the fund charges — only from retrieved sources."
                ),
                offer_next="Would you like to hear why people invest in mutual funds?",
            ),
            SerialSection(
                id="why_invest",
                display_title="Why invest",
                prompt_instruction=(
                    "Explain why retail investors use mutual funds: diversification, "
                    "professional management, and access to capital markets at relatively "
                    "low cost — only from retrieved sources."
                ),
                offer_next=(
                    "Should I explain how mutual funds are structured and regulated in India?"
                ),
            ),
            SerialSection(
                id="structure_regulation",
                display_title="Structure and regulation",
                prompt_instruction=(
                    "Explain how mutual funds are established in India (trust structure) "
                    "and how SEBI regulates fees and expenses — only from retrieved sources."
                ),
                offer_next=(
                    "Would you like an important note on holding period for equity funds?"
                ),
            ),
            SerialSection(
                id="important_note",
                display_title="Important note",
                prompt_instruction=(
                    "Cover the patience / holding-period guidance for actively-managed equity "
                    "schemes (including any 18–24 month guidance in sources). Do not add "
                    "emphasis the source did not use — only from retrieved sources."
                ),
            ),
        ],
        follow_up_topics=[
            FollowUpTopic("How SIP investing works", catalog_id="sip_intro"),
            FollowUpTopic(
                "Equity vs debt mutual funds",
                suggested_question=(
                    "What is the difference between equity and debt mutual funds?"
                ),
            ),
            FollowUpTopic(
                "ELSS and tax-saving funds",
                suggested_question="What is ELSS and how does the lock-in work?",
            ),
        ],
    ),
    "sip_intro": SerialCatalog(
        topic_id="sip_intro",
        sections=[
            SerialSection(
                id="what_it_is",
                display_title="What it is",
                prompt_instruction=(
                    "Define Systematic Investment Plan (SIP): fixed amounts at regular "
                    "intervals, disciplined saving, and rupee cost averaging — only from "
                    "retrieved sources."
                ),
                offer_next="Would you like me to explain how SIP investing works?",
            ),
            SerialSection(
                id="how_it_works",
                display_title="How it works",
                prompt_instruction=(
                    "Explain the mechanics: auto-debit, purchase of fund units at NAV, and "
                    "flexibility to adjust contribution amounts — only from retrieved sources."
                ),
                offer_next="Would you like to hear about types of SIP?",
            ),
            SerialSection(
                id="types_of_sip",
                display_title="Types of SIP",
                prompt_instruction=(
                    "Describe types of SIP in the sources (e.g. top-up, flexible, perpetual) "
                    "— only from retrieved sources."
                ),
                offer_next="Should I cover key features and affordability of SIP?",
            ),
            SerialSection(
                id="features_and_affordability",
                display_title="Features and affordability",
                prompt_instruction=(
                    "Cover SIP features such as regular investment intervals, rupee cost "
                    "averaging, minimum investment amounts, and contribution limits — only "
                    "from retrieved sources."
                ),
                offer_next="Would you like things to know before starting a SIP?",
            ),
            SerialSection(
                id="before_you_start",
                display_title="Before you start",
                prompt_instruction=(
                    "Summarize planning points from sources: investment objective, amount "
                    "planning, fund selection, performance review, and fund house selection "
                    "— only from retrieved sources."
                ),
            ),
        ],
        follow_up_topics=[
            FollowUpTopic("How mutual funds work", catalog_id="mutual_funds_intro"),
            FollowUpTopic(
                "Minimum SIP for ICICI schemes",
                suggested_question="What is the minimum SIP for Bluechip?",
            ),
            FollowUpTopic(
                "Exit load on mutual fund investments",
                suggested_question="What is exit load on mutual funds?",
            ),
        ],
    ),
}


def _match_follow_up_catalog(question: str) -> str | None:
    """Map follow-up labels (e.g. 'How SIP investing works') to catalog ids."""
    q = question.strip().lower()
    if not q:
        return None
    for catalog in CATALOGS.values():
        for topic in catalog.follow_up_topics:
            if not topic.catalog_id:
                continue
            label = topic.label.strip().lower()
            if q == label:
                return topic.catalog_id
    return None


def detect_serial_topic(question: str) -> str | None:
    q = question.strip()
    if not q:
        return None
    for topic_id, pattern in _TOPIC_PATTERNS:
        if pattern.search(q) and topic_id in CATALOGS:
            return topic_id
    return _match_follow_up_catalog(q)


def get_catalog(topic_id: str) -> SerialCatalog | None:
    return CATALOGS.get(topic_id)


def is_decline_message(question: str) -> bool:
    return bool(_DECLINE_RE.match(question.strip()))


def _section_title_matches(question: str, section: SerialSection) -> bool:
    q = question.strip().lower()
    title = section.display_title.lower()
    slug = section.id.replace("_", " ")
    return title in q or slug in q or q == title or q == slug


def is_continuation_message(question: str, serial: SerialExplanationState) -> bool:
    if serial.status != "active":
        return False
    q = question.strip()
    if not q:
        return False
    if _AFFIRMATIVE_RE.match(q):
        return True
    catalog = get_catalog(serial.topic_id)
    if not catalog:
        return False
    delivered = set(serial.delivered_section_ids)
    for section in catalog.sections:
        if section.id in delivered:
            continue
        if _section_title_matches(q, section):
            return True
    return False


def next_section(catalog: SerialCatalog, delivered_ids: list[str]) -> SerialSection | None:
    delivered = set(delivered_ids)
    for section in catalog.sections:
        if section.id not in delivered:
            return section
    return None


def pick_follow_up_labels(
    catalog: SerialCatalog,
    completed_catalog_ids: list[str],
) -> list[str]:
    completed = set(completed_catalog_ids)
    labels: list[str] = []
    for topic in catalog.follow_up_topics:
        if topic.catalog_id and topic.catalog_id in completed:
            continue
        if topic.catalog_id == catalog.topic_id:
            continue
        labels.append(topic.label)
        if len(labels) >= 3:
            break
    return labels


def format_follow_up_closing(labels: list[str]) -> str:
    if not labels:
        return "Ask another factual question anytime."
    joined = "; ".join(labels)
    return f"Want to learn more? You might be interested in: {joined}"


def resolve_section_for_continuation(
    question: str,
    serial: SerialExplanationState,
    catalog: SerialCatalog,
) -> SerialSection | None:
    """Next section in order, or a named undelivered section if user asked by title."""
    delivered = set(serial.delivered_section_ids)
    q = question.strip()
    if not _AFFIRMATIVE_RE.match(q):
        for section in catalog.sections:
            if section.id not in delivered and _section_title_matches(q, section):
                return section
    return next_section(catalog, serial.delivered_section_ids)


def _count_sentences(text: str) -> int:
    parts = re.split(r"[.!?]+", text)
    return len([p for p in parts if p.strip()])


def is_serial_runaway_body(body: str) -> bool:
    """Stricter caps for serial sections — ignores experience level and broad-topic bonus."""
    words = len(body.split())
    sentences = _count_sentences(body)
    return (
        words > SERIAL_RUNAWAY_WORD_LIMIT
        or sentences > SERIAL_RUNAWAY_SENTENCE_LIMIT
    )


def get_expected_closing(
    section: SerialSection,
    *,
    is_last: bool,
    follow_up_labels: list[str] | None,
) -> str | None:
    if is_last and follow_up_labels:
        return format_follow_up_closing(follow_up_labels)
    return section.offer_next


def detect_scope_violations(
    catalog_id: str,
    section_id: str,
    body: str,
) -> list[str]:
    """Return ids of later sections whose topic markers appear in body."""
    catalog = CATALOGS.get(catalog_id)
    markers_map = _SECTION_SCOPE_MARKERS.get(catalog_id, {})
    if not catalog or not body.strip():
        return []
    section_ids = [s.id for s in catalog.sections]
    try:
        idx = section_ids.index(section_id)
    except ValueError:
        return []
    violated: list[str] = []
    for later_id in section_ids[idx + 1:]:
        for pattern in markers_map.get(later_id, []):
            if re.search(pattern, body, re.I):
                violated.append(later_id)
                break
    return violated


def answer_has_expected_closing(final_answer: str, expected_closing: str) -> bool:
    parsed = parse_citation_block(final_answer)
    body = parsed.body or final_answer
    return expected_closing.strip() in body


def _normalize_body_closing(body: str, expected_closing: str) -> tuple[str, str]:
    """Split explanation from closing question; append closing if absent."""
    closing = expected_closing.strip()
    text = body.strip()
    if not closing:
        return text, ""
    if not text:
        return "", closing
    if text.endswith(closing):
        prefix = text[: -len(closing)].rstrip()
        if not prefix:
            return "", closing
        if prefix.endswith("\n\n") or prefix.endswith("\n"):
            return prefix.rstrip(), closing
        explanation = re.sub(r"[.\s]+$", "", prefix).strip()
        return explanation, closing
    idx = text.rfind(closing)
    if idx >= 0:
        explanation = re.sub(r"[.\s]+$", "", text[:idx]).strip()
        return explanation, closing
    return text, closing


def _compose_serial_body(explanation: str, closing: str) -> str:
    if closing:
        if explanation.strip():
            return f"{explanation.strip()}\n\n{closing}"
        return closing
    return explanation.strip()


def rebuild_answer_with_body(final_answer: str, new_body: str) -> str:
    parsed = parse_citation_block(final_answer)
    if parsed.citation_url and parsed.citation_name and parsed.citation_date:
        date_v = parsed.last_updated or parsed.citation_date
        return (
            f"{new_body.strip()}\n\n"
            f"Last updated from sources: {date_v}\n"
            f"Source: [{parsed.citation_name}, {parsed.citation_date}]({parsed.citation_url})"
        )
    return new_body


def ensure_serial_closing(final_answer: str, expected_closing: str | None) -> str:
    """Ensure offer_next / follow-up closing is on its own paragraph before citations."""
    if not expected_closing:
        return final_answer
    parsed = parse_citation_block(final_answer)
    body = parsed.body or ""
    explanation, closing = _normalize_body_closing(body, expected_closing)
    new_body = _compose_serial_body(explanation, closing)
    if new_body == body.strip():
        return final_answer
    return rebuild_answer_with_body(final_answer, new_body)


def filter_scope_violating_sentences(
    catalog_id: str,
    section_id: str,
    body: str,
) -> str:
    """Drop sentences that match markers for later serial sections."""
    text = body.strip()
    if not text:
        return text
    sentences = re.split(r"(?<=[.!?])\s+", text)
    clean: list[str] = []
    for sentence in sentences:
        if not sentence.strip():
            continue
        if detect_scope_violations(catalog_id, section_id, sentence):
            continue
        clean.append(sentence.strip())
    if clean:
        return " ".join(clean)
    return truncate_serial_body(text)


def truncate_serial_body(body: str) -> str:
    """Trim body to serial section limits, preserving leading sentences."""
    text = body.strip()
    if not text:
        return text
    sentences = re.split(r"(?<=[.!?])\s+", text)
    kept: list[str] = []
    for sentence in sentences:
        if not sentence.strip():
            continue
        kept.append(sentence.strip())
        if len(kept) >= SERIAL_RUNAWAY_SENTENCE_LIMIT:
            break
    truncated = " ".join(kept)
    words = truncated.split()
    if len(words) > SERIAL_RUNAWAY_WORD_LIMIT:
        truncated = " ".join(words[:SERIAL_RUNAWAY_WORD_LIMIT])
        if truncated and truncated[-1] not in ".!?":
            truncated += "."
    return truncated


def build_serial_regen_instruction(
    section: SerialSection,
    catalog: SerialCatalog,
    violated_section_ids: list[str],
    expected_closing: str | None,
) -> str:
    forbidden_titles = [
        s.display_title
        for s in catalog.sections
        if s.id in violated_section_ids
    ]
    parts = [
        f"Your prior answer was wrong for serial section **{section.display_title}**.",
        f"Cover ONLY this section: {section.prompt_instruction}",
    ]
    if forbidden_titles:
        joined = ", ".join(forbidden_titles)
        parts.append(f"Do NOT mention content from: {joined}.")
    parts.append(
        f"Keep under {SERIAL_RUNAWAY_WORD_LIMIT} words and "
        f"{SERIAL_RUNAWAY_SENTENCE_LIMIT} sentences."
    )
    if expected_closing:
        parts.append(f"End with exactly: {expected_closing}")
    parts.append(
        "Include [FACTUAL] tag, Last updated from sources line, and Source line."
    )
    return " ".join(parts)


def format_serial_prompt_block(
    section: SerialSection,
    *,
    catalog_id: str,
    is_last: bool,
    follow_up_labels: list[str] | None,
) -> str:
    lines = [
        "## Serial explanation mode (overrides general answer-length guidance)",
        f"Deliver ONLY this section: **{section.display_title}**",
        section.prompt_instruction,
        "Do not cover content planned for later sections.",
    ]
    forbidden = get_section_forbidden_instruction(catalog_id, section.id)
    if forbidden:
        lines.append(forbidden)
    lines.extend(
        [
            f"Keep this section under {SERIAL_RUNAWAY_WORD_LIMIT} words and "
            f"{SERIAL_RUNAWAY_SENTENCE_LIMIT} sentences.",
            "Include `Last updated from sources:` and a `Source:` citation line for this section.",
        ]
    )
    if is_last and follow_up_labels:
        lines.append(
            f"End with exactly: {format_follow_up_closing(follow_up_labels)}"
        )
    elif section.offer_next:
        lines.append(f"End with exactly this question: {section.offer_next}")
    return "\n".join(lines)


def format_serial_facts_block(serial: SerialExplanationState) -> str:
    catalog = get_catalog(serial.topic_id)
    if not catalog:
        return ""
    delivered = ", ".join(serial.delivered_section_ids) or "none"
    pending = next_section(catalog, serial.delivered_section_ids)
    pending_label = pending.display_title if pending else "none (complete)"
    return (
        f"Serial explanation in progress: {serial.topic_id}\n"
        f"Original question: {serial.anchor_question}\n"
        f"Sections delivered: {delivered}\n"
        f"Next section if user continues: {pending_label}"
    )
