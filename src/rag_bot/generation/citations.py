"""Citation parsing and enforcement."""

import re
from dataclasses import dataclass

from rag_bot.config import get_settings
from rag_bot.generation.refusals import citation_fallback_refusal, clarification_followup_message
from rag_bot.generation.types import CitationFlow
from rag_bot.operations.regulatory import icici_pru_ter_disclosure_url
from rag_bot.retrieval.refusals import thin_retrieval_message
from rag_bot.retrieval.types import ParentContext

# When citation enforcement fails, do not cite parents at or below threshold + margin.
GROUNDING_FALLBACK_MARGIN = 0.05

_TAG_RE = re.compile(r"^\s*\[(?:FACTUAL|REFUSAL)\]\s*", re.I)
_CITATION_RE = re.compile(
    r"Source:\s*\[([^\]]+?),\s*([^\]]+?)\]\(([^)]+)\)\s*$",
    re.MULTILINE,
)
_LAST_UPDATED_RE = re.compile(
    r"Last updated from sources:\s*(.+?)\s*$",
    re.MULTILINE | re.I,
)
_SCHEME_NUMBER_QUERY_RE = re.compile(
    r"\b(?:expense\s+ratio|ter\b|nav\b|riskometer|benchmark)\b",
    re.I,
)
_TER_EXPENSE_QUERY_RE = re.compile(r"\b(?:expense\s+ratio|ter\b)\b", re.I)
_TER_CORPUS_URL_RE = re.compile(r"^corpus:ter-", re.I)
_COMBINED_FACTSHEET_PDF_RE = re.compile(
    r"digitalfactsheet\.icicipruamc\.com/fact/pdf/",
    re.I,
)

# Per-level backstops (context.md Answer Length Policy). Beginner needs more room
# for parenthetical definitions and structured lists; expert stays terse.
RUNAWAY_LIMITS_BY_LEVEL: dict[str, tuple[int, int]] = {
    "new": (280, 14),
    "somewhat_familiar": (250, 8),
    "expert": (200, 6),
}
# Extra headroom for broad conceptual questions at beginner level (e.g. "explain mutual funds").
BROAD_CONCEPTUAL_BONUS = (50, 4)

_BROAD_CONCEPTUAL_OPENER_RE = re.compile(
    r"^(?:explain|what (?:is|are)(?:\s+a|\s+an)?|how do(?:es)?|tell me about)\b",
    re.I,
)
_BROAD_TOPIC_RE = re.compile(
    r"\b(?:mutual\s+funds?|invest(?:ing|ment)?|equity\s+funds?|debt\s+funds?|"
    r"balanced\s+advantage|flexi?\s*cap|large\s+cap|elss|sip|nav)\b",
    re.I,
)
_NUMERIC_FACT_LOOKUP_RE = re.compile(
    r"\b(?:minimum|maximum|how much|how many|current|latest)\b|"
    r"\b(?:expense\s+ratio|exit\s+load|ter\b|lock[- ]?in)\b",
    re.I,
)


@dataclass
class CitationParseResult:
    body: str
    citation_name: str | None = None
    citation_date: str | None = None
    citation_url: str | None = None
    last_updated: str | None = None


def strip_response_tags(text: str) -> str:
    return _TAG_RE.sub("", text.strip())


def parse_citation_block(text: str) -> CitationParseResult:
    cleaned = strip_response_tags(text)
    citation_match = _CITATION_RE.search(cleaned)
    updated_match = _LAST_UPDATED_RE.search(cleaned)

    citation_url = citation_match.group(3).strip() if citation_match else None
    citation_name = citation_match.group(1).strip() if citation_match else None
    citation_date = citation_match.group(2).strip() if citation_match else None
    last_updated = updated_match.group(1).strip() if updated_match else None

    body = cleaned
    if citation_match:
        body = body[: citation_match.start()].strip()
    if updated_match and updated_match.start() < len(body):
        body = body[: updated_match.start()].strip()

    return CitationParseResult(
        body=body,
        citation_name=citation_name,
        citation_date=citation_date,
        citation_url=citation_url,
        last_updated=last_updated,
    )


def _allowed_urls(parents: list[ParentContext]) -> set[str]:
    allowed = {p.source_url for p in parents}
    for url in list(allowed):
        if is_ter_corpus_url(url):
            allowed.add(icici_pru_ter_disclosure_url())
    return allowed


def is_ter_corpus_url(url: str | None) -> bool:
    return bool(url and _TER_CORPUS_URL_RE.match(url.strip()))


def is_ter_expense_ratio_query(question: str | None) -> bool:
    if not question:
        return False
    return bool(_TER_EXPENSE_QUERY_RE.search(question))


