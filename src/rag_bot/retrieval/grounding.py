"""Grounding threshold evaluation (rerank score with semantic fallback)."""

from rag_bot.retrieval.types import ChildCandidate


def grounding_score_for_candidate(candidate: ChildCandidate) -> tuple[float | None, str]:
    """
    Return (score, source) for threshold comparison.
    Prefers rerank score; falls back to pre-rerank semantic similarity.
    """
    if candidate.rerank_score is not None:
        return candidate.rerank_score, "rerank"
    if candidate.semantic_score is not None:
        return candidate.semantic_score, "semantic"
    return None, "none"


def evaluate_grounding_threshold(
    ranked_candidates: list[ChildCandidate],
    threshold: float,
) -> tuple[bool, float | None, str]:
    """
    Whether the top candidate passes the hard grounding threshold.

    When rerank scores are unavailable, uses semantic similarity of the top
    ranked child. With no score at all, fails the threshold (thin retrieval).
    """
    if not ranked_candidates:
        return False, None, "none"

    score, source = grounding_score_for_candidate(ranked_candidates[0])
    if score is None:
        return False, None, "none"
    return score >= threshold, score, source
