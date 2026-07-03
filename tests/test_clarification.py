"""Clarification intent and citation low-confidence guard tests."""

import unittest
from unittest.mock import MagicMock, patch

from rag_bot.generation.citations import (
    enforce_citation,
    is_borderline_grounding,
    top_parent_rerank_score,
)
from rag_bot.generation.clarification import (
    is_clarification_request,
    resolve_serial_section_for_clarification,
)
from rag_bot.generation.serial_explanations import (
    CATALOGS,
    SerialExplanationState,
)
from rag_bot.generation.session_state import SessionState
from rag_bot.retrieval.types import ParentContext


class ClarificationIntentTests(unittest.TestCase):
    def test_detects_confusion_phrases(self) -> None:
        self.assertTrue(is_clarification_request("I dont get it"))
        self.assertTrue(is_clarification_request("I don't understand"))
        self.assertTrue(is_clarification_request("confused"))
        self.assertTrue(is_clarification_request("what does that mean"))

    def test_ignores_factual_questions(self) -> None:
        self.assertFalse(is_clarification_request("What is the minimum SIP for Bluechip?"))

    def test_serial_clarification_uses_last_delivered_section(self) -> None:
        catalog = CATALOGS["sip_intro"]
        serial = SerialExplanationState(
            topic_id="sip_intro",
            anchor_question="Explain SIP",
            status="active",
            delivered_section_ids=["what_it_is"],
        )
        section = resolve_serial_section_for_clarification(serial, catalog)
        self.assertEqual(section.id, "what_it_is")


class CitationLowConfidenceGuardTests(unittest.TestCase):
    def _parent(self, url: str, score: float | None = None) -> ParentContext:
        return ParentContext(
            parent_chunk_id="p1",
            text="snippet",
            source_name="Factsheet PDF",
            date_version="2026-03",
            source_url=url,
            scheme_name=None,
            rerank_score=score,
            formatted_text="",
        )

    def test_borderline_margin(self) -> None:
        self.assertTrue(is_borderline_grounding(0.326, 0.35))
        self.assertFalse(is_borderline_grounding(0.41, 0.35))
        self.assertTrue(is_borderline_grounding(None, 0.35))

    def test_borderline_low_score_no_confident_citation(self) -> None:
        url = "https://digitalfactsheet.icicipruamc.com/fact/pdf/combined.pdf"
        parents = [self._parent(url, 0.326)]
        raw = "[FACTUAL] Some answer without citation block."
        answer, flow, _ = enforce_citation(
            raw,
            parents,
            top_rerank_score=0.326,
            grounding_threshold=0.35,
        )
        self.assertEqual(flow.final_outcome, "low_confidence_refusal")
        self.assertIsNone(flow.cited_url)
        self.assertNotIn(url, answer)
        self.assertIn("couldn't find", answer.lower())

    def test_clarification_context_message(self) -> None:
        url = "https://example.com/doc.pdf"
        parents = [self._parent(url, 0.32)]
        raw = "[FACTUAL] Unclear answer."
        answer, flow, _ = enforce_citation(
            raw,
            parents,
            top_rerank_score=0.32,
            grounding_threshold=0.35,
            clarification_context=True,
        )
        self.assertEqual(flow.final_outcome, "low_confidence_refusal")
        self.assertIn("which part is unclear", answer.lower())

    def test_high_score_allows_fallback_refusal(self) -> None:
        url = "corpus:ter-jun2026-flexicap"
        parents = [self._parent(url, 0.85)]
        raw = "[FACTUAL] Some answer without citation block."
        answer, flow, _ = enforce_citation(
            raw,
            parents,
            top_rerank_score=0.85,
            grounding_threshold=0.35,
        )
        self.assertEqual(flow.final_outcome, "fallback_refusal")
        self.assertEqual(flow.cited_url, url)
        self.assertIn(url, answer)

    def test_top_parent_rerank_score(self) -> None:
        parents = [
            self._parent("https://a.com", 0.2),
            self._parent("https://b.com", 0.45),
        ]
        self.assertEqual(top_parent_rerank_score(parents), 0.45)


class ClarificationMidSerialPipelineTests(unittest.TestCase):
    @patch("rag_bot.generation.pipeline.save_session_state")
    @patch("rag_bot.generation.pipeline._record_turn")
    @patch("rag_bot.generation.pipeline.generate_completion")
    @patch("rag_bot.generation.pipeline.load_parents_by_ids")
    @patch("rag_bot.generation.pipeline.load_session_state")
    @patch("rag_bot.generation.pipeline.get_session_experience_level")
    @patch("rag_bot.generation.pipeline.apply_migrations")
    def test_clarification_mid_serial_reexplain_not_abort(
        self,
        mock_migrations,
        mock_level,
        mock_load_state,
        mock_load_parents,
        mock_generate,
        mock_record_turn,
        mock_save_state,
    ) -> None:
        from rag_bot.generation.pipeline import ask

        state = SessionState()
        state.recent_turns = [
            {
                "question": "Explain SIP",
                "answer": "SIP is regular investing.",
                "turn_id": "t1",
            }
        ]
        state.serial_explanation = SerialExplanationState(
            topic_id="sip_intro",
            anchor_question="Explain SIP",
            status="active",
            delivered_section_ids=["what_it_is"],
            retrieved_parent_ids=["parent-1"],
        )
        mock_load_state.return_value = state
        mock_level.return_value = "new"
        mock_record_turn.return_value = (__import__("uuid").uuid4(), state)

        parent = ParentContext(
            parent_chunk_id="parent-1",
            text="SIP content",
            source_name="ICICI Bank SIP",
            date_version="2026-06",
            source_url="https://www.icici.bank.in/sip",
            scheme_name=None,
            rerank_score=0.9,
            formatted_text="SIP source block",
        )
        mock_load_parents.return_value = [parent]
        mock_generate.return_value = (
            "[FACTUAL] SIP means investing a fixed amount regularly.\n\n"
            "Would you like me to explain how SIP investing works?\n\n"
            "Last updated from sources: 2026-06\n"
            "Source: [ICICI Bank SIP, 2026-06](https://www.icici.bank.in/sip)",
            MagicMock(input_tokens=10, output_tokens=20),
        )

        result = ask(__import__("uuid").uuid4(), "I dont get it")

        self.assertIn("reexplain", result.debug)
        self.assertTrue(result.debug.get("reexplain"))
        self.assertEqual(state.serial_explanation.status, "active")
        self.assertEqual(state.serial_explanation.topic_id, "sip_intro")
        mock_generate.assert_called_once()


if __name__ == "__main__":
    unittest.main()
