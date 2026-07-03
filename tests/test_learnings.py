"""Learnings document helper tests."""

import unittest

from rag_bot.generation.learnings import (
    filter_key_facts,
    substantive_overlap_ok,
    _collect_refusals,
    _collect_sources,
)


class LearningsHelperTests(unittest.TestCase):
    def test_substantive_overlap_accepts_verbatim_fact(self) -> None:
        sources = ["The expense ratio is 1.2% per the factsheet."]
        line = "- Flexicap expense ratio is 1.2% per the factsheet."
        self.assertTrue(substantive_overlap_ok(line, sources))

    def test_substantive_overlap_rejects_hallucination(self) -> None:
        sources = ["The expense ratio is 1.2% per the factsheet."]
        line = "- Flexicap expense ratio is 9.9% with guaranteed returns."
        self.assertFalse(substantive_overlap_ok(line, sources))

    def test_filter_key_facts_drops_bad_lines(self) -> None:
        sources = ["Exit load is 1% within 12 months."]
        raw = "- Exit load is 1% within 12 months.\n- Exit load is 99% forever."
        filtered = filter_key_facts(raw, sources)
        self.assertIn("1%", filtered)
        self.assertNotIn("99%", filtered)

    def test_collect_sources_from_citation_flow(self) -> None:
        turns = [
            {
                "final_answer": "Answer text.",
                "citation_flow": {"cited_url": "https://example.com/factsheet"},
            }
        ]
        urls = _collect_sources(turns)
        self.assertEqual(urls, ["https://example.com/factsheet"])

    def test_collect_refusals_performance(self) -> None:
        turns = [
            {
                "user_question": "What is the 5-year return?",
                "refusal_category": "no_performance",
                "final_answer": "See factsheet.",
            }
        ]
        lines = _collect_refusals(turns)
        self.assertEqual(len(lines), 1)
        self.assertIn("performance", lines[0].lower())


if __name__ == "__main__":
    unittest.main()
