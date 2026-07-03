"""Diagnostic query discovery tests (no DB required)."""

import unittest

from rag_bot.operations.diagnostics import discover_queries, list_query_names


class DiagnosticsDiscoveryTests(unittest.TestCase):
    def test_minimum_query_count(self) -> None:
        names = list_query_names()
        self.assertGreaterEqual(len(names), 15)

    def test_expected_queries_present(self) -> None:
        names = set(list_query_names())
        self.assertIn("thumbs_down_review", names)
        self.assertIn("operational_health_summary", names)
        self.assertIn("retrieval/thin_retrieval_refusals", names)
        self.assertIn("citation/invented_url_failures", names)

    def test_discover_returns_paths(self) -> None:
        queries = discover_queries()
        self.assertTrue(all(p.suffix == ".sql" for p in queries.values()))


if __name__ == "__main__":
    unittest.main()
