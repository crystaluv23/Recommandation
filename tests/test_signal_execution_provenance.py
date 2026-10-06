"""Technical Signal failures survive production prediction and learning views."""

import json
from dataclasses import replace
from unittest import TestCase

from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_core import (
    CaseReflectionEvidence, PlanMetaMemory, PlanMetaReflection, RoundMetaEntry,
    _assemble_final_context, default_information_plan,
)
from stock_opportunity_agent.research.evolution_plan_roles import (
    LLMBlindPredictor, LLMPlanCritic, LLMRoundReflector, _plan_critic_trajectory,
)
from stock_opportunity_agent.research.evolution_output_validation import _compact_posthoc_context
from stock_opportunity_agent.research.scheme_evolution import score_predictions
from stock_opportunity_agent.signal_library import (
    SignalCoverage, SignalExecutionStatus, SignalResult, SignalValue,
)
from tests.scheme_evolution_test_support import NOW, make_record, make_trajectory
from tests.test_evolution_state_patch import PatchCaller


NO_FINDINGS = {
    "reflection_items": [], "selected_reflection_refs": [],
    "no_findings_reason": "Runtime provenance replay makes no economic research claim.",
}


def result(status, signal_id="fixture_signal"):
    """Keep private diagnostics local while supplying each canonical outcome."""
    technical = status not in {
        SignalExecutionStatus.SUCCESS, SignalExecutionStatus.DOMAIN_UNAVAILABLE,
    }
    return SignalResult(
        signal_id=signal_id, version=1,
        value=SignalValue.UNAVAILABLE if status is not SignalExecutionStatus.SUCCESS else SignalValue.POSITIVE,
        confidence=0 if status is not SignalExecutionStatus.SUCCESS else 0.8,
        interpretation="LOCAL_DIAGNOSTIC_SENTINEL" if technical else "Fixture domain observation.",
        coverage=SignalCoverage.UNAVAILABLE if status is not SignalExecutionStatus.SUCCESS else SignalCoverage.SUFFICIENT,
        execution_status=status,
        execution_error_code="fixture_invalid" if technical else None,
        execution_error_message="LOCAL_DIAGNOSTIC_SENTINEL" if technical else None,
    )


