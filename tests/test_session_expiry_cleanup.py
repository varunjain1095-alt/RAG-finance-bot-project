"""Integration tests for expired-session state cleanup."""

import unittest
import uuid

import psycopg

from rag_bot.generation.logging_db import (
    SessionExpiredError,
    cleanup_expired_sessions,
    clear_session_runtime_state,
    create_session,
    ensure_session_active,
)
from rag_bot.generation.session_state import SessionState
from rag_bot.ingestion.db import apply_migrations, get_connection
from rag_bot.ingestion.embeddings import EMBEDDING_DIM


def _db_available() -> bool:
    try:
        with get_connection() as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False


def _seed_expired_session() -> uuid.UUID:
    session_id = create_session(experience_level="somewhat_familiar")
    state = SessionState(
        schemes_discussed=["ICICI Prudential Flexicap Fund"],
        active_scheme="ICICI Prudential Flexicap Fund",
        retrieval_mode=True,
        turns_backfilled=True,
    )
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE sessions
            SET current_state = %s::jsonb,
                updated_at = NOW() - INTERVAL '25 hours'
            WHERE session_id = %s
            """,
            (psycopg.types.json.Json(state.to_dict()), session_id),
        )
        zero_vector = [0.0] * EMBEDDING_DIM
        conn.execute(
            """
            INSERT INTO session_turn_embeddings (
                session_id, query_log_id, turn_index, text, embedding
            ) VALUES (%s, NULL, 1, %s, %s)
            """,
            (
                session_id,
                "User: test | Bot: answer",
                zero_vector,
            ),
        )
        conn.commit()
    return session_id


def _runtime_state_snapshot(session_id: uuid.UUID) -> tuple[dict, int]:
    with get_connection() as conn:
        state_row = conn.execute(
            "SELECT current_state FROM sessions WHERE session_id = %s",
            (session_id,),
        ).fetchone()
        embed_count = conn.execute(
            "SELECT COUNT(*) FROM session_turn_embeddings WHERE session_id = %s",
            (session_id,),
        ).fetchone()[0]
    return dict(state_row[0]), int(embed_count)


@unittest.skipUnless(_db_available(), "Postgres not available")
class SessionExpiryCleanupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        apply_migrations()

    def test_ensure_session_active_clears_state_on_expiry(self) -> None:
        session_id = _seed_expired_session()
        state_before, embeds_before = _runtime_state_snapshot(session_id)
        self.assertTrue(state_before.get("schemes_discussed"))
        self.assertEqual(embeds_before, 1)

        with self.assertRaises(SessionExpiredError):
            ensure_session_active(session_id)

        state_after, embeds_after = _runtime_state_snapshot(session_id)
        self.assertEqual(state_after, {})
        self.assertEqual(embeds_after, 0)

        row = None
        with get_connection() as conn:
            row = conn.execute(
                "SELECT session_id FROM sessions WHERE session_id = %s",
                (session_id,),
            ).fetchone()
        self.assertIsNotNone(row, "session row retained for query_logs FK integrity")

    def test_proactive_cleanup_clears_abandoned_expired_session(self) -> None:
        session_id = _seed_expired_session()
        cleared = cleanup_expired_sessions()
        self.assertGreaterEqual(cleared, 1)

        state_after, embeds_after = _runtime_state_snapshot(session_id)
        self.assertEqual(state_after, {})
        self.assertEqual(embeds_after, 0)

    def test_clear_session_runtime_state_is_idempotent(self) -> None:
        session_id = create_session()
        with get_connection() as conn:
            clear_session_runtime_state(conn, session_id)
            conn.commit()
        state_after, embeds_after = _runtime_state_snapshot(session_id)
        self.assertEqual(state_after, {})
        self.assertEqual(embeds_after, 0)


if __name__ == "__main__":
    unittest.main()
