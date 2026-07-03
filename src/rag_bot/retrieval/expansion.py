"""Query expansion via synonym dictionary (Option B hybrid)."""

import re
from dataclasses import dataclass

# User-side terms → document-side equivalents (bidirectional groups).
_SYNONYM_GROUPS: tuple[frozenset[str], ...] = (
    frozenset({"annual fee", "expense ratio", "ter", "total expense ratio"}),
    frozenset({"withdrawal", "redemption", "redeem", "exit"}),
    frozenset({"minimum holding period", "lock in", "lock-in", "lockin"}),
    frozenset({"nav", "net asset value"}),
    frozenset({"sip", "systematic investment plan"}),
    frozenset({"stp", "systematic transfer plan"}),
    frozenset({"exit load", "redemption charge", "cdsc"}),
)

_USER_SIDE_TERMS: dict[str, frozenset[str]] = {}
for group in _SYNONYM_GROUPS:
    for term in group:
        _USER_SIDE_TERMS[term.lower()] = group


@dataclass(frozen=True)
class ExpandedQuery:
    original: str
    semantic_query: str
    lexical_query: str
    lexical_expanded: bool
    added_terms: tuple[str, ...]


def _normalize_term(term: str) -> str:
    return re.sub(r"\s+", " ", term.lower().strip())


# Terms that trigger lexical (BM25) expansion — casual / user phrasing only.
_LEXICAL_EXPAND_TRIGGERS = frozenset(
    {
        "annual fee",
        "withdrawal",
        "redeem",
        "exit",
        "lock in",
        "lock-in",
        "lockin",
        "minimum holding period",
        "cdsc",
        "redemption charge",
    }
)


def _terms_in_query(query: str) -> set[str]:
    lowered = query.lower()
    found: set[str] = set()
    for term in sorted(_USER_SIDE_TERMS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(term)}\b", lowered):
            found.add(term)
    return found


def _expand_terms(matched_user_terms: set[str]) -> list[str]:
    expanded: set[str] = set()
    for term in matched_user_terms:
        group = _USER_SIDE_TERMS.get(term)
        if group:
            expanded.update(group)
    return sorted(expanded)


def expand_query(query: str) -> ExpandedQuery:
    """
    Semantic path: always merge original + synonym variants.
    Lexical path: expand only when a user-side synonym is detected.
    """
    matched = _terms_in_query(query)
    added = _expand_terms(matched)

    if added:
        semantic_query = f"{query} {' '.join(added)}".strip()
    else:
        semantic_query = query

    lexical_triggers = matched & _LEXICAL_EXPAND_TRIGGERS
    if lexical_triggers:
        lexical_query = semantic_query
        lexical_expanded = True
    else:
        lexical_query = query
        lexical_expanded = False

    return ExpandedQuery(
        original=query,
        semantic_query=semantic_query,
        lexical_query=lexical_query,
        lexical_expanded=lexical_expanded,
        added_terms=tuple(added),
    )
