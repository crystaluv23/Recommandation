"""Zero-call regression replay over the immutable V130/V138 artifacts."""

from unittest import TestCase

from scripts.replay_v130_v138_acceptance import (
    DEFAULT_DATASET,
    DEFAULT_V130,
    DEFAULT_V138,
    replay,
)


class V130V138ReplayAcceptanceTests(TestCase):
    def test_regression_replay_keeps_baseline_and_repairs_systemic_boundaries(self):
        result = replay(DEFAULT_V130, DEFAULT_V138, DEFAULT_DATASET)

        self.assertAlmostEqual(result["v130"]["metrics"]["binary_f1"], 0.8)
        self.assertAlmostEqual(result["v138"]["metrics"]["binary_f1"], 0.6896551724)
        self.assertGreaterEqual(
            result["technical_recovery_counterfactual"]["metrics"]["binary_f1"],
            result["v130"]["metrics"]["binary_f1"],
        )
        self.assertGreaterEqual(
            result["correction_scope_replay"]["matched_request_count"], 2
        )
        self.assertTrue(
            result["reflection_flow_replay"]
            ["round_one_reflection_visible_to_round_two"]
        )
        self.assertFalse(
            result["reflection_flow_replay"]
            ["synthetic_research_feedback_visible"]
        )
        self.assertGreater(
            result["magnitude_target_replay"]["ten_plus_case_count_in_ge3_high"],
            0,
        )
        self.assertTrue(
            result["slow_modality_replay"]["narrative_candidate_refs"]
        )


if __name__ == "__main__":
    import unittest

    unittest.main()
