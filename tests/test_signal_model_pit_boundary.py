"""Reject the actual v3 late-result fault before any model-facing projection."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime
import json
from pathlib import Path
import sys
import tempfile
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from diagnose_executed_answer_scope import StageContract, _reflect
from stock_opportunity_agent.llm import get_model
from stock_opportunity_agent.research.evolution_core import (
    ExecutionTrajectory, InformationPlan, ResearchState, SignalRound, _assemble_final_context,
)
from stock_opportunity_agent.research.evolution_output_validation import _compact_posthoc_context
from stock_opportunity_agent.research.evolution_plan_roles import _plan_critic_trajectory, LLMBlindPredictor
from stock_opportunity_agent.research.evolution_transport import StructuredRoleClient, ExternalAttemptLedger
from stock_opportunity_agent.research.local_role_exchange import LocalRoleExchange, LocalRoleRequestPending
from stock_opportunity_agent.signal_library import require_signal_result_pit, SignalModelInputRejected
from stock_opportunity_agent.models import ValidationError


BATCH = ROOT / "runs/diagnostics/local_roles_mvp_20261019_v3"


def frozen_sample(name):
    return next(row for row in json.loads((BATCH / "inputs.json").read_text())["samples"] if row["sample_id"] == name)


def assembled(sample):
    state = json.loads((BATCH / "samples" / sample["sample_id"] / "initial_reflect.json").read_text())["state"]
    return _assemble_final_context(plan=InformationPlan.from_dict(sample["plan"]), company_id=sample["company_id"],
        additional_identity_aliases=tuple(sample["identity"].get("identity_aliases", ())),
        basic_info=sample["basic_info"], state=ResearchState.from_dict(state),
        rounds=(SignalRound.from_dict(sample["signal_round"]),),
        prediction_time=datetime.fromisoformat(sample["prediction_time"]), prediction_baseline=sample["prediction_baseline"],
        state_deltas=(), computed_metrics=sample["computed_metric_cards"], signal_research_status=sample["signal_research_status"])


def local_client(root):
    return StructuredRoleClient(registration=get_model("independent-subagent"),
        contract=StageContract(json.loads((BATCH / "contract.json").read_text())), workspace=root,
        ledger=ExternalAttemptLedger(root / "attempts.json", max_attempts=1, max_total_cost=1),
        local_role_exchange=LocalRoleExchange(root / "exchange", max_calls=1), allow_external=False, environ={})


class SignalModelPITBoundaryTests(TestCase):
    def test_actual_reflect_rejects_late_result_before_local_role_dispatch(self):
        sample = frozen_sample("future_actual")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            client = StructuredRoleClient(registration=get_model("independent-subagent"),
                contract=StageContract(json.loads((BATCH / "contract.json").read_text())), workspace=root,
                ledger=ExternalAttemptLedger(root / "attempts.json", max_attempts=1, max_total_cost=1),
                local_role_exchange=LocalRoleExchange(root / "exchange", max_calls=1), allow_external=False, environ={})
            with self.assertRaisesRegex(SignalModelInputRejected, "signal_input_pit") as rejected:
                _reflect(client, sample)
            self.assertNotIsInstance(rejected.exception, ValidationError)
            self.assertFalse(list((root / "exchange/inbox").glob("*.json")))
            self.assertEqual(client.request_hash_trace, [])
            self.assertEqual(client.ledger.summary["attempt_count"], 0)

    def test_malformed_evidence_cannot_claim_canonical_time_qualification(self):
        cutoff = datetime.fromisoformat("2025-09-30T00:00:00+00:00")
        for evidence in (None, {}, {"supporting": []}, {"supporting": None, "counter": []},
                         {"supporting": [], "counter": {}}, {"supporting": [{}], "counter": []}):
            with self.subTest(evidence=evidence), self.assertRaises(SignalModelInputRejected):
                require_signal_result_pit({"signal_id": "test", "version": 1, "evidence": evidence}, as_of=cutoff)
        self.assertEqual(require_signal_result_pit({"signal_id": "test", "version": 1,
            "evidence": {"supporting": [], "counter": []}}, as_of=cutoff), [])

    def test_counter_evidence_and_equivalent_zones_use_actual_instant(self):
        raw = frozen_sample("future_forecast")["signal_round"]["batch"]["results"][0]
        cutoff = datetime.fromisoformat("2025-09-30T00:00:00Z")
        raw["evidence"]["counter"] = [{"timestamp": "2025-09-30T08:00:01+08:00"}]
        with self.assertRaisesRegex(SignalModelInputRejected, "counter"):
            require_signal_result_pit(raw, as_of=cutoff)
        raw["evidence"]["counter"][0]["timestamp"] = "2025-09-30T08:00:00+08:00"
        self.assertEqual(len(require_signal_result_pit(raw, as_of=cutoff)), 2)

    def test_empty_canonical_evidence_does_not_hide_late_runtime_binding(self):
        context = json.loads((BATCH / "consumers/future_actual.json").read_text())["final_context"]
        card = context["signal_rounds"][0]["batch"]["results"][0]
        card["evidence"] = {"supporting": [], "counter": []}
        for binding in (["2025-11-10T12:00:00+00:00"], None, ["unknown"]):
            card["input_evidence_available_at"] = binding
            with self.subTest(binding=binding), self.assertRaises(SignalModelInputRejected):
                _compact_posthoc_context(context)

    def test_coexisting_binding_is_exact_ordered_copy_of_canonical_instants(self):
        raw = frozen_sample("future_forecast")["signal_round"]["batch"]["results"][0]
        cutoff = datetime.fromisoformat("2025-09-30T00:00:00Z")
        raw["evidence"]["counter"] = [{"timestamp": "2025-06-26T00:00:00Z"}]
        exact = ["2025-06-25T20:00:00+08:00", "2025-06-26T00:00:00Z"]
        raw["input_evidence_available_at"] = exact
        self.assertEqual(len(require_signal_result_pit(raw, as_of=cutoff)), 2)
        for binding in ([], exact[:1], exact[::-1], exact + exact[:1], [exact[0], "2025-06-27T00:00:00Z"]):
            raw["input_evidence_available_at"] = binding
            with self.subTest(binding=binding), self.assertRaises(SignalModelInputRejected):
                require_signal_result_pit(raw, as_of=cutoff)

    def test_actual_final_context_rejects_original_late_result(self):
        with self.assertRaisesRegex(RuntimeError, "signal_input_pit"):
            assembled(frozen_sample("future_actual"))

    def test_legacy_leaking_compact_card_cannot_be_consumed_without_time_binding(self):
        context = json.loads((BATCH / "consumers/future_actual.json").read_text())["final_context"]
        with self.assertRaisesRegex(RuntimeError, "signal_input_pit"):
            _compact_posthoc_context(context)

    def test_direct_predictor_rejects_old_card_before_caller(self):
        context = json.loads((BATCH / "consumers/future_actual.json").read_text())["final_context"]
        original = deepcopy(context)
        with tempfile.TemporaryDirectory() as directory:
            client = local_client(Path(directory))
            predictor = LLMBlindPredictor(client)
            for entry in (predictor.estimate_prediction_tokens, predictor.predict):
                with self.subTest(entry=entry.__name__), self.assertRaises(SignalModelInputRejected):
                    entry(context)
            self.assertEqual(client.request_hash_trace, [])
            self.assertFalse(list((Path(directory) / "exchange/inbox").glob("*.json")))
        self.assertEqual(context, original)

    def test_actual_posthoc_role_propagates_input_rejection_without_fallback(self):
        sample = frozen_sample("future_actual")
        original = ExecutionTrajectory.from_dict(json.loads(Path(sample["original_trajectory"]["path"]).read_text())["trajectory"])
        context = json.loads((BATCH / "consumers/future_actual.json").read_text())["final_context"]
        with tempfile.TemporaryDirectory() as directory:
            client = local_client(Path(directory))
            with self.assertRaises(SignalModelInputRejected):
                LLMBlindPredictor(client).reflect(context, original.prediction, original.ground_truth)
            self.assertEqual(client.request_hash_trace, [])

    def test_legal_rebuilt_context_reaches_actual_predictor_caller(self):
        context = assembled(frozen_sample("future_forecast"))
        with tempfile.TemporaryDirectory() as directory:
            client = local_client(Path(directory))
            with self.assertRaises(LocalRoleRequestPending):
                LLMBlindPredictor(client).predict(context)
            inbox = list((Path(directory) / "exchange/inbox").glob("*.json"))
            self.assertEqual(len(inbox), 1)
            request = json.loads(inbox[0].read_text())
            self.assertIn("input_evidence_available_at", json.dumps(request))
            self.assertIn("$140 million", json.dumps(request))

    def test_missing_cutoff_and_missing_legacy_binding_refuse_new_consumption(self):
        context = assembled(frozen_sample("future_forecast"))
        del context["prediction_time"]
        with self.assertRaisesRegex(SignalModelInputRejected, "prediction_time"):
            _compact_posthoc_context(context)

    def test_diagnostic_uses_real_entrypoints_without_answering_roles(self):
        from diagnose_signal_model_pit_boundary import diagnose
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "new-evidence"
            result = diagnose(BATCH, output)
            self.assertTrue(result["boundary_checks_passed"])
            self.assertEqual(result["fixed_sample_denominator"], 7)
            self.assertEqual(result["negative_new_inbox_count"], 0)
            self.assertEqual(len(result["legal_consumer_outcomes"]), 6)
            self.assertEqual(result["new_independent_role_responses"], 0)
            with self.assertRaisesRegex(ValueError, "must be new"):
                diagnose(BATCH, output)

    def test_actual_critic_rejects_original_late_result(self):
        sample = frozen_sample("future_actual")
        original = ExecutionTrajectory.from_dict(json.loads(Path(sample["original_trajectory"]["path"]).read_text())["trajectory"])
        injected = replace(original, signal_rounds=(SignalRound.from_dict(sample["signal_round"]),))
        with self.assertRaisesRegex(RuntimeError, "signal_input_pit"):
            _plan_critic_trajectory(injected, case_index=1)

    def test_legal_future_forecast_keeps_content_and_all_consumers(self):
        sample = frozen_sample("future_forecast")
        context = assembled(sample)
        card = context["signal_rounds"][0]["batch"]["results"][0]
        self.assertIn("$140 million", card["interpretation"]["summary"])
        self.assertEqual(card["input_evidence_available_at"], ["2025-06-25T12:00:00+00:00"])
        compact = _compact_posthoc_context(context)
        self.assertIn("$140 million", compact["signal_results"][0]["interpretation"]["summary"])
        original = ExecutionTrajectory.from_dict(json.loads(Path(sample["original_trajectory"]["path"]).read_text())["trajectory"])
        injected = replace(original, signal_rounds=(SignalRound.from_dict(sample["signal_round"]),), final_context=context)
        self.assertIn("$140 million", _plan_critic_trajectory(injected, case_index=1)["signal_rounds"][0]["signal_results"][0]["interpretation"]["summary"])
