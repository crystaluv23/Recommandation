"""Detect relation-bound errors without rejecting valid research prose."""

from datetime import date
from unittest import TestCase

from stock_opportunity_agent.research.evolution_output_validation import _price_reasoning_issues
from stock_opportunity_agent.research.evolution_research_validation import (
    _future_source_date_refs,
    _runtime_evaluation_input_requested,
)


class RuntimeGuardRelationTests(TestCase):
    def test_future_exclusion_is_local_and_positive_request_still_checked(self):
        for exclusion in ("reference to", "any reference to", "referring to",
                          "using", "requesting", "requiring"):
            tail = f", without {exclusion} contents or results published after the prediction time?"
            allowed = "What did the issuer disclose by the prediction time about its scheduled results release date"
            with self.subTest(exclusion=exclusion):
                self.assertEqual(_future_source_date_refs(allowed + tail, date(2025, 9, 30),
                                                          field_name="next_information_needs"), [])
                self.assertTrue(_future_source_date_refs(
                    "What were the actual operating results after the prediction time" + tail,
                    date(2025, 9, 30), field_name="next_information_needs"))

    def test_price_expectations_subject_is_not_scalar_lookup(self):
        for price in ("current adjusted share price", "current stock price",
                      "prediction-time share price"):
            for predicate in ("already discounting the growth narrative",
                              "reflecting the disclosed expectations", "priced in the expected adoption"):
                with self.subTest(price=price, predicate=predicate):
                    self.assertFalse(_runtime_evaluation_input_requested(
                        f"Is the {price} {predicate}, and what evidence challenges that thesis?", set()))

    def test_analysis_allowance_does_not_hide_an_independent_lookup(self):
        for question in ("What is the current stock price?", "Confirm the current stock price.",
                         "Is the current stock price reflecting growth, and what is the current stock price?",
                         "Is the current stock price reflecting growth, and provide the baseline price?",
                         "Find the current stock price discounting growth."):
            with self.subTest(question=question):
                self.assertTrue(_runtime_evaluation_input_requested(question, set()))

    def test_historical_endpoints_cannot_supply_required_gain_target(self):
        anchor = {"status": "available", "mean_adjusted_close": 109.614,
                  "doubling_threshold": 219.228, "recent_close": 109.53}
        examples = (
            "The historical window runs from 87.17 to 109.53, which is far short of the 100% gain from baseline needed for 2x.",
            "Historical performance went to 90, while a 100% gain from baseline to the doubling threshold defines 2x.",
            "Reaching 50 is a historical scenario; reaching 219.228 requires a 100% gain from baseline.",
        )
        self.assertEqual(_price_reasoning_issues(enumerate(examples), anchor), [])

    def test_explicitly_bound_wrong_targets_keep_numeric_guard(self):
        anchor = {"status": "available", "mean_adjusted_close": 10,
                  "doubling_threshold": 20, "recent_close": 11}
        for text in ("To 20 requires a 106% gain from baseline.",
                     "A 106% gain from baseline to 20 is needed.",
                     "A 106% gain from baseline to the doubling threshold is needed."):
            with self.subTest(text=text):
                issues = _price_reasoning_issues((("key_reasons[0]", text),), anchor)
                self.assertEqual([i.code for i in issues], ["price_anchor_percent_change_invalid"])
                self.assertEqual(issues[0].paths, ("key_reasons[0]",))
