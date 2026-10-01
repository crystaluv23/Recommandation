"""Regression checks for construction errors and reachable context omissions."""

import unittest

from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.stage_contracts import (
    bounded_entry_page, json_bytes, validate_stage_input,
)


class StageContractTests(unittest.TestCase):
    def test_missing_dependency_and_label_permission_fail_before_transport(self):
        with self.assertRaisesRegex(ValidationError, "dependency missing"):
            validate_stage_input("research_controller_reflect", {"research_state": {}}, allow_outcomes=False)
        with self.assertRaisesRegex(ValidationError, "cannot allow outcomes"):
            validate_stage_input("blind_predictor_predict", {"final_context": {}}, allow_outcomes=True)
        audit = validate_stage_input("blind_predictor_predict_correction", {"final_context": {}}, allow_outcomes=False)
        self.assertTrue(audit["registered"])
        self.assertEqual(audit["payload_utf8_bytes"], json_bytes({"final_context": {}}))

    def test_unknown_extension_is_explicitly_unregistered(self):
        self.assertFalse(validate_stage_input("new_extension", {}, allow_outcomes=False)["registered"])

    def test_oversized_first_entry_cannot_hide_readable_later_entries(self):
        entries = [{"ref": "large", "text": "x" * 500}, {"ref": "small", "text": "ready"}]
        page = bounded_entry_page(entries, max_bytes=100)
        self.assertEqual(page["items"], [entries[1]])
        self.assertEqual(page["oversized_entries"][0]["index"], 0)
        self.assertEqual(page["counts"]["oversized"], 1)
        self.assertFalse(page["selection_is_exhaustive"])
        self.assertEqual(len(entries[0]["text"]), 500)

    def test_pagination_discloses_both_omission_directions(self):
        entries = [{"ref": str(i)} for i in range(5)]
        first = bounded_entry_page(entries, max_items=2)
        second = bounded_entry_page(entries, cursor=first["next_cursor"], max_items=2)
        self.assertEqual(first["counts"]["omitted_after"], 3)
        self.assertEqual(second["counts"]["omitted_before"], 2)
        self.assertEqual(second["counts"]["omitted_after"], 1)
        self.assertEqual(second["items"], entries[2:4])


class TemporalGuardInflectionTests(unittest.TestCase):
    """Real v154 hypotheses distinguish future completion from current pricing."""

    def test_v154_viasat_within_horizon_expectations_is_admissible(self):
        from stock_opportunity_agent.research.evolution_research_validation import (
            _raw_research_evaluation_boundary_issues,
        )
        context = {"prediction_time": "2025-05-30T00:00:00+00:00", "horizon_end": "2025-11-30"}
        actual = (
            "If Viasat discloses within the horizon that its final two Viasat-3 "
            "satellites remain on schedule for early 2026 operation and that "
            "capex is declining toward the stated $1.3B next-12-month level, "
            "then expectations for positive free cash flow by mid-2026 could "
            "improve enough to support a partial re-rating, but not necessarily "
            "a doubling by 2025-11-30."
        )
        issues = _raw_research_evaluation_boundary_issues({"hypotheses": [actual]}, context)
        self.assertNotIn("outside_horizon_event_causality", {issue.code for issue in issues})
        unsupported = "The 2026 operation of the satellites will cause the share price to double."
        issues = _raw_research_evaluation_boundary_issues({"hypotheses": [unsupported]}, context)
        self.assertIn("outside_horizon_event_causality", {issue.code for issue in issues})
