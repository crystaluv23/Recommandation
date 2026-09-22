"""Magnitude feedback wiring into reflection roles (action-plan P3)."""

import json
import unittest
from dataclasses import replace

from tests.scheme_evolution_test_support import *  # noqa: F403
from tests.evolution_runtime_test_support import *  # noqa: F403

from stock_opportunity_agent.research.scheme_evolution import score_predictions


_VALID_POSTHOC = {
    "prediction_outcome": {"correct": False},
    "decision_drivers": [],
    "why_prediction_failed": [
        "The supplied evidence supported a 2x candidate but not the realized class."
    ],
    "misleading_signals": [],
    "ignored_evidence": [],
    "missing_information": [],
    "plan_issues": [],
}

_VALID_PLAN_REFLECTION = {
    "successful_patterns": [],
    "failed_patterns": ["magnitude class systematically underestimated"],
    "repeated_failure_modes": [],
    "misleading_signals": [],
    "missing_information_needs": [],
    "next_explorations": [],
}

_VALID_ROUND_META = {
    "round_id": 1,
    "plan_level": {
        "successful_patterns": [],
        "failed_patterns": ["all positives collapse to 2-3x"],
    },
    "prediction_errors": {
        "false_positive": [],
        "false_negative": [],
    },
    "signal_observations": {
        "useful": [],
        "suspicious": [],
        "missing_capabilities": [],
    },
    "search_implications": ["test magnitude class calibration"],
    "evidence_refs": ["plan_a", "plan_b"],
}


class PosthocMagnitudeWiringTest(unittest.TestCase):
    def test_payload_carries_deterministic_magnitude_block(self):
        caller = ScriptedRoleCaller([json.loads(json.dumps(_VALID_POSTHOC))])
        predictor = LLMBlindPredictor(caller)

        predictor.reflect(
            {"summary": "Momentum and backlog growth were supplied."},
            BlindPrediction(
                is_surge=True,
                candidate_judgment=CandidateJudgment.POSSIBLE,
                magnitude=MagnitudeClass.TWO_TO_THREE,
                confidence=ConfidenceLevel.MEDIUM,
                key_reasons=("backlog growth",),
                uncertainties=(),
                session_id="anonymous-session",
            ),
            GroundTruth(15.0),
        )

        payload = caller.calls[0]["payload"]
        self.assertEqual(
            payload["magnitude_feedback"]["error_kind"],
            "underestimate",
        )
        self.assertEqual(payload["magnitude_feedback"]["ordinal_distance"], 2)
        self.assertIn("direction error", caller.calls[0]["system_prompt"])
        self.assertIn(
            "never change the copied correctness bit",
            caller.calls[0]["system_prompt"],
        )


class PlanCriticMagnitudeWiringTest(unittest.TestCase):
    def test_payload_carries_diagnostics_and_case_blocks(self):
        rows = (
            make_trajectory("case_w1", 15.0, True, MagnitudeClass.TWO_TO_THREE),
            make_trajectory("case_w2", 5.0, True, MagnitudeClass.TWO_TO_THREE),
            make_trajectory("case_w3", 2.5, True, MagnitudeClass.TWO_TO_THREE),
            make_trajectory("case_w4", 1.5, False, None),
        )
        caller = ScriptedRoleCaller(
            [json.loads(json.dumps(_VALID_PLAN_REFLECTION))]
        )

        LLMPlanCritic(caller).critique(
            plan=default_information_plan(),
            trajectories=rows,
            metrics=score_predictions(rows),
        )

        payload = caller.calls[0]["payload"]
        self.assertEqual(payload["magnitude_diagnostics"]["underestimate_count"], 2)
        self.assertEqual(
            payload["trajectories"][0]["magnitude_feedback"]["error_kind"],
            "underestimate",
        )
        self.assertEqual(
            payload["trajectories"][3]["magnitude_feedback"]["error_kind"],
            "not_applicable",
        )
        prompt = caller.calls[0]["system_prompt"]
        self.assertIn("primary fitness", prompt)
        self.assertIn("secondary ordering", prompt)
        self.assertIn("underestimates class", prompt)

    def test_technical_abstention_is_scored_but_not_research_attribution(self):
        research = make_trajectory(
            "case_research", 15.0, True, MagnitudeClass.TWO_TO_THREE
        )
        base = make_trajectory("case_technical", 15.0, False, None)
        technical = replace(
            base,
            prediction=replace(
                base.prediction,
                session_id="exclusion_case_technical",
            ),
            self_reflection=PredictionSelfReflection(
                correct=False,
                plan_issues=("technical_case_exclusion: correction exhausted",),
            ),
        )
        caller = ScriptedRoleCaller(
            [json.loads(json.dumps(_VALID_PLAN_REFLECTION))]
        )

        LLMPlanCritic(caller).critique(
            plan=default_information_plan(),
            trajectories=(research, technical),
            metrics=score_predictions((research, technical)),
        )

        payload = caller.calls[0]["payload"]
        self.assertEqual(payload["metrics"]["sample_count"], 2)
        self.assertEqual(
            payload["technical_completion"]["technical_exclusion_count"], 1
        )
        self.assertEqual(
            payload["magnitude_diagnostics"]["research_completed_case_count"], 1
        )
        technical_view = payload["trajectories"][1]
        self.assertIn("technical_exclusion", technical_view)
        self.assertFalse(
            technical_view["technical_exclusion"]["research_attribution_allowed"]
        )
        self.assertNotIn("candidate_judgment_feedback", technical_view)
        self.assertNotIn("magnitude_feedback", technical_view)
        self.assertNotIn("self_reflection", technical_view)


class RoundReflectorMagnitudeWiringTest(unittest.TestCase):
    def test_records_carry_diagnostics_and_prompt_states_ordering(self):
        record_a = make_record("plan_a", 0.7, (1.0, 0.0))
        record_b = make_record("plan_b", 0.6, (0.0, 1.0))
        caller = ScriptedRoleCaller(
            [json.loads(json.dumps(_VALID_ROUND_META))]
        )

        result = LLMRoundReflector(caller).reflect(
            round_id=1,
            records=(record_a, record_b),
            prior="reflect over the round",
            parent_comparisons_by_plan_id={"plan_a": (), "plan_b": ()},
        )

        self.assertEqual(result.evidence_refs, ("plan_a", "plan_b"))
        payload = caller.calls[0]["payload"]
        for record in payload["records"]:
            self.assertIn("magnitude_diagnostics", record)
            self.assertEqual(record["magnitude_diagnostics"]["surge_case_count"], 1)
        prompt = caller.calls[0]["system_prompt"]
        self.assertIn("magnitude macro-F1", prompt)
        self.assertIn("primary fitness", prompt)


class ProposerMagnitudeGuidanceTest(unittest.TestCase):
    def test_proposer_prompt_addresses_magnitude_tasks(self):
        import inspect

        from stock_opportunity_agent.research.evolution_plan_roles import (
            LLMInformationPlanProposer,
        )

        source_text = inspect.getsource(LLMInformationPlanProposer)
        self.assertIn("magnitude_diagnostics", source_text)
        self.assertIn("magnitude-class failures", source_text)
        self.assertIn("address, defer, or reject them", source_text)


if __name__ == "__main__":
    unittest.main()
