import unittest

from stock_opportunity_agent.research.mining_closure import (
    SCENARIOS,
    build_scenario,
    promotion_decision,
    run_controlled_closure,
    run_holdout,
)


class MiningClosureTests(unittest.TestCase):
    def test_all_eight_scenarios_reach_their_expected_terminals(self) -> None:
        expected = {
            "single_fact": ("candidate", "promote"),
            "multi_period": ("rejected", "reject"),
            "ratio": ("candidate", "promote"),
            "cross_document": ("candidate", "promote"),
            "narrative_event": ("candidate", "promote"),
            "insufficient_evidence": ("evidence_unavailable", None),
            "technical_failure": ("technical_failure", None),
            "no_pattern": ("no_pattern_with_coverage", None),
        }
        self.assertEqual(set(expected), set(SCENARIOS))
        for name in SCENARIOS:
            with self.subTest(scenario=name):
                result = run_controlled_closure(name)
                terminal, decision = expected[name]
                self.assertEqual(result.terminal_kind, terminal)
                self.assertEqual(result.decision, decision)

    def test_single_fact_full_loop_promotes_with_complete_chain(self) -> None:
        result = run_controlled_closure("single_fact")

        self.assertEqual(result.decision, "promote")
        self.assertEqual(result.reasons, ())
        self.assertEqual(result.dev_fixture["available"], 4)
        self.assertEqual(result.dev_fixture["correct"], 4)
        self.assertEqual(result.holdout["available"], 4)
        self.assertEqual(result.holdout["correct"], 4)
        self.assertEqual(result.holdout["wrong"], 0)

    def test_multi_period_check_contradiction_rejects_with_reasons(self) -> None:
        result = run_controlled_closure("multi_period")

        self.assertEqual(result.decision, "reject")
        self.assertTrue(result.reasons)
        self.assertIn(
            "no positive directional evidence", " ".join(result.reasons)
        )
        self.assertGreaterEqual(result.holdout.get("wrong", 0), 1)

    def test_cross_document_requires_two_distinct_documents(self) -> None:
        result = run_controlled_closure("cross_document")

        self.assertEqual(result.decision, "promote")
        scenario = build_scenario("cross_document")
        dev = run_holdout(scenario.execution, scenario.store, scenario.dev_cases)
        self.assertEqual(dev["available"], 4)
        self.assertEqual(dev["correct"], 4)

    def test_narrative_event_execution_reads_only_narrative_family(self) -> None:
        scenario = build_scenario("narrative_event")
        aggregate = run_holdout(
            scenario.execution, scenario.store, scenario.dev_cases
        )

        self.assertEqual(aggregate["available"], 4)
        self.assertEqual(aggregate["correct"], 4)
        self.assertEqual(aggregate["wrong"], 0)

    def test_promotion_decision_keeps_the_absolute_floor(self) -> None:
        self.assertEqual(
            promotion_decision({"available": 2, "correct": 2, "wrong": 0}),
            {
                "decision": "reject",
                "reasons": ["insufficient availability: 2 < 3"],
            },
        )
        self.assertEqual(
            promotion_decision({"available": 4, "correct": 1, "wrong": 3})["decision"],
            "reject",
        )
        promoted = promotion_decision(
            {"available": 4, "correct": 3, "wrong": 1}
        )
        self.assertEqual(promoted["decision"], "promote")
        self.assertEqual(promoted["reasons"], [])

    def test_insufficient_evidence_never_becomes_a_domain_claim(self) -> None:
        result = run_controlled_closure("insufficient_evidence")

        self.assertEqual(result.terminal_kind, "evidence_unavailable")
        self.assertIsNone(result.decision)
        self.assertEqual(result.holdout, {})

    def test_unknown_scenario_name_is_rejected(self) -> None:
        from stock_opportunity_agent.models import ValidationError

        with self.assertRaises(ValidationError):
            build_scenario("does-not-exist")


if __name__ == "__main__":
    unittest.main()
