"""Session and query logging."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg

from rag_bot.config import get_settings
from rag_bot.generation.session_state import SessionState
from rag_bot.generation.types import CitationFlow, GenerationTimings
from rag_bot.ingestion.db import get_connection

VALID_EXPERIENCE_LEVELS = frozenset({"new", "somewhat_familiar", "expert"})
DEFAULT_EXPERIENCE_LEVEL = "somewhat_familiar"


class SessionExpiredError(ValueError):
    """Raised when a session exceeded the inactivity window."""


def create_session(
    *,
    experience_level: str | None = None,
    user_identifier: str | None = None,
) -> uuid.UUID:
    level = experience_level or DEFAULT_EXPERIENCE_LEVEL
    if level not in VALID_EXPERIENCE_LEVELS:
        level = DEFAULT_EXPERIENCE_LEVEL
    session_id = uuid.uuid4()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO sessions (session_id, user_identifier, experience_level, current_state)
            VALUES (%s, %s, %s, '{}'::jsonb)
            """,
            (session_id, user_identifier, level),
        )
        conn.commit()
    return session_id


def _session_inactivity_cutoff() -> datetime:
    hours = get_settings().session_inactivity_hours
    return datetime.now(timezone.utc) - timedelta(hours=hours)


def clear_session_runtime_state(
    conn: psycopg.Connection,
    session_id: uuid.UUID,
) -> None:
    """Remove reignition state and turn embeddings; keep session row for audit FKs."""
    conn.execute(
        "DELETE FROM session_turn_embeddings WHERE session_id = %s",
        (session_id,),
    )
    conn.execute(
        """
        UPDATE sessions
        SET current_state = '{}'::jsonb
        WHERE session_id = %s
        """,
        (session_id,),
    )


def cleanup_expired_sessions(*, dry_run: bool = False) -> int:
    """
    Clear runtime state for all sessions past the inactivity threshold.
    Returns the number of sessions cleared (or that would be cleared if dry_run).
    """
    cutoff = _session_inactivity_cutoff()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT session_id FROM sessions
            WHERE updated_at < %s
              AND (
                current_state IS DISTINCT FROM '{}'::jsonb
                OR EXISTS (
                    SELECT 1 FROM session_turn_embeddings ste
                    WHERE ste.session_id = sessions.session_id
                )
              )
            """,
            (cutoff,),
        ).fetchall()
        if dry_run:
            return len(rows)
        for (session_id,) in rows:
            clear_session_runtime_state(conn, session_id)
        conn.commit()
    return len(rows)


def ensure_session_active(session_id: uuid.UUID) -> None:
    cutoff = _session_inactivity_cutoff()
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT updated_at FROM sessions
            WHERE session_id = %s
            """,
            (session_id,),
        ).fetchone()
        if not row:
            raise ValueError(f"Session not found: {session_id}")
        updated_at = row[0]
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        if updated_at < cutoff:
            clear_session_runtime_state(conn, session_id)
            conn.commit()
            raise SessionExpiredError(
                f"Session expired after {get_settings().session_inactivity_hours}h inactivity — "
                "create a new session."
            )


def get_session_experience_level(session_id: uuid.UUID) -> str:
    ensure_session_active(session_id)
    with get_connection() as conn:
        row = conn.execute(
            "SELECT experience_level FROM sessions WHERE session_id = %s",
            (session_id,),
        ).fetchone()
    if not row:
        raise ValueError(f"Session not found: {session_id}")
    return row[0]


def update_session_experience_level(session_id: uuid.UUID, level: str) -> str:
    if level not in VALID_EXPERIENCE_LEVELS:
        level = DEFAULT_EXPERIENCE_LEVEL
    ensure_session_active(session_id)
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE sessions
            SET experience_level = %s, updated_at = NOW()
            WHERE session_id = %s
            """,
            (level, session_id),
        )
        conn.commit()
    return level


def load_session_state(session_id: uuid.UUID) -> SessionState:
    ensure_session_active(session_id)
    with get_connection() as conn:
        row = conn.execute(
            "SELECT current_state FROM sessions WHERE session_id = %s",
            (session_id,),
        ).fetchone()
    if not row:
        raise ValueError(f"Session not found: {session_id}")
    return SessionState.from_db(row[0])


def save_session_state(session_id: uuid.UUID, state: SessionState) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE sessions
            SET current_state = %s::jsonb, updated_at = NOW()
            WHERE session_id = %s
            """,
            (psycopg.types.json.Json(state.to_dict()), session_id),
        )
        conn.commit()


