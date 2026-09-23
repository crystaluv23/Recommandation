"""Zero-call replay acceptance for the completed V139 live cycle."""

import unittest

from scripts.replay_v139_live_acceptance import (
    DEFAULT_V130,
    DEFAULT_V139,
    replay,
)


class V139LiveAcceptanceTest(unittest.TestCase):
    def test_v139_live_artifacts_expose_successes_and_remaining_gaps(self):
        report = replay(DEFAULT_V130, DEFAULT_V139)

        self.assertEqual(report["external_calls"], 0)
        self.assertFalse(report["locked_test_accessed"])
        self.assertTrue(report["parallel_fast"]["actual_parallel_overlap"])
        self.assertFalse(
            report["best_v139_vs_v130"]["significant_decline_detected"]
        )
        self.assertEqual(
            report["attempt_recovery"]["historical_status_counts"][
                "in_progress"
            ],
            2,
        )
        self.assertEqual(
            report["attempt_recovery"]["post_reconcile_summary"][
                "in_progress"
            ],
            0,
        )
        self.assertEqual(report["slow"]["magnitude_feedback_count"], 2)
        self.assertFalse(report["slow"]["historical_target_track_present"])
        self.assertFalse(
            report["slow"][
                "narrative_exploration_claim_valid_under_current_contract"
            ]
        )
        self.assertEqual(
            report["post_fix_target_sampling"]["dev_group_counts"],
            {"ge3_high": 16, "ge3_low": 16},
        )
        self.assertEqual(
            report["post_fix_target_sampling"]["check_group_counts"],
            {"ge3_high": 8, "ge3_low": 8},
        )
        self.assertTrue(
            report["post_fix_target_sampling"]["issuer_disjoint"]
        )


if __name__ == "__main__":
    unittest.main()
