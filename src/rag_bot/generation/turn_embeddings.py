"""Session-scoped turn embeddings for context reignition retrieval mode."""

import logging
import uuid

from rag_bot.ingestion.db import get_connection
from rag_bot.ingestion.embeddings import embed_texts

logger = logging.getLogger(__name__)

DEFAULT_TOP_K = 3


def format_turn_text(question: str, answer: str) -> str:
    return f"User: {question} | Bot: {answer}"


def store_turn_embedding(
    session_id: uuid.UUID,
    turn_id: uuid.UUID,
    turn_index: int,
    question: str,
    answer: str,
) -> None:
    turn_text = format_turn_text(question, answer)
    with get_connection() as conn:
        exists = conn.execute(
            "SELECT 1 FROM session_turn_embeddings WHERE query_log_id = %s",
            (turn_id,),
        ).fetchone()
        if exists:
            return
    embedding = embed_texts([turn_text])[0]
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO session_turn_embeddings (
                session_id, query_log_id, turn_index, text, embedding
            ) VALUES (%s, %s, %s, %s, %s)
            """,
            (session_id, turn_id, turn_index, turn_text, embedding),
        )
        conn.commit()


def backfill_session_turn_embeddings(session_id: uuid.UUID) -> int:
    """Embed all query_log turns for a session not yet indexed."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT ql.turn_id, ql.user_question, ql.final_answer,
                   ROW_NUMBER() OVER (ORDER BY ql.created_at) AS turn_index
            FROM query_logs ql
            WHERE ql.session_id = %s
              AND NOT EXISTS (
                  SELECT 1 FROM session_turn_embeddings ste
                  WHERE ste.query_log_id = ql.turn_id
              )
            ORDER BY ql.created_at
            """,
            (session_id,),
        ).fetchall()

    if not rows:
        return 0

    texts = [format_turn_text(q, a) for _, q, a, _ in rows]
    embeddings = embed_texts(texts)

    with get_connection() as conn:
        for idx, (turn_id, question, answer, turn_index) in enumerate(rows):
            conn.execute(
                """
                INSERT INTO session_turn_embeddings (
                    session_id, query_log_id, turn_index, text, embedding
                ) VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    session_id,
                    turn_id,
                    int(turn_index),
                    texts[idx],
                    embeddings[idx],
                ),
            )
        conn.commit()

    logger.info("Backfilled %d turn embeddings for session %s", len(rows), session_id)
    return len(rows)


def retrieve_relevant_turns(
    session_id: uuid.UUID,
    question: str,
    *,
    top_k: int = DEFAULT_TOP_K,
) -> list[str]:
    query_embedding = embed_texts([question])[0]
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT text,
                   (1 - (embedding <=> %s::vector))::double precision AS similarity
            FROM session_turn_embeddings
            WHERE session_id = %s
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """,
            (query_embedding, session_id, query_embedding, top_k),
        ).fetchall()
    return [row[0] for row in rows]