def is_ter_parent(parent: ParentContext) -> bool:
    url = (parent.source_url or "").lower()
    if is_ter_corpus_url(parent.source_url):
        return True
    if icici_pru_ter_disclosure_url().lower() in url:
        return True
    name = (parent.source_name or "").lower()
    return "— ter " in name or " ter jun" in name


def _is_combined_factsheet_pdf(url: str) -> bool:
    return bool(_COMBINED_FACTSHEET_PDF_RE.search(url))


def _is_per_scheme_factsheet(url: str) -> bool:
    lower = url.lower()
    return (
        lower.startswith("https://")
        and "digitalfactsheet" in lower
        and not _is_combined_factsheet_pdf(url)
    )


def resolve_ter_public_citation_url(source_url: str | None) -> str:
    if is_ter_corpus_url(source_url):
        return icici_pru_ter_disclosure_url()
    return source_url or icici_pru_ter_disclosure_url()


def _format_citation(name: str, date_version: str, url: str) -> str:
    return f"Source: [{name}, {date_version}]({url})"


def _format_answer_body(
    body: str,
    name: str,
    date_version: str,
    url: str,
) -> str:
    return (
        f"{body.strip()}\n\n"
        f"Last updated from sources: {date_version}\n"
        f"{_format_citation(name, date_version, url)}"
    )


def _count_sentences(text: str) -> int:
    parts = re.split(r"[.!?]+", text)
    return len([p for p in parts if p.strip()])


def is_broad_conceptual_question(question: str | None) -> bool:
    """Broad explainers (not narrow numeric lookups) warrant relaxed beginner caps."""
    if not question:
        return False
    q = question.strip()
    if len(q.split()) > 15:
        return False
    if _NUMERIC_FACT_LOOKUP_RE.search(q):
        return False
    if not _BROAD_CONCEPTUAL_OPENER_RE.search(q):
        return False
    return bool(_BROAD_TOPIC_RE.search(q)) or q.lower().startswith("explain ")


def runaway_limits(
    experience_level: str,
    question: str | None = None,
) -> tuple[int, int]:
    word_limit, sentence_limit = RUNAWAY_LIMITS_BY_LEVEL.get(
        experience_level,
        RUNAWAY_LIMITS_BY_LEVEL["somewhat_familiar"],
    )
    if experience_level == "new" and is_broad_conceptual_question(question):
        word_limit += BROAD_CONCEPTUAL_BONUS[0]
        sentence_limit += BROAD_CONCEPTUAL_BONUS[1]
    return word_limit, sentence_limit


def is_runaway_body(
    body: str,
    *,
    experience_level: str = "somewhat_familiar",
    question: str | None = None,
) -> bool:
    word_limit, sentence_limit = runaway_limits(experience_level, question)
    words = len(body.split())
    sentences = _count_sentences(body)
    return words > word_limit or sentences > sentence_limit


def is_scheme_specific_number_query(question: str | None) -> bool:
    if not question:
        return False
    return bool(_SCHEME_NUMBER_QUERY_RE.search(question))


def pick_primary_parent(parents: list[ParentContext]) -> ParentContext:
    """Primary source for fallback citation — first reranked parent."""
    return parents[0]


def top_parent_rerank_score(parents: list[ParentContext]) -> float | None:
    scores = [p.rerank_score for p in parents if p.rerank_score is not None]
    return max(scores) if scores else None


def is_borderline_grounding(
    score: float | None,
    threshold: float,
    margin: float = GROUNDING_FALLBACK_MARGIN,
) -> bool:
    """True when retrieval confidence is too weak for a confident citation fallback."""
    if score is None:
        return True
    return score <= threshold + margin


def pick_citation_parent(
    parents: list[ParentContext],
    question: str | None = None,
) -> ParentContext:
    """Choose citation URL per hierarchy among retrieved parents."""
    if not parents:
        raise ValueError("parents required")
    if is_ter_expense_ratio_query(question):
        for parent in parents:
            if is_ter_parent(parent):
                return parent
    if is_scheme_specific_number_query(question):
        for parent in parents:
            if _is_per_scheme_factsheet(parent.source_url or ""):
                return parent
        for parent in parents:
            url = parent.source_url or ""
            if url.startswith("https://") and not _is_combined_factsheet_pdf(url):
                return parent
    return parents[0]


