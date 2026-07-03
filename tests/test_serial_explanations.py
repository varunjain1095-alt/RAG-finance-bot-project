"""Serial multi-turn conceptual explanation tests."""

import unittest

from rag_bot.generation.serial_explanations import (
    CATALOGS,
    answer_has_expected_closing,
    detect_scope_violations,
    detect_serial_topic,
    ensure_serial_closing,
    filter_scope_violating_sentences,
    format_follow_up_closing,
    format_serial_prompt_block,
    get_section_forbidden_instruction,
    is_continuation_message,
    is_decline_message,
    is_serial_runaway_body,
    pick_follow_up_labels,
    resolve_section_for_continuation,
    SerialExplanationState,
)


class SerialExplanationTests(unittest.TestCase):
    def test_detect_mutual_funds_topic(self) -> None:
        self.assertEqual(detect_serial_topic("explain mutual funds"), "mutual_funds_intro")

    def test_detect_what_is_a_mutual_fund(self) -> None:
        self.assertEqual(
            detect_serial_topic("what is a mutual fund"), "mutual_funds_intro"
        )

    def test_detect_sip_topic(self) -> None:
        self.assertEqual(detect_serial_topic("what is SIP?"), "sip_intro")
        self.assertEqual(detect_serial_topic("what is SIP"), "sip_intro")

    def test_detect_sip_follow_up_label(self) -> None:
        self.assertEqual(
            detect_serial_topic("How SIP investing works"), "sip_intro"
        )

    def test_detect_sip_how_does_work(self) -> None:
        self.assertEqual(
            detect_serial_topic("How does SIP work?"), "sip_intro"
        )

    def test_affirmative_continuation(self) -> None:
        serial = SerialExplanationState(
            topic_id="mutual_funds_intro",
            anchor_question="explain mutual funds",
            status="active",
            delivered_section_ids=["what_it_is"],
        )
        self.assertTrue(is_continuation_message("yes", serial))

    def test_section_name_continuation(self) -> None:
        serial = SerialExplanationState(
            topic_id="mutual_funds_intro",
            anchor_question="explain mutual funds",
            status="active",
            delivered_section_ids=["what_it_is"],
        )
        self.assertTrue(is_continuation_message("key mechanics", serial))

    def test_resolve_named_section(self) -> None:
        catalog = CATALOGS["mutual_funds_intro"]
        serial = SerialExplanationState(
            topic_id="mutual_funds_intro",
            anchor_question="explain mutual funds",
            status="active",
            delivered_section_ids=["what_it_is"],
        )
        section = resolve_section_for_continuation("why invest", serial, catalog)
        self.assertEqual(section.id, "why_invest")

    def test_follow_up_excludes_completed_catalogs(self) -> None:
        catalog = CATALOGS["mutual_funds_intro"]
        labels = pick_follow_up_labels(
            catalog,
            completed_catalog_ids=["sip_intro"],
        )
        self.assertEqual(len(labels), 2)
        self.assertNotIn("How SIP investing works", labels)

    def test_follow_up_closing_format(self) -> None:
        closing = format_follow_up_closing(["A", "B", "C"])
        self.assertIn("Want to learn more?", closing)
        self.assertIn("A; B; C", closing)

    def test_decline_message(self) -> None:
        self.assertTrue(is_decline_message("no thanks"))

    def test_serial_runaway_caps(self) -> None:
        short = "A mutual fund pools money from many investors."
        self.assertFalse(is_serial_runaway_body(short))
        long_body = " ".join(["word"] * 121)
        self.assertTrue(is_serial_runaway_body(long_body))

    def test_scope_violation_nav_on_what_it_is(self) -> None:
        body = (
            "A mutual fund pools investor money. When you invest you receive units at NAV."
        )
        violations = detect_scope_violations(
            "mutual_funds_intro", "what_it_is", body
        )
        self.assertIn("key_mechanics", violations)

    def test_scope_violation_sebi_on_what_it_is(self) -> None:
        body = "A mutual fund pools money. SEBI regulates fees funds can charge."
        violations = detect_scope_violations(
            "mutual_funds_intro", "what_it_is", body
        )
        self.assertIn("structure_regulation", violations)

    def test_filter_scope_violating_sentences(self) -> None:
        body = (
            "A mutual fund pools money from many investors. "
            "When you invest you receive units at NAV. "
            "SEBI regulates mutual funds."
        )
        filtered = filter_scope_violating_sentences(
            "mutual_funds_intro", "what_it_is", body
        )
        self.assertIn("pools money", filtered)
        self.assertNotIn("NAV", filtered)
        self.assertNotIn("SEBI", filtered)

    def test_ensure_serial_closing_appends_offer_next(self) -> None:
        answer = (
            "A mutual fund pools money from investors.\n\n"
            "Last updated from sources: 2026-06\n"
            "Source: [AMFI, 2026-06](https://example.com)"
        )
        offer = "Would you like me to run through the key mechanics?"
        result = ensure_serial_closing(answer, offer)
        self.assertIn(offer, result)
        self.assertTrue(answer_has_expected_closing(result, offer))
        self.assertIn("Last updated from sources:", result)

    def test_ensure_serial_closing_splits_inline_question(self) -> None:
        offer = "Would you like me to run through the key mechanics?"
        answer = (
            f"A mutual fund pools money from investors. {offer}\n\n"
            "Last updated from sources: 2026-06\n"
            "Source: [AMFI, 2026-06](https://example.com)"
        )
        result = ensure_serial_closing(answer, offer)
        self.assertIn(f"investors\n\n{offer}", result)
        self.assertNotIn(f"investors. {offer}", result)

    def test_forbidden_instruction_what_it_is(self) -> None:
        text = get_section_forbidden_instruction("mutual_funds_intro", "what_it_is")
        self.assertIsNotNone(text)
        self.assertIn("SEBI", text)
        self.assertIn("NAV", text)

    def test_format_serial_prompt_block_includes_forbidden(self) -> None:
        section = CATALOGS["mutual_funds_intro"].sections[0]
        block = format_serial_prompt_block(
            section,
            catalog_id="mutual_funds_intro",
            is_last=False,
            follow_up_labels=None,
        )
        self.assertIn("Do NOT mention in this section", block)
        self.assertIn("End with exactly this question", block)

    def test_select_parents_for_serial_prompt(self) -> None:
        from rag_bot.generation.pipeline import _select_parents_for_serial_prompt

        class Parent:
            def __init__(self, score: float, text: str) -> None:
                self.rerank_score = score
                self.formatted_text = text

        parents = [
            Parent(0.9, "a" * 2000),
            Parent(0.5, "b" * 2000),
            Parent(0.3, "c" * 100),
        ]
        selected = _select_parents_for_serial_prompt(parents)
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0].rerank_score, 0.9)

        small_parents = [
            Parent(0.9, "a" * 1500),
            Parent(0.5, "b" * 1400),
            Parent(0.3, "c" * 100),
        ]
        selected_two = _select_parents_for_serial_prompt(small_parents)
        self.assertEqual(len(selected_two), 2)


if __name__ == "__main__":
    unittest.main()