class SignalExecutionProvenanceTests(TestCase):
    def trajectory(self, status):
        return make_trajectory("opaque_fixture", 1.1, False, None, signal_result=result(status))

    def context(self, trajectory):
        return _assemble_final_context(
            plan=default_information_plan(), company_id=trajectory.company_id,
            additional_identity_aliases=(), basic_info=trajectory.basic_info,
            state=trajectory.final_state, rounds=trajectory.signal_rounds, prediction_time=NOW,
        )

    def test_each_execution_status_survives_final_and_posthoc_views(self):
        for status in SignalExecutionStatus:
            with self.subTest(status=status):
                trajectory = self.trajectory(status)
                context = self.context(trajectory)
                card = context["signal_rounds"][0]["batch"]["results"][0]
                self.assertEqual(card["execution"], {"status": status.value})
                compact = _compact_posthoc_context(context)
                self.assertEqual(compact["signal_results"][0]["execution"], {"status": status.value})
                critic = _plan_critic_trajectory(trajectory, case_index=1)
                self.assertEqual(critic["signal_rounds"][0]["signal_results"][0]["execution"], {"status": status.value})
                self.assertNotIn("LOCAL_DIAGNOSTIC_SENTINEL", json.dumps([context, compact, critic]))
                self.assertEqual(trajectory.signal_rounds[0].batch.results[0].execution_status, status)

    def test_repeated_signal_keeps_its_own_round_result(self):
        failed = self.trajectory(SignalExecutionStatus.VALIDATION_FAILED)
        successful = self.trajectory(SignalExecutionStatus.SUCCESS)
        trajectory = replace(failed, signal_rounds=(*failed.signal_rounds, *successful.signal_rounds))
        cards = [row["batch"]["results"][0] for row in self.context(trajectory)["signal_rounds"]]
        self.assertEqual([row["execution"]["status"] for row in cards], ["validation_failed", "success"])
        self.assertEqual([row["state"]["value"] for row in cards], ["unavailable", "positive"])

    def test_actual_predictor_and_posthoc_requests_receive_status(self):
        trajectory = self.trajectory(SignalExecutionStatus.BUDGET_BLOCKED)
        context = self.context(trajectory)
        prediction = trajectory.prediction.to_dict()
        prediction.pop("is_surge")
        caller = PatchCaller(prediction, NO_FINDINGS)
        predictor = LLMBlindPredictor(caller)
        predicted = predictor.predict(context).value
        predictor.reflect(context, predicted, trajectory.ground_truth)
        self.assertEqual(len(caller.calls), 2)
        self.assertEqual(caller.calls[0]["payload"]["final_context"]["signal_rounds"][0]["batch"]["results"][0]["execution"], {"status": "budget_blocked"})
        self.assertEqual(caller.calls[1]["payload"]["compact_context"]["signal_results"][0]["execution"], {"status": "budget_blocked"})
        for call in caller.calls:
            self.assertIn("technical execution gaps", call["system_prompt"])
            self.assertNotIn("LOCAL_DIAGNOSTIC_SENTINEL", json.dumps(call))

    def test_actual_critic_request_and_persisted_round_slow_read_retain_failures(self):
        trajectory = self.trajectory(SignalExecutionStatus.VALIDATION_FAILED)
        caller = PatchCaller(NO_FINDINGS)
        reflection = LLMPlanCritic(caller).critique(
            plan=default_information_plan(), trajectories=(trajectory,),
            metrics=score_predictions((trajectory,)),
        )
        expected = [{"signal_round": 1, "signal_ref": "fixture_signal:v1", "status": "validation_failed"}]
        self.assertEqual(caller.calls[0]["payload"]["trajectories"][0]["recorded_signal_execution_failures"], expected)
        record = replace(make_record("plan_fixture", 0.5, (1.0,)),
            reflection=reflection, trajectories=(trajectory,),
            metrics=score_predictions((trajectory,)), evaluation=None, fitness=None)
        entry = RoundMetaEntry(round_id=1, evidence_refs=(record.plan_id,),
            plan_reflections=(PlanMetaReflection.from_record(record),))
        restored = RoundMetaEntry.from_dict(json.loads(json.dumps(entry.to_dict())))
        self.assertEqual(restored.plan_reflections[0].original_case_reflections[0].to_dict()["recorded_signal_execution_failures"], expected)
        memory = PlanMetaMemory(entries=(restored,))
        catalog = memory.reflection_index().catalog_view(max_bytes=100_000)
        originals = []
        for row in catalog["sources"]:
            source = memory.read_refs((row["source_ref"],), role="signal_mining", max_bytes=100_000)["sources"][0]
            if "recorded_signal_execution_failures" in source["content"]:
                originals.append(source["content"]["recorded_signal_execution_failures"])
        self.assertIn(expected, originals)

        second = replace(make_record("plan_counterexample", 0.5, (0.0, 1.0)),
            trajectories=(self.trajectory(SignalExecutionStatus.DOMAIN_UNAVAILABLE),),
            metrics=score_predictions((trajectory,)), evaluation=None, fitness=None)
        round_caller = PatchCaller(NO_FINDINGS)
        LLMRoundReflector(round_caller).reflect(round_id=1, records=(record, second), prior="Fixed prior.")
        self.assertEqual(len(round_caller.calls), 1)
        self.assertIn("technical execution gaps", round_caller.calls[0]["system_prompt"])

    def test_legacy_missing_diagnostics_remain_unknown_and_domain_gap_is_not_failure(self):
        evidence = CaseReflectionEvidence.from_trajectory(self.trajectory(SignalExecutionStatus.DOMAIN_UNAVAILABLE), case_index=1)
        self.assertEqual(evidence.to_dict()["recorded_signal_execution_failures"], [])
        legacy = evidence.to_dict()
        legacy.pop("recorded_signal_execution_failures")
        restored = CaseReflectionEvidence.from_dict(legacy)
        self.assertIsNone(restored.recorded_signal_execution_failures)
        self.assertNotIn("recorded_signal_execution_failures", restored.to_dict())
        compact = _compact_posthoc_context({"signal_rounds": [{"batch": {"results": [{
            "signal_ref": "fixture_signal:v1", "state": {"value": "unavailable", "confidence": 0},
            "interpretation": {"summary": "Legacy unknown cause."}, "status": {"coverage": "unavailable"},
        }]}}]})
        self.assertNotIn("execution", compact["signal_results"][0])

    def test_diagnostic_rows_validate_identity_status_and_duplicates(self):
        evidence = CaseReflectionEvidence.from_trajectory(self.trajectory(SignalExecutionStatus.VALIDATION_FAILED), case_index=1)
        valid = {"signal_round": 1, "signal_ref": "group:signal_name:v2", "status": "transport_failed"}
        self.assertEqual(replace(evidence, recorded_signal_execution_failures=(valid,)).to_dict()["recorded_signal_execution_failures"], [valid])
        invalid = [
            {**valid, "signal_ref": "Illegal.Name:v2"}, {**valid, "signal_round": True},
            {**valid, "status": []}, {**valid, "status": "domain_unavailable"},
            {**valid, "status": "success"}, {**valid, "unowned": "extra"},
        ]
        for row in invalid:
            with self.subTest(row=row), self.assertRaises(ValidationError):
                replace(evidence, recorded_signal_execution_failures=(row,))
        with self.assertRaises(ValidationError):
            replace(evidence, recorded_signal_execution_failures=(valid, valid))
