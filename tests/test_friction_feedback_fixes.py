"""Friction feedback fixes: hints added, validation verdicts unchanged.

These fixes reduce correction friction by enriching the deterministic
correction feedback (where the missing literal lives, the exact target need,
the compliant repair path). Validators stay byte-strict: every test asserts
the issue still fails with the same code/paths while carrying the new hint.
"""

import unittest

from tests.scheme_evolution_test_support import *  # noqa: F403

from stock_opportunity_agent.research.evolution_research_validation import (
    _raw_basic_claim_quantity_issues,
    _validate_basic_claim_quantities,
)


class BasicQuantityElsewhereHintsTest(unittest.TestCase):
    """Initialize-stage preflight: name where the literal already lives."""

    def test_literal_in_other_evidence_item_is_named_in_feedback(self):
        value = {
            "supporting_evidence": [
                {
                    "claim": "Cash of 500 million supported the buyback.",
                    "exact_text": "The company held cash reserves.",
                    "projection_id": "basic:balance",
                    "basic_ref": "basic:balance",
                },
                {
                    "claim": "Liquidity totaled 500 million at year end.",
                    "exact_text": "Cash and equivalents were 500 million.",
                    "projection_id": "basic:liquidity",
                    "basic_ref": "basic:liquidity",
                },
            ]
        }
        issues = _raw_basic_claim_quantity_issues(value)
        self.assertTrue(issues)
        issue = next(
            item for item in issues if item.code == "claim_quantity_not_supported"
        )
        rendered = str(issue.message)
        self.assertIn("500 million", rendered)
        self.assertIn("evidence_item[1]", rendered)
        self.assertIn("byte-for-byte", rendered)
        self.assertIn(
            "quantity_elsewhere_hints", dict(issue.repair_context or {})
        )
        # Verdict discipline: paths and repairs unchanged from the strict form.
        self.assertEqual(
            issue.paths,
            ("supporting_evidence[0].claim",),
        )
        self.assertEqual(issue.allowed_repairs, ("replace", "remove", "add"))

    def test_literal_absent_everywhere_gets_no_compute_instruction(self):
        value = {
            "supporting_evidence": [
                {
                    "claim": "Revenue grew 40 percent year over year.",
                    "exact_text": "Revenue increased from 100 to 115.",
                    "projection_id": "basic:income",
                    "basic_ref": "basic:income",
                }
            ]
        }
        issues = _raw_basic_claim_quantity_issues(value)
        self.assertTrue(issues)
        issue = next(
            item for item in issues if item.code == "claim_quantity_not_supported"
        )
        rendered = str(issue.message)
        self.assertIn("NO supplied Basic exact_text", rendered)
        self.assertIn("narrow the claim", rendered)
        self.assertEqual(
            dict(issue.repair_context or {}).get("quantity_elsewhere"),
            "absent_from_all_basic_refs",
        )

    def test_tagged_refs_validator_names_cross_claim_locations(self):
        refs = (
            ResearchEvidenceRef(
                kind="basic_info",
                signal_ref=None,
                claim="Cash of 500 million supported the buyback.",
                exact_text="The company held cash reserves.",
                projection_id="basic:balance",
            ),
            ResearchEvidenceRef(
                kind="basic_info",
                signal_ref=None,
                claim="Liquidity totaled 500 million at year end.",
                exact_text="Cash and equivalents were 500 million.",
                projection_id="basic:liquidity",
            ),
        )
        state = ResearchState(
            decision=ResearchDecision.FINALIZE,
        )
        issues = _validate_basic_claim_quantities(refs, state)
        self.assertTrue(issues)
        rendered = str(issues[0].message)
        self.assertIn("evidence_item[1]", rendered)
        self.assertIn("byte-for-byte", rendered)


class FeedbackPathInstructionsTest(unittest.TestCase):
    def test_answer_need_and_residual_need_feedback_texts_present(self):
        import inspect

        from stock_opportunity_agent.research import evolution_plan_roles

        source = inspect.getsource(evolution_plan_roles)
        self.assertIn("themselves are not editable in this output", source)
        self.assertIn("The targeted need is:", source)
        self.assertIn("minus the facet this Signal answered", source)


if __name__ == "__main__":
    unittest.main()
