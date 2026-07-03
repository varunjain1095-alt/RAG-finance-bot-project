"""Parent deduplication, swap, and metadata headers."""

import json
import logging
from typing import Any

import psycopg

from rag_bot.retrieval.types import ChildCandidate, ParentContext

logger = logging.getLogger(__name__)

TOP_PARENTS = 3


def _metadata_url(metadata: Any, fallback: str) -> str:
    if isinstance(metadata, dict):
        return metadata.get("source_url") or fallback
    if isinstance(metadata, str):
        try:
            parsed = json.loads(metadata)
            return parsed.get("source_url") or fallback
        except json.JSONDecodeError:
            return fallback
    return fallback


def _format_parent_header(
    source_name: str,
    date_version: str,
    source_url: str,
) -> str:
    return f"[Source: {source_name}, {date_version} | URL: {source_url}]"


def dedupe_by_parent(
    candidates: list[ChildCandidate],
    *,
    max_parents: int = TOP_PARENTS,
) -> list[ChildCandidate]:
    seen_parents: set[str] = set()
    unique: list[ChildCandidate] = []
    for candidate in candidates:
        if candidate.parent_chunk_id in seen_parents:
            continue
        seen_parents.add(candidate.parent_chunk_id)
        unique.append(candidate)
        if len(unique) >= max_parents:
            break
    return unique


def swap_to_parents(
    conn: psycopg.Connection,
    candidates: list[ChildCandidate],
) -> list[ParentContext]:
    if not candidates:
        return []

    parent_ids = [c.parent_chunk_id for c in candidates]
    rows = conn.execute(
        """
        SELECT
            p.parent_chunk_id::text,
            p.text,
            p.metadata,
            p.scheme_name,
            d.source_name,
            d.date_version,
            d.source_url
        FROM parent_chunks p
        JOIN source_documents d ON d.document_id = p.document_id
        WHERE p.parent_chunk_id = ANY(%s::uuid[])
        """,
        (parent_ids,),
    ).fetchall()

    by_id: dict[str, tuple] = {row[0]: row for row in rows}
    parents: list[ParentContext] = []

    for candidate in candidates:
        row = by_id.get(candidate.parent_chunk_id)
        if not row:
            logger.warning("Parent chunk missing: %s", candidate.parent_chunk_id)
            continue
        (
            parent_id,
            text,
            metadata,
            scheme_name,
            source_name,
            date_version,
            doc_url,
        ) = row
        citation_url = _metadata_url(metadata, doc_url)
        header = _format_parent_header(source_name, date_version, citation_url)
        parents.append(
            ParentContext(
                parent_chunk_id=parent_id,
                text=text,
                source_name=source_name,
                date_version=date_version,
                source_url=citation_url,
                scheme_name=scheme_name,
                rerank_score=candidate.rerank_score,
                formatted_text=f"{header}\n{text}",
            )
        )
    return parents


def load_parents_by_ids(parent_ids: list[str]) -> list[ParentContext]:
    """Load parent contexts by id (for serial-explanation continuation turns)."""
    if not parent_ids:
        return []

    from rag_bot.ingestion.db import get_connection

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                p.parent_chunk_id::text,
                p.text,
                p.metadata,
                p.scheme_name,
                d.source_name,
                d.date_version,
                d.source_url
            FROM parent_chunks p
            JOIN source_documents d ON d.document_id = p.document_id
            WHERE p.parent_chunk_id = ANY(%s::uuid[])
            """,
            (parent_ids,),
        ).fetchall()

    by_id: dict[str, tuple] = {row[0]: row for row in rows}
    parents: list[ParentContext] = []
    for parent_id in parent_ids:
        row = by_id.get(parent_id)
        if not row:
            logger.warning("Parent chunk missing: %s", parent_id)
            continue
        (
            pid,
            text,
            metadata,
            scheme_name,
            source_name,
            date_version,
            doc_url,
        ) = row
        citation_url = _metadata_url(metadata, doc_url)
        header = _format_parent_header(source_name, date_version, citation_url)
        parents.append(
            ParentContext(
                parent_chunk_id=pid,
                text=text,
                source_name=source_name,
                date_version=date_version,
                source_url=citation_url,
                scheme_name=scheme_name,
                formatted_text=f"{header}\n{text}",
            )
        )
    return parents
