"""Hybrid retrieval: semantic + lexical + RRF fusion."""

import logging
from typing import Any

import psycopg

from rag_bot.retrieval.filters import latest_source_document_join
from rag_bot.retrieval.types import ChildCandidate

logger = logging.getLogger(__name__)

RRF_K = 60
DEFAULT_TOP_K = 20


def _scheme_filter_sql(scheme_name: str | None, child_alias: str = "c") -> tuple[str, list[Any]]:
    if scheme_name:
        return f"AND {child_alias}.scheme_name = %s", [scheme_name]
    return "", []


def semantic_search(
    conn: psycopg.Connection,
    query_embedding: list[float],
    *,
    scheme_name: str | None = None,
    top_k: int = DEFAULT_TOP_K,
) -> list[tuple[str, str, str, str | None, float | None]]:
    """Returns rows: child_chunk_id, parent_chunk_id, text, scheme_name."""
    scheme_sql, scheme_params = _scheme_filter_sql(scheme_name)
    join_sql = latest_source_document_join()
    sql = f"""
        SELECT c.child_chunk_id::text, c.parent_chunk_id::text, c.text, c.scheme_name,
               (1 - (c.embedding <=> %s::vector))::double precision AS similarity
        FROM child_chunks c
        {join_sql}
        WHERE c.embedding IS NOT NULL
        {scheme_sql}
        ORDER BY c.embedding <=> %s::vector
        LIMIT %s
    """
    params: list[Any] = [query_embedding, *scheme_params, query_embedding, top_k]
    return conn.execute(sql, params).fetchall()


def lexical_search(
    conn: psycopg.Connection,
    lexical_query: str,
    *,
    scheme_name: str | None = None,
    top_k: int = DEFAULT_TOP_K,
) -> list[tuple[str, str, str, str | None]]:
    scheme_sql, scheme_params = _scheme_filter_sql(scheme_name)
    join_sql = latest_source_document_join()
    sql = f"""
        SELECT c.child_chunk_id::text, c.parent_chunk_id::text, c.text, c.scheme_name
        FROM child_chunks c
        {join_sql}
        WHERE c.search_tsv @@ plainto_tsquery('english', %s)
        {scheme_sql}
        ORDER BY ts_rank(c.search_tsv, plainto_tsquery('english', %s)) DESC
        LIMIT %s
    """
    params: list[Any] = [lexical_query, *scheme_params, lexical_query, top_k]
    return conn.execute(sql, params).fetchall()


def rrf_fuse(
    ranked_lists: list[list[str]],
    *,
    k: int = RRF_K,
) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, child_id in enumerate(ranked, start=1):
            scores[child_id] = scores.get(child_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda item: -item[1])


def hybrid_search(
    conn: psycopg.Connection,
    query_embedding: list[float],
    lexical_query: str,
    *,
    scheme_name: str | None = None,
    top_k: int = DEFAULT_TOP_K,
) -> list[ChildCandidate]:
    semantic_rows = semantic_search(
        conn, query_embedding, scheme_name=scheme_name, top_k=top_k
    )
    lexical_rows = lexical_search(
        conn, lexical_query, scheme_name=scheme_name, top_k=top_k
    )

    child_meta: dict[str, tuple[str, str, str | None, float | None]] = {}
    semantic_ids: list[str] = []
    lexical_ids: list[str] = []

    for child_id, parent_id, text, scheme, similarity in semantic_rows:
        child_meta[child_id] = (parent_id, text, scheme, float(similarity))
        semantic_ids.append(child_id)

    for child_id, parent_id, text, scheme in lexical_rows:
        if child_id not in child_meta:
            child_meta[child_id] = (parent_id, text, scheme, None)
        lexical_ids.append(child_id)

    fused = rrf_fuse([semantic_ids, lexical_ids], k=RRF_K)[:top_k]

    candidates: list[ChildCandidate] = []
    for child_id, score in fused:
        parent_id, text, scheme, semantic_score = child_meta[child_id]
        candidates.append(
            ChildCandidate(
                child_chunk_id=child_id,
                parent_chunk_id=parent_id,
                text=text,
                scheme_name=scheme,
                rrf_score=score,
                semantic_score=semantic_score,
            )
        )
    return candidates
