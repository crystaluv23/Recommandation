"""Bounded diagnostic guards and consumer wiring; no model compliance claims."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from stock_opportunity_agent.artifacts import atomic_write_json, canonical_json_hash
from stock_opportunity_agent.llm.agent import AgentUsage
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_core import (
    AgentStep, BlindPrediction, CandidateJudgment, ConfidenceLevel, ExecutionTrajectory,
    GroundTruth, PredictionSelfReflection, ResearchDecision, ResearchEvidenceRef,
    ResearchState, RuntimeStopReason, RuntimeUsage, SignalRound, SignalSelectionDecision,
    default_information_plan,
)
from stock_opportunity_agent.signal_library import SignalBatchResult, SignalCoverage, SignalEvidence, SignalResult, SignalValue

_SPEC = importlib.util.spec_from_file_location("scope_diagnostic_test_module", Path(__file__).resolve().parents[1] / "scripts/diagnose_executed_answer_scope.py")
diag = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = diag
_SPEC.loader.exec_module(diag)


class ExecutedAnswerScopeDiagnosticTests(TestCase):
    """Use explicit synthetic artifacts and real no-network request preparation."""

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.now = datetime(2025, 9, 30, tzinfo=timezone.utc)
        self.need = "What Q3 revenue guidance did Example Corporation disclose?"
        self.other = "What capital expenditure is planned?"
        self.prior = ResearchState(next_information_needs=(self.need, self.other, self.other))
        self.selection = SignalSelectionDecision(
            signal_ref="guidance_acceleration:v3", reason_code="answer_need", selection_reason="Guidance request.",
            applicability_hypothesis="Guidance may cover the need.", expected_role="primary", context_tags=("general",),
            target_need_indices=(0,), answer_scope="full",
        )
        self.result = SignalResult(
            signal_id="guidance_acceleration", version=3, value=SignalValue.NEUTRAL, confidence=0.5,
            interpretation="Only Q2 guidance is disclosed.", coverage=SignalCoverage.PARTIAL,
            supporting_evidence=(SignalEvidence(document_id="source", exact_span="Q2 revenue outlook is unchanged.", timestamp=self.now),),
        )
        self.round = SignalRound(information_needs=self.prior.next_information_needs, selections=(self.selection,),
                                 batch=SignalBatchResult(results=(self.result,), signal_calls=1))
        self.plan = default_information_plan()
        controller = diag.LLMResearchController(None)
        controller.set_evaluation_context(self.now)
        trajectory = ExecutionTrajectory(
            company_id="synthetic_company", prediction_time=self.now, basic_info={"requests": []},
            initial_state=self.prior, signal_rounds=(self.round,), final_state=self.prior, final_context={},
            prediction=BlindPrediction(False, CandidateJudgment.INSUFFICIENT_INFORMATION, None, ConfidenceLevel.LOW,
                                       ("Synthetic historical artifact only.",), (), "synthetic"),
            prediction_ref="synthetic/prediction", ground_truth=GroundTruth(1.0),
            self_reflection=PredictionSelfReflection(correct=True), stop_reason=RuntimeStopReason.BUDGET_EXHAUSTED,
            usage=RuntimeUsage(1, 1, AgentUsage()),
        )
        source = self.base / "synthetic-trajectory.json"
        atomic_write_json(source, {"trajectory": trajectory.to_dict()})
        seed = {
            "sample_id": "synthetic_a", "company_id": "synthetic_company", "case_id": "synthetic_case",
            "prediction_time": self.now.isoformat(), "identity": {"company_name": "Example Corporation", "identity_aliases": ["Example Corporation"]},
            "plan": self.plan.to_dict(), "prior_state": self.prior.to_dict(), "signal_round": self.round.to_dict(),
            "target_need_index": 0, "target_need": self.need, "original_trajectory": diag.binding(source),
            "evaluation_context": controller.evaluation_context, "evaluation_anchor": None,
            "reflection_runtime": {"must_finalize": False, "termination_trigger": None},
            "closure_runtime": {"must_finalize": True, "termination_trigger": "budget_exhausted"},
            "closure_estimate_state": self.prior.to_dict(), "computed_metric_cards": [], "computed_metrics": [],
            "signal_research_status": {}, "basic_info": {"requests": []}, "prediction_baseline": {"status": "unavailable"},
        }
        # Real production construction supplies a synthetic prior-wire original; no model response is generated.
        ledger = diag.ExternalAttemptLedger(self.base / "seed-attempts.json", max_attempts=8, max_total_cost=.25)
        client = diag.BoundedReflectClient(registration=diag.get_model(diag.MODEL), contract=diag.StageContract({"limits": {}}),
                                           workspace=self.base / "seed", ledger=ledger, allow_external=False, environ={})
        with self.assertRaises(diag.ExternalRequestPending) as caught:
            diag._reflect(client, seed)
        request = diag.read_json(caught.exception.request_path)["request"]
        payload = json.loads(request["messages"][1]["content"])
        seed["original_initial_context"] = {key: payload.get(key) for key in diag.PRESERVED_PAYLOAD_FIELDS}
        second = deepcopy(seed)
        second["sample_id"] = "synthetic_b"
        self.inputs = {"schema_version": "synthetic", "samples": [seed, second]}
        self.originals = [diag.binding(source)]
        self.root = self.base / "diagnostic"

    def preview(self):
        with patch.object(diag, "_source_inputs", return_value=(self.inputs, self.originals)), \
                patch.object(diag, "_load_execution_environment", side_effect=AssertionError("preview loaded environment")):
            return diag.preview(self.root)

    def scripted_step(self, _client, sample, *, state=None, closure=False):
        """Synthetic accepted state is used only to test save/reload/consumer wiring."""
        previous = state or self.prior
        if closure:
            current = replace(previous, decision=ResearchDecision.FINALIZE)
            items = []
        else:
            current = replace(previous, supporting_evidence=(ResearchEvidenceRef(
                kind="signal", claim=self.result.supporting_evidence[0].exact_span,
                signal_ref=self.result.ref, evidence_group="supporting", evidence_index=0),))
            items = [{"need_index": 0, "prior_need": self.need, "answer_scope": "unanswered", "residual_need": None,
                      "evidence_refs": [], "reason": "Example Corporation disclosed Q2 only."}]
        return AgentStep(current, metadata={"need_dispositions": {"prior_state_hash": canonical_json_hash(previous.to_dict()), "items": items}})

    def test_preview_real_request_builds_four_requests_without_attempt_or_environment(self):
        result = self.preview()
        self.assertEqual(result["external_attempts"], 0)
        self.assertEqual(len(result["initial_requests"]), 2)
        self.assertEqual(len(result["closure_estimates"]), 2)
        self.assertTrue(all(all(row["preserved_original_context"].values()) for row in result["initial_requests"]))
        diag.verify_preview(self.root, result["manifest_hash"])
        with self.assertRaises(ValidationError):
            diag.preview(self.root)

    def test_original_wire_difference_is_rejected(self):
        self.inputs["samples"][0]["original_initial_context"]["reflection_runtime"]["must_finalize"] = True
        with self.assertRaisesRegex(ValidationError, "differs from the original"):
            self.preview()

    def test_frozen_code_inventory_and_input_changes_refuse_before_environment(self):
        result = self.preview()
        with patch.object(diag, "_code_bindings", return_value=[]):
            with self.assertRaisesRegex(ValidationError, "code inventory"):
                diag.verify_preview(self.root, result["manifest_hash"])
        frozen = diag.read_json(self.root / "inputs.json")
        frozen["samples"][0]["target_need"] = "changed"
        atomic_write_json(self.root / "inputs.json", frozen)
        with patch.object(diag, "_load_execution_environment", side_effect=AssertionError("unsafe env load")):
            with self.assertRaisesRegex(ValidationError, "input bundle changed"):
                diag.execute(self.root, result["manifest_hash"])

    def test_execute_persist_reload_both_stages_and_actual_consumers(self):
        preview = self.preview()
        with patch.object(diag, "_load_execution_environment"), patch.object(diag, "_reflect", side_effect=self.scripted_step):
            result = diag.execute(self.root, preview["manifest_hash"])
        self.assertTrue(result["passed"], result)
        artifact = diag.read_json(self.root / "consumers/synthetic_a.json")
        self.assertEqual(len(artifact["state_deltas"]), 2)
        self.assertIn("Example Corporation", artifact["state_deltas"][0]["need_dispositions"]["items"][0]["reason"])
        self.assertNotIn("Example Corporation", artifact["final_context"]["state_evolution"][0]["need_dispositions"]["items"][0]["reason"])
        self.assertFalse(artifact["actual_prediction_executed"])
        with self.assertRaisesRegex(ValidationError, "already executed"):
            diag.verify_preview(self.root, preview["manifest_hash"])

    def test_saved_hash_and_dropped_duplicate_occurrence_are_rejected(self):
        preview = self.preview()
        with patch.object(diag, "_load_execution_environment"), patch.object(diag, "_reflect", side_effect=self.scripted_step):
            diag.execute(self.root, preview["manifest_hash"])
        path = self.root / "samples/synthetic_a/terminal_closure.json"
        saved = diag.read_json(path)
        original = deepcopy(saved)
        saved["metadata"]["need_dispositions"]["prior_state_hash"] = "bad"
        atomic_write_json(path, saved)
        with self.assertRaisesRegex(ValidationError, "exact prior"):
            diag.assemble_consumers(self.root, self.inputs["samples"][0])
        original["state"]["next_information_needs"].pop()
        atomic_write_json(path, original)
        with self.assertRaises(ValidationError):
            diag.assemble_consumers(self.root, self.inputs["samples"][0])

    def test_native_corrections_share_one_allowance(self):
        for correction in ("research_controller_reflect_correction", "research_controller_reflect_patch_mechanics_correction"):
            client = object.__new__(diag.BoundedReflectClient)
            client.logical_calls = 0
            with patch.object(diag.StructuredRoleClient, "complete_json", return_value=None) as call:
                client.complete_json(stage="research_controller_reflect")
                client.complete_json(stage=correction)
                with self.assertRaises(ValidationError):
                    client.complete_json(stage="research_controller_reflect_correction")
                self.assertEqual(call.call_count, 2)

    def test_readable_metrics_preserve_values_and_clause_multiplicity(self):
        first = [{"readable": "metric: x 1; y 2; y 2"}]
        same = [{"readable": "metric: y 2; x 1; y 2"}]
        wrong = [{"readable": "metric: x 1; y 2"}]
        self.assertEqual(diag._readable_identity(first), diag._readable_identity(same))
        self.assertNotEqual(diag._readable_identity(first), diag._readable_identity(wrong))
