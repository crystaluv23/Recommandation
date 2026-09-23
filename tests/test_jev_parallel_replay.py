"""Acceptance test for the zero-network Jev parallel replay."""

from unittest import TestCase

from scripts.replay_jev_parallel import run_replay


class JevParallelReplayTests(TestCase):
    def test_replay_preserves_decisions_and_feedback_without_network(self):
        result = run_replay()
        self.assertEqual(result["external_calls"], 0)
        self.assertEqual(
            result["routing"]["selected_signal_refs"],
            ["revenue_growth_yoy:v1"],
        )
        self.assertEqual(len(result["routing"]["all_card_decisions"]), 2)
        self.assertEqual(
            result["routing"]["all_card_decisions"][1]["choice"],
            "no_match",
        )
        self.assertEqual(result["prediction"]["candidate_judgment"], "possible")
        self.assertEqual(result["prediction"]["magnitude"], "3-10x")
        self.assertEqual(
            result["jev_decision_feedback"]["candidate_judgment"][
                "probability_assigned_to_realized_binary"
            ],
            0.8,
        )
        self.assertTrue(all(result["acceptance"].values()))
