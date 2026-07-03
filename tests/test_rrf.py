"""Tests for RRF fusion."""

import unittest

from rag_bot.retrieval.search import rrf_fuse


class RrfFusionTests(unittest.TestCase):
    def test_merge_two_lists(self) -> None:
        fused = rrf_fuse([["a", "b", "c"], ["c", "a", "d"]])
        scores = dict(fused)
        self.assertIn("a", scores)
        self.assertIn("c", scores)
        # c appears high in both lists
        self.assertGreater(scores["c"], scores["b"])


if __name__ == "__main__":
    unittest.main()
