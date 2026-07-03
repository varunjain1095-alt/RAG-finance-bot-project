"""Tests for scheme detector."""

import unittest

from rag_bot.retrieval.schemes import (
    BALANCED_ADVANTAGE,
    ELSS,
    FLEXICAP,
    LARGE_CAP,
    SchemeDetectionKind,
    detect_scheme,
)


class SchemeDetectorTests(unittest.TestCase):
    def test_canonical_flexicap(self) -> None:
        result = detect_scheme("What is the expense ratio of ICICI Prudential Flexicap Fund?")
        self.assertEqual(result.kind, SchemeDetectionKind.MATCHED)
        self.assertEqual(result.scheme_name, FLEXICAP)

    def test_bluechip_variant(self) -> None:
        result = detect_scheme("blue chip expense ratio")
        self.assertEqual(result.kind, SchemeDetectionKind.MATCHED)
        self.assertEqual(result.scheme_name, LARGE_CAP)

    def test_large_cap_official_name(self) -> None:
        result = detect_scheme("Large Cap Fund TER")
        self.assertEqual(result.kind, SchemeDetectionKind.MATCHED)
        self.assertEqual(result.scheme_name, LARGE_CAP)

    def test_out_of_scope_hdfc(self) -> None:
        result = detect_scheme("HDFC Top 100 fund expense ratio")
        self.assertEqual(result.kind, SchemeDetectionKind.OUT_OF_SCOPE)

    def test_out_of_scope_us_bluechip(self) -> None:
        result = detect_scheme("US Bluechip Equity Fund expense ratio")
        self.assertEqual(result.kind, SchemeDetectionKind.OUT_OF_SCOPE)

    def test_clarification_bluchip(self) -> None:
        result = detect_scheme("Bluchip exit load")
        self.assertEqual(result.kind, SchemeDetectionKind.CLARIFICATION)
        self.assertEqual(result.clarification_scheme, LARGE_CAP)

    def test_generic_no_scheme(self) -> None:
        result = detect_scheme("What is expense ratio?")
        self.assertEqual(result.kind, SchemeDetectionKind.NO_SCHEME)

    def test_elss_variant(self) -> None:
        result = detect_scheme("annual fee for ELSS")
        self.assertEqual(result.kind, SchemeDetectionKind.MATCHED)
        self.assertEqual(result.scheme_name, ELSS)

    def test_balanced_advantage(self) -> None:
        result = detect_scheme("balanced advantage exit load")
        self.assertEqual(result.kind, SchemeDetectionKind.MATCHED)
        self.assertEqual(result.scheme_name, BALANCED_ADVANTAGE)


if __name__ == "__main__":
    unittest.main()
