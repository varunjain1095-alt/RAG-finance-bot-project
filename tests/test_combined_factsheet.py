"""Tests for combined AMC factsheet scheme tagging."""

import unittest

from rag_bot.ingestion.parsers.combined_factsheet import (
    assign_scheme_for_page,
    chunk_combined_factsheet_markdown,
)
from rag_bot.retrieval.schemes import (
    BALANCED_ADVANTAGE,
    ELSS,
    FLEXICAP,
    LARGE_CAP,
)


class CombinedFactsheetTests(unittest.TestCase):
    def test_detects_scheme_from_performance_line(self) -> None:
        text = (
            "Notes: 1. Different plans shall have different expense structure. "
            "The performance details provided herein are of ICICI Prudential Flexicap Fund. "
            "2. The scheme is currently managed by Sankaran Naren."
        )
        scheme, sticky = assign_scheme_for_page(text, None)
        self.assertEqual(scheme, FLEXICAP)
        self.assertEqual(sticky, FLEXICAP)

    def test_carries_scheme_on_factsheet_continuation_page(self) -> None:
        continuation = (
            "## Page 58\n\n"
            "minimum redemption amount pertaining to the scheme. "
            "For SIP Returns : Refer page no. from 147 to 152."
        )
        scheme, sticky = assign_scheme_for_page(continuation, BALANCED_ADVANTAGE)
        self.assertEqual(scheme, BALANCED_ADVANTAGE)
        self.assertEqual(sticky, BALANCED_ADVANTAGE)

    def test_index_page_not_tagged(self) -> None:
        index = (
            "ICICI Prudential Large Cap Fund\n"
            "ICICI Prudential Flexicap Fund\n"
            "ICICI Prudential ELSS Tax Saver Fund\n"
            "ICICI Prudential Balanced Advantage Fund"
        )
        scheme, sticky = assign_scheme_for_page(index, FLEXICAP)
        self.assertIsNone(scheme)
        self.assertIsNone(sticky)

    def test_chunk_tags_large_cap_page_with_min_investment(self) -> None:
        markdown = (
            "## Page 14\n\n"
            "Application Amount for fresh Subscription : Rs.100 (plus in multiples of Re.1)\n"
            "The performance details provided herein are of ICICI Prudential Large Cap Fund.\n"
            "ICICI Prudential Large Cap Fund (Erstwhile ICICI Prudential Bluechip Fund)"
        )
        parents = chunk_combined_factsheet_markdown(markdown)
        tagged = [p for p in parents if p.scheme_name == LARGE_CAP]
        self.assertTrue(tagged)
        combined_text = " ".join(c.text for p in tagged for c in p.children)
        self.assertIn("Application Amount", combined_text)

    def test_elss_page_tagged(self) -> None:
        markdown = (
            "## Page 22\n\n"
            "The performance details provided herein are of ICICI Prudential ELSS Tax Saver Fund.\n"
            "Application Amount for fresh Subscription : Rs.500"
        )
        parents = chunk_combined_factsheet_markdown(markdown)
        self.assertTrue(any(p.scheme_name == ELSS for p in parents))


if __name__ == "__main__":
    unittest.main()