def apply_citation_hierarchy(
    cited_url: str,
    parents: list[ParentContext],
    question: str | None,
) -> str:
    """Remap internal corpus URLs to public sources per citation hierarchy."""
    if is_ter_corpus_url(cited_url):
        return icici_pru_ter_disclosure_url()
    if is_ter_expense_ratio_query(question):
        for parent in parents:
            if is_ter_parent(parent):
                return resolve_ter_public_citation_url(parent.source_url)
        return cited_url
    if not is_scheme_specific_number_query(question):
        return cited_url
    if cited_url.startswith("https://"):
        if _is_combined_factsheet_pdf(cited_url):
            preferred = pick_citation_parent(parents, question)
            return preferred.source_url or cited_url
        return cited_url
    preferred = pick_citation_parent(parents, question)
    pref_url = preferred.source_url or ""
    if pref_url.startswith("https://") and not _is_combined_factsheet_pdf(pref_url):
        return pref_url
    return cited_url


def enforce_citation(
    raw_llm_output: str,
    parents: list[ParentContext],
    *,
    regen_output: str | None = None,
    user_question: str | None = None,
    top_rerank_score: float | None = None,
    grounding_threshold: float | None = None,
    clarification_context: bool = False,
) -> tuple[str, CitationFlow, str | None]:
    """
    Verify citation on LLM output. Optionally apply one regeneration output.
    Returns (final_answer, citation_flow, raw_after_regen).
    """
    flow = CitationFlow()
    allowed = _allowed_urls(parents)
    primary = pick_citation_parent(parents, user_question)
    threshold = grounding_threshold if grounding_threshold is not None else (
        get_settings().grounding_threshold
    )
    resolved_score = top_rerank_score if top_rerank_score is not None else (
        top_parent_rerank_score(parents)
    )

    def _low_confidence_refusal() -> tuple[str, CitationFlow, str | None]:
        flow.final_outcome = "low_confidence_refusal"
        flow.citation_present = False
        flow.cited_url = None
        flow.url_provenance_passed = False
        flow.failure_mode = "low_confidence"
        message = (
            clarification_followup_message()
            if clarification_context
            else thin_retrieval_message()
        )
        return message, flow, regen_output

    def _should_block_confident_fallback() -> bool:
        return is_borderline_grounding(resolved_score, threshold)

    def _process(text: str, is_regen: bool) -> tuple[str | None, CitationFlow]:
        parsed = parse_citation_block(text)
        local_flow = CitationFlow()

        if not parsed.citation_url:
            local_flow.citation_present = False
            local_flow.failure_mode = "missing"
            local_flow.final_outcome = "pending"
            return None, local_flow

        local_flow.citation_present = True
        citation_url = apply_citation_hierarchy(
            parsed.citation_url, parents, user_question
        )
        local_flow.cited_url = citation_url

        if parsed.citation_url in allowed or citation_url in allowed:
            local_flow.url_provenance_passed = True
            cite_parent = next(
                (p for p in parents if p.source_url == citation_url),
                primary,
            )
            date_v = parsed.last_updated or parsed.citation_date or cite_parent.date_version
            name = parsed.citation_name or cite_parent.source_name
            answer = _format_answer_body(
                parsed.body,
                name,
                date_v,
                citation_url,
            )
            local_flow.final_outcome = "cited_after_regen" if is_regen else "cited"
            return answer, local_flow

        # URL wrong format but we could reformat if URL matches with trim?
        local_flow.url_provenance_passed = False
        local_flow.failure_mode = "invented_url"
        local_flow.final_outcome = "pending"
        return None, local_flow

    answer, attempt_flow = _process(raw_llm_output, is_regen=False)
    flow = attempt_flow

    if answer:
        return answer, flow, None

    if regen_output:
        flow.required_regeneration = True
        answer, regen_flow = _process(regen_output, is_regen=True)
        flow = regen_flow
        flow.required_regeneration = True
        if answer:
            return answer, flow, regen_output

    # Reformat if citation line exists with wrong format but URL in allowed set
    parsed = parse_citation_block(raw_llm_output)
    if parsed.citation_url and parsed.citation_url in allowed:
        flow.url_provenance_passed = True
        flow.failure_mode = "format_only"
        flow.final_outcome = "cited"
        citation_url = apply_citation_hierarchy(
            parsed.citation_url, parents, user_question
        )
        flow.cited_url = citation_url
        cite_parent = next(
            (p for p in parents if p.source_url == citation_url),
            primary,
        )
        date_v = parsed.last_updated or parsed.citation_date or cite_parent.date_version
        answer = _format_answer_body(
            parsed.body,
            parsed.citation_name or cite_parent.source_name,
            date_v,
            citation_url,
        )
        return answer, flow, None

    flow.final_outcome = "fallback_refusal"
    if _should_block_confident_fallback():
        return _low_confidence_refusal()
    flow.cited_url = primary.source_url
    flow.citation_present = True
    fallback = citation_fallback_refusal(
        primary.source_url, primary.source_name, primary.date_version
    )
    return fallback, flow, regen_output
