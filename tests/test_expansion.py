"""Tests for query expansion."""

import unittest

from rag_bot.retrieval.expansion import expand_query


class QueryExpansionTests(unittest.TestCase):
    def test_casual_term_semantic_and_lexical(self) -> None:
        expanded = expand_query("annual fee for ELSS")
        self.assertIn("expense ratio", expanded.semantic_query.lower())
        self.assertTrue(expanded.lexical_expanded)
        self.assertIn("expense ratio", expanded.lexical_query.lower())

    def test_formal_term_lexical_not_expanded(self) -> None:
        expanded = expand_query("expense ratio ELSS")
        self.assertIn("expense ratio", expanded.semantic_query.lower())
        self.assertFalse(expanded.lexical_expanded)
        self.assertEqual(expanded.lexical_query, "expense ratio ELSS")

    def test_no_match_passes_through(self) -> None:
        expanded = expand_query("Flexicap portfolio composition")
        self.assertEqual(expanded.semantic_query, "Flexicap portfolio composition")
        self.assertFalse(expanded.lexical_expanded)
        self.assertEqual(expanded.added_terms, ())


if __name__ == "__main__":
    unittest.main()
