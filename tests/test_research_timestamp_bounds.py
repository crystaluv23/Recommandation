"""Aware forecast cutoffs preserve instants through the actual shared validators."""
from datetime import datetime, timezone
from unittest import TestCase

from stock_opportunity_agent.research.evolution_research_validation import (
    _raw_future_information_issues, _bounded_residual_need,
)


class ResearchTimestampBoundTests(TestCase):
    cutoff = datetime(2025, 9, 30, tzinfo=timezone.utc)

    def issues(self, need, cutoff=None):
        return _raw_future_information_issues({"next_information_needs": [need]},
            {"prediction_time": (cutoff or self.cutoff).isoformat()})

    def test_equal_earlier_and_equivalent_zone_forecasts(self):
        for bound in ("2025-09-30T00:00:00+00:00", "2025-09-30T00:00:00Z",
                      "2025-09-30T08:00:00+08:00", "2025-09-29T23:59:59+00:00"):
            for topic in ("Q3 2025 guidance", "Q4 2025 outlook", "2026 forecasts", "fiscal 2026 estimates"):
                with self.subTest(bound=bound, topic=topic):
                    self.assertEqual(self.issues(f"What {topic} had the issuer disclosed by {bound}?"), [])

    def test_future_instant_naive_and_malformed_bounds_cannot_license_forecasts(self):
        for bound in ("2025-09-30T00:00:01+00:00", "2025-09-30T18:00:00+00:00",
                      "2025-09-30T08:00:01+08:00", "2025-09-30T00:00:00",
                      "2025-09-30T00:00:00Zgarbage", "2025-09-30T25:00:00+00:00",
                      "2025-09-30T00:00:00+99:00"):
            with self.subTest(bound=bound):
                self.assertTrue(self.issues(f"What Q4 2025 guidance had the issuer disclosed by {bound}?"))

    def test_actual_runtime_intraday_cutoff_is_retained(self):
        cutoff = datetime(2025, 9, 30, 12, tzinfo=timezone.utc)
        self.assertEqual(self.issues("What Q4 2025 forecast was disclosed by 2025-09-30T11:59:59Z?", cutoff), [])
        self.assertTrue(self.issues("What Q4 2025 forecast was disclosed by 2025-09-30T12:00:01Z?", cutoff))

    def test_valid_bound_does_not_authorize_future_actual_or_publication(self):
        for need in (
            "What Q4 2025 actual revenue and forecast had the issuer disclosed by 2025-09-30T00:00:00Z?",
            "What Q4 2025 forecasts were published on 2025-11-10, as of 2025-09-30T00:00:00Z?",
            "What forecasts were published on 2025-11-10T12:00:00Z, as of 2025-09-30T00:00:00Z?",
            "What forecasts were published on 2025-09-30T00:00:01Z, as of 2025-09-30T00:00:00Z?",
            "What Q4 2025 actual results and Q3 2025 outlook were disclosed by 2025-09-30T00:00:00Z?",
            "What is the issuer's Q3 2025 revenue guidance?",
        ):
            with self.subTest(need=need):
                self.assertTrue(self.issues(need))

    def test_residual_inherits_exact_aware_bound(self):
        prior = "What Q4 2025 revenue guidance and adjustment direction were disclosed by 2025-09-30T08:00:00+08:00?"
        bounded = _bounded_residual_need("What is the Q4 2025 adjustment direction?", prior, self.cutoff)
        self.assertIsNotNone(bounded)
        self.assertIn("2025-09-30T08:00:00+08:00", bounded)
        self.assertEqual(self.issues(bounded), [])

    def test_missing_or_naive_context_remains_unknown_without_typeerror(self):
        value = {"next_information_needs": ["What Q4 2025 guidance was disclosed by 2025-09-30T00:00:00Z?"]}
        for context in (None, {}, {"prediction_time": "invalid"}, {"prediction_time": "2025-09-30"},
                        {"prediction_time": "2025-09-30T00:00:00"}):
            with self.subTest(context=context):
                self.assertEqual(_raw_future_information_issues(value, context), [])