def mark_learnings_generated(session_id: uuid.UUID) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE sessions
            SET learnings_generated_at = NOW(), updated_at = NOW()
            WHERE session_id = %s
            """,
            (session_id,),
        )
        conn.commit()


def fetch_session_turns(session_id: uuid.UUID) -> list[dict[str, Any]]:
    ensure_session_active(session_id)
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT turn_id, user_question, final_answer, refusal_category,
                   citation_flow, created_at
            FROM query_logs
            WHERE session_id = %s
            ORDER BY created_at
            """,
            (session_id,),
        ).fetchall()
    return [
        {
            "turn_id": row[0],
            "user_question": row[1],
            "final_answer": row[2],
            "refusal_category": row[3],
            "citation_flow": row[4] if isinstance(row[4], dict) else {},
            "created_at": row[5],
        }
        for row in rows
    ]


def log_pii_refusal(session_id: uuid.UUID, pii_type: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO pii_refusals (pii_refusal_id, session_id, pii_type)
            VALUES (%s, %s, %s)
            """,
            (uuid.uuid4(), session_id, pii_type),
        )
        conn.commit()


def log_query_turn(
    *,
    session_id: uuid.UUID,
    experience_level: str,
    user_question: str,
    final_answer: str,
    retrieved_chunks: list[dict[str, Any]],
    final_prompt: str | None,
    raw_llm_output: str | None,
    cited_chunk_id: uuid.UUID | None,
    citation_flow: CitationFlow,
    refusal_category: str | None,
    timings: GenerationTimings,
    cost_usd: float,
) -> uuid.UUID:
    turn_id = uuid.uuid4()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO query_logs (
                turn_id, session_id, experience_level, user_question,
                retrieved_chunks, final_prompt, raw_llm_output, final_answer,
                cited_chunk_id, citation_flow, refusal_category,
                latency_input_filters_ms, latency_embedding_ms, latency_retrieval_ms,
                latency_rerank_ms, latency_generation_ms, latency_postprocessing_ms,
                latency_total_ms, cost_usd
            ) VALUES (
                %s, %s, %s, %s,
                %s::jsonb, %s, %s, %s,
                %s, %s::jsonb, %s,
                %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                turn_id,
                session_id,
                experience_level,
                user_question,
                psycopg.types.json.Json(retrieved_chunks),
                final_prompt,
                raw_llm_output,
                final_answer,
                cited_chunk_id,
                psycopg.types.json.Json(citation_flow.to_dict()),
                refusal_category,
                int(timings.input_filters_ms),
                int(timings.embedding_ms),
                int(timings.retrieval_ms),
                int(timings.rerank_ms),
                int(timings.generation_ms),
                int(timings.postprocessing_ms),
                int(timings.total_ms),
                cost_usd,
            ),
        )
        conn.execute(
            "UPDATE sessions SET updated_at = NOW() WHERE session_id = %s",
            (session_id,),
        )
        conn.commit()
    return turn_id


def log_feedback(
    turn_id: uuid.UUID,
    session_id: uuid.UUID,
    rating: str,
    comment: str | None = None,
) -> uuid.UUID:
    if rating not in ("thumbs_up", "thumbs_down"):
        raise ValueError("rating must be thumbs_up or thumbs_down")
    feedback_id = uuid.uuid4()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO feedback (feedback_id, turn_id, session_id, rating, comment)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (turn_id) DO UPDATE SET
                rating = EXCLUDED.rating,
                comment = EXCLUDED.comment,
                created_at = NOW()
            """,
            (feedback_id, turn_id, session_id, rating, comment),
        )
        conn.commit()
    return feedback_id
