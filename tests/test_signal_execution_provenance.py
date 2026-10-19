"""Technical Signal failures survive production prediction and learning views."""

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_core import (
    CaseReflectionEvidence, PlanMetaMemory, PlanMetaReflection, RoundMetaEntry,
    _assemble_final_context, default_information_plan,
)
from stock_opportunity_agent.research.evolution_plan_roles import (
    LLMBlindPredictor, LLMPlanCritic, LLMResearchController, LLMRoundReflector,
    LLMSignalRetrievalAgent,
    _plan_critic_trajectory,
)
from stock_opportunity_agent.research.evolution_output_validation import _compact_posthoc_context
from stock_opportunity_agent.research.scheme_evolution import score_predictions
from stock_opportunity_agent.signal_library import (
    FAILED_SIGNAL_MODEL_SUMMARY, SIGNAL_EXECUTION_STATUS_INSTRUCTION,
    UNKNOWN_UNAVAILABLE_SIGNAL_MODEL_SUMMARY, UNAVAILABLE_SIGNAL_MODEL_SUMMARY,
    SignalBatchResult, SignalCoverage, SignalExecutionStatus, SignalRegistry, SignalResult, SignalValue,
    signal_result_model_view,
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
    def test_posthoc_preserves_actual_answer_disposition_and_does_not_infer_legacy(self):
        recorded = {
            "round": 1,
            "delta": {"decision": "finalize"},
            "need_dispositions": {
                "prior_state_hash": "a" * 64,
                "items": [{
                    "need_index": 0, "prior_need": "Which later-quarter guidance was disclosed?",
                    "answer_scope": "unanswered", "residual_need": None,
                    "evidence_refs": [], "reason": "Only the earlier quarter is visible.",
                }],
            },
        }
        packet = {
            "state_evolution": [recorded, {"round": 2, "delta": {}}],
            "signal_rounds": [{"selections": [{"answer_scope": "full"}]}],
        }
        original = deepcopy(packet)
        compact = _compact_posthoc_context(packet)
        self.assertEqual(compact["state_evolution"], [{
            "round": 1, "need_dispositions": recorded["need_dispositions"],
        }])
        compact["state_evolution"][0]["need_dispositions"]["items"][0]["reason"] = "changed view"
        self.assertEqual(packet, original)
        self.assertEqual(_compact_posthoc_context({
            "signal_rounds": packet["signal_rounds"],
        })["state_evolution"], [])

    def trajectory(self, status):
        trajectory = make_trajectory("opaque_fixture", 1.1, False, None, signal_result=result(status))
        return replace(trajectory, final_context=self.context(trajectory))

    def context(self, trajectory):
        return _assemble_final_context(
            plan=default_information_plan(), company_id=trajectory.company_id,
            additional_identity_aliases=(), basic_info=trajectory.basic_info,
            state=trajectory.final_state, rounds=trajectory.signal_rounds, prediction_time=NOW,
        )

    def test_model_views_preserve_distinct_execution_causes_without_mutating_sources(self):
        for status in SignalExecutionStatus:
            with self.subTest(status=status):
                canonical = result(status).to_dict()
                original = deepcopy(canonical)
                viewed = signal_result_model_view(canonical)
                if status is SignalExecutionStatus.SUCCESS:
                    expected = canonical["interpretation"]["summary"]
                elif status is SignalExecutionStatus.DOMAIN_UNAVAILABLE:
                    expected = UNAVAILABLE_SIGNAL_MODEL_SUMMARY
                else:
                    expected = FAILED_SIGNAL_MODEL_SUMMARY
                self.assertEqual(viewed["interpretation"]["summary"], expected)
                self.assertEqual(viewed["execution"], {"status": status.value})
                self.assertEqual(signal_result_model_view(viewed), viewed)
                self.assertEqual(canonical, original)

        canonical = result(SignalExecutionStatus.DOMAIN_UNAVAILABLE).to_dict()
        for execution in (None, {}, {"status": "legacy_unrecognized"}, {"status": []}, {"status": {}}):
            with self.subTest(execution=execution):
                legacy = deepcopy(canonical)
                if execution is None:
                    legacy.pop("execution")
                else:
                    legacy["execution"] = execution
                original = deepcopy(legacy)
                viewed = signal_result_model_view(legacy)
                self.assertEqual(viewed["interpretation"]["summary"],
                                 UNKNOWN_UNAVAILABLE_SIGNAL_MODEL_SUMMARY)
                if execution is None:
                    self.assertNotIn("execution", viewed)
                else:
                    self.assertEqual(viewed["execution"].get("status"), execution.get("status"))
                self.assertEqual(signal_result_model_view(viewed), viewed)
                self.assertEqual(legacy, original)

    def test_mixed_causes_survive_posthoc_reprojection(self):
        trajectory = self.trajectory(SignalExecutionStatus.DOMAIN_UNAVAILABLE)
        technical = self.trajectory(SignalExecutionStatus.VALIDATION_FAILED)
        trajectory = replace(trajectory, signal_rounds=(
            *trajectory.signal_rounds, *technical.signal_rounds))
        context = self.context(trajectory)
        legacy = deepcopy(context["signal_rounds"][0]["batch"]["results"][0])
        legacy.pop("execution")
        context["signal_rounds"][0]["batch"]["results"].append(legacy)
        original = deepcopy(context)
        compact = _compact_posthoc_context(context)
        self.assertEqual([row["interpretation"]["summary"] for row in compact["signal_results"]], [
            UNAVAILABLE_SIGNAL_MODEL_SUMMARY, UNKNOWN_UNAVAILABLE_SIGNAL_MODEL_SUMMARY,
            FAILED_SIGNAL_MODEL_SUMMARY,
        ])
        self.assertNotIn("execution", compact["signal_results"][1])
        self.assertEqual(context, original)

    def test_native_reflect_uses_explicit_status_instruction(self):
        trajectory = self.trajectory(SignalExecutionStatus.DOMAIN_UNAVAILABLE)

        def response(request):
            contract = request["payload"]["output_patch_contract"]
            return {"base_hash": contract["base_hash"], "operations": []}

        caller = PatchCaller(response)
        reflected = LLMResearchController(caller).reflect(
            default_information_plan(), trajectory.final_state,
            SignalBatchResult(results=(result(SignalExecutionStatus.DOMAIN_UNAVAILABLE),), signal_calls=1),
        )
        self.assertEqual(reflected.value, trajectory.final_state)
        self.assertEqual(len(caller.calls), 1)
        self.assertIn(SIGNAL_EXECUTION_STATUS_INSTRUCTION, caller.calls[0]["system_prompt"])
        self.assertNotIn("unavailable Signal is only a coverage diagnostic", caller.calls[0]["system_prompt"])

    def test_actual_routing_history_retains_cause_without_private_diagnostics(self):
        with TemporaryDirectory() as directory:
            registry = SignalRegistry(Path(directory) / "signals")
            registry.install_catalog(Path(__file__).resolve().parents[1] / "configs/signals_v1.json")
            for status in (SignalExecutionStatus.DOMAIN_UNAVAILABLE, SignalExecutionStatus.VALIDATION_FAILED):
                with self.subTest(status=status):
                    caller = PatchCaller({"selections": []})
                    raw = result(status, "cash_reserves").to_dict()
                    original = deepcopy(raw)
                    LLMSignalRetrievalAgent(caller).select(
                        ("Unspecified issuer evidence facet.",), registry.freeze(),
                        {"cash_reserves:v1": ()}, {"cash_reserves:v1": raw},
                        ("revenue_growth_yoy:v1",),
                    )
                    self.assertEqual(len(caller.calls), 1)
                    call = caller.calls[0]
                    card = call["payload"]["previous_signal_results"]["cash_reserves:v1"]
                    self.assertEqual(card["execution"], {"status": status.value})
                    self.assertIn(SIGNAL_EXECUTION_STATUS_INSTRUCTION, call["system_prompt"])
                    self.assertNotIn("could not find its required data", call["system_prompt"])
                    self.assertNotIn("LOCAL_DIAGNOSTIC_SENTINEL", json.dumps(call))
                    self.assertEqual(raw, original)

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
            self.assertIn(SIGNAL_EXECUTION_STATUS_INSTRUCTION, call["system_prompt"])
            self.assertNotIn("LOCAL_DIAGNOSTIC_SENTINEL", json.dumps(call))

    def test_actual_critic_request_and_persisted_round_slow_read_retain_failures(self):
        trajectory = self.trajectory(SignalExecutionStatus.VALIDATION_FAILED)
        caller = PatchCaller(NO_FINDINGS)
        reflection = LLMPlanCritic(caller).critique(
            plan=default_information_plan(), trajectories=(trajectory,),
            metrics=score_predictions((trajectory,)),
        )
        expected = [{"signal_round": 1, "signal_ref": "fixture_signal:v1", "status": "validation_failed"}]
        self.assertIn(SIGNAL_EXECUTION_STATUS_INSTRUCTION, caller.calls[0]["system_prompt"])
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
        self.assertIn(SIGNAL_EXECUTION_STATUS_INSTRUCTION, round_caller.calls[0]["system_prompt"])

    def test_legacy_missing_diagnostics_remain_unknown_and_domain_gap_is_not_failure(self):
        evidence = CaseReflectionEvidence.from_trajectory(self.trajectory(SignalExecutionStatus.DOMAIN_UNAVAILABLE), case_index=1)
        self.assertEqual(evidence.to_dict()["recorded_signal_execution_failures"], [])
        legacy = evidence.to_dict()
        legacy.pop("recorded_signal_execution_failures")
        restored = CaseReflectionEvidence.from_dict(legacy)
        self.assertIsNone(restored.recorded_signal_execution_failures)
        self.assertNotIn("recorded_signal_execution_failures", restored.to_dict())
        compact = _compact_posthoc_context({"prediction_time": NOW.isoformat(), "signal_rounds": [{"batch": {"results": [{
            "signal_ref": "fixture_signal:v1", "state": {"value": "unavailable", "confidence": 0},
            "interpretation": {"summary": "Legacy unknown cause."}, "status": {"coverage": "unavailable"},
            "evidence": {"supporting": [], "counter": []},
        }]}}]})
        self.assertNotIn("execution", compact["signal_results"][0])
        self.assertEqual(compact["signal_results"][0]["interpretation"]["summary"],
                         UNKNOWN_UNAVAILABLE_SIGNAL_MODEL_SUMMARY)

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

    def test_legacy_trajectory_keeps_source_hashes_through_saved_plan_and_round_index(self):
        from stock_opportunity_agent.research.evolution_core import PlanRecord
        from stock_opportunity_agent.research.evolution_reflection_memory import ReflectionMemoryIndex
        from tests.test_evolution_reflection_memory import authored

        legacy = make_trajectory("legacy_fixture", 1.1, False, None,
            signal_result=result(SignalExecutionStatus.VALIDATION_FAILED))
        # The old producer never put execution into final_context. Its absent
        # source identity also makes the legacy case ref depend on the full row.
        self.assertIsNone(legacy.self_reflection.source_identity)
        original = CaseReflectionEvidence.from_trajectory(legacy, case_index=1).to_dict()
        self.assertNotIn("recorded_signal_execution_failures", original)

        def response(request):
            source = next(row for row in request["payload"]["source_catalog"]
                if row.get("statistics", {}).get("group") == "technical_completion")
            item = authored(source, category="repeated_failure_modes")
            item.update(kind="fact", brief="technical_completion_rate=1.",
                        detail="Observed technical_completion_rate=1.")
            return {"reflection_items": [item], "selected_reflection_refs": [], "no_findings_reason": None}

        plan = default_information_plan()
        caller = PatchCaller(response)
        reflection = LLMPlanCritic(caller).critique(plan=plan, trajectories=(legacy,),
            metrics=score_predictions((legacy,)))
        self.assertEqual(len(reflection.reflection_items), 1)
        record = replace(make_record(plan.plan_id, 0.5, (1.0,)), plan=plan,
            trajectories=(legacy,), reflection=reflection, metrics=score_predictions((legacy,)),
            evaluation=None, fitness=None)
        restored = PlanRecord.from_dict(json.loads(json.dumps(record.to_dict())))
        row = PlanMetaReflection.from_record(restored)
        self.assertEqual(row.original_case_reflections[0].to_dict(), original)
        index = ReflectionMemoryIndex.from_plan_rows((row.to_model_dict(),), owner_ref="round:legacy")
        item = reflection.reflection_items[0]
        self.assertEqual(index.read_refs((item.item_ref,), role="signal_mining")["sources"][0]["content"], item.to_dict())
        ref = item.source_refs[0]
        self.assertIn(ref, [source["source_ref"] for source in index.source_catalog()])

    def test_only_complete_matching_saved_statuses_emit_diagnostics(self):
        from copy import deepcopy

        trajectory = self.trajectory(SignalExecutionStatus.TRANSPORT_FAILED)
        for mutation in ("missing", "wrong_ref", "wrong_status", "missing_round"):
            context = deepcopy(trajectory.final_context)
            card = context["signal_rounds"][0]["batch"]["results"][0]
            if mutation == "missing":
                card.pop("execution")
            elif mutation == "wrong_ref":
                card["signal_ref"] = "other_signal:v1"
            elif mutation == "wrong_status":
                card["execution"]["status"] = "domain_unavailable"
            else:
                context["signal_rounds"] = []
            with self.subTest(mutation=mutation):
                legacy = CaseReflectionEvidence.from_trajectory(replace(trajectory, final_context=context), case_index=1)
                self.assertIsNone(legacy.recorded_signal_execution_failures)
                self.assertNotIn("recorded_signal_execution_failures", legacy.to_dict())
        self.assertEqual(CaseReflectionEvidence.from_trajectory(trajectory, case_index=1).to_dict()[
            "recorded_signal_execution_failures"], [{"signal_round": 1, "signal_ref": "fixture_signal:v1", "status": "transport_failed"}])

    def test_empty_old_round_has_no_recorded_status_evidence(self):
        from stock_opportunity_agent.signal_library import SignalBatchResult
        from stock_opportunity_agent.research.evolution_core import SignalRound

        trajectory = self.trajectory(SignalExecutionStatus.DOMAIN_UNAVAILABLE)
        empty = SignalRound(selections=(), information_needs=(), batch=SignalBatchResult(
            results=(), signal_calls=0))
        trajectory = replace(trajectory, signal_rounds=(empty,), final_context={
            "signal_rounds": [{"selected_signals": [], "batch": {"results": [], "signal_calls": 0}}]})
        evidence = CaseReflectionEvidence.from_trajectory(trajectory, case_index=1)
        self.assertNotIn("recorded_signal_execution_failures", evidence.to_dict())
