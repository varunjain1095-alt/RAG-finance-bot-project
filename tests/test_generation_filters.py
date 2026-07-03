"""Input filter tests."""

import unittest

from rag_bot.generation.filters import (
    FilterResultKind,
    detect_pii,
    is_investment_recommendation_request,
    is_mixed_factual_advisory,
    run_input_filters,
)
from rag_bot.generation.refusals import investment_recommendation_refusal_message


def _assert_pii_detected(query: str, expected_type: str) -> None:
    self_type = expected_type
    got = detect_pii(query)
    assert got == self_type, f"detect_pii({query!r}) = {got!r}, expected {self_type!r}"
    result = run_input_filters(query)
    assert result.kind == FilterResultKind.PII, f"filter kind = {result.kind}"
    assert result.pii_type == self_type, f"pii_type = {result.pii_type}"


class PiiDetectionTests(unittest.TestCase):
    def test_pii_pan(self) -> None:
        _assert_pii_detected("My PAN is ABCDE1234F", "pan")

    def test_pii_aadhaar_spaced(self) -> None:
        _assert_pii_detected("Aadhaar 1234 5678 9012", "aadhaar")

    def test_pii_aadhaar_unspaced(self) -> None:
        _assert_pii_detected("My Aadhaar is 123456789012", "aadhaar")

    def test_pii_account_number(self) -> None:
        _assert_pii_detected("account number 123456789012", "account_number")

    def test_pii_otp(self) -> None:
        _assert_pii_detected("OTP is 123456", "otp")

    def test_pii_email(self) -> None:
        _assert_pii_detected("Contact me at investor@example.com", "email")

    def test_pii_phone(self) -> None:
        _assert_pii_detected("Call me on +919876543210", "phone")


class InputFilterTests(unittest.TestCase):
    def test_oos_should_i_buy(self) -> None:
        result = run_input_filters("Should I buy Bluechip?")
        self.assertEqual(result.kind, FilterResultKind.OUT_OF_SCOPE)

    def test_performance_cagr(self) -> None:
        result = run_input_filters("What is the 5-year CAGR of Bluechip?")
        self.assertEqual(result.kind, FilterResultKind.NO_PERFORMANCE)

    def test_performance_balanced_advantage_performed(self) -> None:
        result = run_input_filters("How did Balanced Advantage perform last year?")
        self.assertEqual(result.kind, FilterResultKind.NO_PERFORMANCE)

    def test_mixed_passes_filters(self) -> None:
        q = "What is Flexicap expense ratio and should I invest?"
        self.assertTrue(is_mixed_factual_advisory(q))
        result = run_input_filters(q)
        self.assertEqual(result.kind, FilterResultKind.MIXED)

    def test_factual_expense_ratio_passes(self) -> None:
        result = run_input_filters("What is the expense ratio of Flexicap?")
        self.assertEqual(result.kind, FilterResultKind.PASS)

    def test_oos_best_mutual_fund_to_invest(self) -> None:
        query = "What is the best mutual fund to invest in?"
        self.assertTrue(is_investment_recommendation_request(query))
        result = run_input_filters(query)
        self.assertEqual(result.kind, FilterResultKind.OUT_OF_SCOPE)
        message = investment_recommendation_refusal_message()
        self.assertIn(
            "does not provide advice on which specific funds you should purchase",
            message,
        )
        self.assertIn("SEBI-registered investment advisor", message)
        self.assertIn("amfiindia.com/investor-corner", message)
        self.assertIn("investor.sebi.gov.in", message)


if __name__ == "__main__":
    unittest.main()
