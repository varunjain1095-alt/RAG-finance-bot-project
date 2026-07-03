"""Voyage rerank-2 with fail-open fallback to RRF order."""

import logging
import time

import httpx

from rag_bot.config import get_settings
from rag_bot.retrieval.types import ChildCandidate

logger = logging.getLogger(__name__)

VOYAGE_RERANK_URL = "https://api.voyageai.com/v1/rerank"
RERANK_MODEL = "rerank-2"
RERANK_RETRY_BACKOFF_SECONDS = 0.5


def _rerank_via_api(
    query: str,
    candidates: list[ChildCandidate],
    *,
    api_key: str,
    top_k: int,
) -> list[ChildCandidate]:
    documents = [c.text for c in candidates]
    response = httpx.post(
        VOYAGE_RERANK_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": RERANK_MODEL,
            "query": query,
            "documents": documents,
            "top_k": min(top_k, len(documents)),
        },
        timeout=60.0,
    )
    response.raise_for_status()
    data = response.json()

    ranked: list[ChildCandidate] = []
    for item in data.get("data", []):
        idx = item["index"]
        score = float(item["relevance_score"])
        candidate = candidates[idx]
        ranked.append(
            ChildCandidate(
                child_chunk_id=candidate.child_chunk_id,
                parent_chunk_id=candidate.parent_chunk_id,
                text=candidate.text,
                scheme_name=candidate.scheme_name,
                rrf_score=candidate.rrf_score,
                rerank_score=score,
                semantic_score=candidate.semantic_score,
            )
        )
    return ranked


def rerank_candidates(
    query: str,
    candidates: list[ChildCandidate],
    *,
    top_k: int = 20,
) -> tuple[list[ChildCandidate], bool, float | None]:
    """
    Rerank child candidates. Returns (ranked, rerank_used, top_score).
    On failure: fail open to RRF order with rerank_score=None.
    """
    if not candidates:
        return [], False, None

    settings = get_settings()
    if not settings.voyage_api_key:
        logger.warning("VOYAGE_API_KEY not set; skipping rerank (RRF order)")
        return candidates[:top_k], False, None

    last_error: Exception | None = None
    for attempt in range(2):
        try:
            ranked = _rerank_via_api(
                query, candidates, api_key=settings.voyage_api_key, top_k=top_k
            )
            top_score = ranked[0].rerank_score if ranked else None
            return ranked, True, top_score
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.warning("Rerank attempt %d failed: %s", attempt + 1, exc)
            if attempt == 0:
                time.sleep(RERANK_RETRY_BACKOFF_SECONDS)

    logger.error("Rerank failed after retry; falling back to RRF order: %s", last_error)
    return candidates[:top_k], False, None
