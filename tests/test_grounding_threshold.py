"""Grounding threshold tests (evals.md P2-13)."""

import unittest
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from rag_bot.config import reload_settings
from rag_bot.retrieval.grounding import evaluate_grounding_threshold
from rag_bot.retrieval.expansion import ExpandedQuery
from rag_bot.retrieval.schemes import FLEXICAP, SchemeDetection, SchemeDetectionKind
from rag_bot.retrieval.pipeline import retrieve
from rag_bot.retrieval.types import ChildCandidate, RetrievalOutcome


def _child(
    *,
    rerank_score: float | None = None,
    semantic_score: float | None = None,
) -> ChildCandidate:
    return ChildCandidate(
        child_chunk_id="child-1",
        parent_chunk_id="parent-1",
        text="scheme facts chunk text",
        scheme_name="ICICI Prudential Flexicap Fund",
        rrf_score=0.02,
        rerank_score=rerank_score,
        semantic_score=semantic_score,
    )


class GroundingHelperTests(unittest.TestCase):
    def test_low_rerank_score_fails_threshold(self) -> None:
        passes, score, source = evaluate_grounding_threshold(
            [_child(rerank_score=0.1, semantic_score=0.9)],
            threshold=0.35,
        )
        self.assertFalse(passes)
        self.assertEqual(score, 0.1)
        self.assertEqual(source, "rerank")

    def test_rerank_skipped_uses_semantic_fallback_pass(self) -> None:
        passes, score, source = evaluate_grounding_threshold(
            [_child(rerank_score=None, semantic_score=0.5)],
            threshold=0.35,
        )
        self.assertTrue(passes)
        self.assertEqual(score, 0.5)
        self.assertEqual(source, "semantic")

    def test_rerank_skipped_semantic_low_fails(self) -> None:
        passes, score, source = evaluate_grounding_threshold(
            [_child(rerank_score=None, semantic_score=0.1)],
            threshold=0.35,
        )
        self.assertFalse(passes)
        self.assertEqual(score, 0.1)
        self.assertEqual(source, "semantic")

    def test_no_scores_fails_by_default(self) -> None:
        passes, score, source = evaluate_grounding_threshold(
            [_child(rerank_score=None, semantic_score=None)],
            threshold=0.35,
        )
        self.assertFalse(passes)
        self.assertIsNone(score)
        self.assertEqual(source, "none")


class RetrieveGroundingIntegrationTests(unittest.TestCase):
    @contextmanager
    def _patched_retrieval(
        self,
        reranked: list[ChildCandidate],
        *,
        rerank_used: bool,
        rerank_top_score: float | None,
    ):
        mock_conn = MagicMock()
        mock_parents = [
            MagicMock(
                parent_chunk_id="parent-1",
                formatted_text="[Source: test | URL: http://example.com]\nbody",
            )
        ]

        with (
            patch("rag_bot.retrieval.pipeline.detect_scheme") as mock_detect,
            patch("rag_bot.retrieval.pipeline.expand_query") as mock_expand,
            patch("rag_bot.retrieval.pipeline.embed_texts", return_value=[[0.1] * 768]),
            patch("rag_bot.retrieval.pipeline.get_connection") as mock_get_conn,
            patch("rag_bot.retrieval.pipeline.hybrid_search") as mock_hybrid,
            patch("rag_bot.retrieval.pipeline.rerank_candidates") as mock_rerank,
            patch("rag_bot.retrieval.pipeline.dedupe_by_parent") as mock_dedupe,
            patch("rag_bot.retrieval.pipeline.swap_to_parents", return_value=mock_parents),
            patch.dict("os.environ", {"GROUNDING_THRESHOLD": "0.35"}),
        ):
            reload_settings()
            mock_detect.return_value = SchemeDetection(
                kind=SchemeDetectionKind.MATCHED,
                scheme_name=FLEXICAP,
            )
            mock_expand.return_value = ExpandedQuery(
                original="Flexicap zephyr quantum fee",
                semantic_query="Flexicap zephyr quantum fee",
                lexical_query="Flexicap zephyr quantum fee",
                lexical_expanded=False,
                added_terms=(),
            )
            mock_get_conn.return_value.__enter__.return_value = mock_conn
            mock_hybrid.return_value = reranked
            mock_rerank.return_value = (reranked, rerank_used, rerank_top_score)
            mock_dedupe.return_value = reranked[:1]
            yield

    def test_in_scheme_low_rerank_triggers_thin_retrieval(self) -> None:
        reranked = [_child(rerank_score=0.1, semantic_score=0.8)]
        with self._patched_retrieval(
            reranked, rerank_used=True, rerank_top_score=0.1
        ):
            result = retrieve("Flexicap zephyr quantum fee")
        self.assertEqual(result.outcome, RetrievalOutcome.THIN_RETRIEVAL)
        self.assertIn("couldn't find a clear answer", result.message or "")
        self.assertEqual(result.debug.get("grounding_score_source"), "rerank")
        self.assertEqual(result.top_rerank_score, 0.1)

    def test_rerank_skipped_enforces_semantic_fallback(self) -> None:
        reranked = [_child(rerank_score=None, semantic_score=0.1)]
        with self._patched_retrieval(
            reranked, rerank_used=False, rerank_top_score=None
        ):
            result = retrieve("Flexicap zephyr quantum fee")
        self.assertEqual(result.outcome, RetrievalOutcome.THIN_RETRIEVAL)
        self.assertEqual(result.debug.get("grounding_score_source"), "semantic")
        self.assertEqual(result.top_rerank_score, 0.1)

    def test_rerank_skipped_semantic_passes_threshold(self) -> None:
        reranked = [_child(rerank_score=None, semantic_score=0.5)]
        with self._patched_retrieval(
            reranked, rerank_used=False, rerank_top_score=None
        ):
            result = retrieve("Flexicap expense ratio")
        self.assertEqual(result.outcome, RetrievalOutcome.SUCCESS)
        self.assertEqual(result.debug.get("grounding_score_source"), "semantic")


if __name__ == "__main__":
    unittest.main()
