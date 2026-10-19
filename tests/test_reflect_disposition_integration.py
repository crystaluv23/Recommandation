"""Native Reflect patches bind actual answers to provenance and downstream views."""

from dataclasses import replace
from datetime import datetime, timezone
from unittest import TestCase

from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.models import StructuredValidationError
from stock_opportunity_agent.research.evolution_core import (
    ResearchState, SignalSelectionDecision, default_information_plan,
)
from stock_opportunity_agent.research.evolution_plan_roles import LLMResearchController
from stock_opportunity_agent.research.evolution_research_validation import (
    raw_need_disposition_issues, validate_need_dispositions,
)
from stock_opportunity_agent.signal_library import (
    SignalBatchResult, SignalCoverage, SignalEvidence, SignalResult, SignalValue,
)
from tests.test_evolution_state_patch import PatchCaller, patch


class ReflectDispositionIntegrationTests(TestCase):
    def inputs(self):
        prior = ResearchState(next_information_needs=("What revenue and margin guidance is available?",))
        selection = SignalSelectionDecision(
            signal_ref="guidance_acceleration:v1", reason_code="answer_need",
            selection_reason="Expected to answer the complete guidance question.",
            applicability_hypothesis="Guidance may be available.",
            expected_role="primary", target_need_indices=(0,), answer_scope="full",
        )
        result = SignalResult(
            signal_id="guidance_acceleration", version=1, value=SignalValue.NEUTRAL,
            confidence=0.8, interpretation="Revenue guidance was reaffirmed.",
            coverage=SignalCoverage.SUFFICIENT,
            supporting_evidence=(SignalEvidence(document_id="guidance-document",
                exact_span="Revenue guidance was reaffirmed.",
                timestamp=datetime(2025, 8, 1, tzinfo=timezone.utc)),),
        )
        return prior, selection, SignalBatchResult(results=(result,), signal_calls=1)

    def controller(self, caller, selection):
        controller = LLMResearchController(caller)
        controller.set_reflection_runtime_context(
            selections=(selection,), must_finalize=False, termination_trigger=None,
        )
        return controller

    def test_native_actual_partial_overrides_full_expectation_and_sufficient_coverage(self):
        prior, selection, batch = self.inputs()
        residual = "What margin guidance is available?"
        evidence = {"signal_ref": selection.signal_ref, "evidence_group": "supporting", "evidence_index": 0}
        row = {"need_index": 0, "answer_scope": "partial", "residual_need": residual,
               "evidence_refs": [evidence], "reason": "Revenue guidance is present; margin guidance is absent."}

        def native(call):
            return patch(call["payload"]["output_patch_contract"],
                {"op": "append", "path": "supporting_evidence", "value": {
                    "kind": "signal", "claim": "Revenue guidance was reaffirmed.", **evidence}},
                {"op": "replace", "path": "next_information_needs[0]", "value": residual},
                {"op": "append", "path": "need_dispositions", "value": row},
            )

        caller = PatchCaller(native)
        result = self.controller(caller, selection).reflect(default_information_plan(), prior, batch)
        self.assertEqual(len(caller.calls), 1)
        self.assertEqual(result.value.next_information_needs, (residual,))
        self.assertNotIn("need_dispositions", result.value.to_dict())
        self.assertEqual(result.metadata, {"need_dispositions": {
            "prior_state_hash": canonical_json_hash(prior.to_dict()),
            "items": [{**row, "prior_need": prior.next_information_needs[0]}],
        }})
        self.assertEqual(caller.calls[0]["payload"]["executed_selection_intents"][0].get("answer_scope", "full"), "full")

    def test_native_missing_disposition_requires_row_and_preserves_other_state(self):
        prior, selection, batch = self.inputs()
        row = {"need_index": 0, "answer_scope": "unanswered", "residual_need": None,
               "evidence_refs": [], "reason": "No answer evidence was adopted."}

        def repair(call):
            permissions = call["payload"]["output_patch_contract"]["allowed_operations"]
            self.assertTrue(any(p["path"] == "need_dispositions" and p["op"] == "append" for p in permissions))
            self.assertFalse(any(p["path"].startswith("hypotheses") for p in permissions))
            return patch(call["payload"]["output_patch_contract"],
                {"op": "append", "path": "need_dispositions", "value": row})

        caller = PatchCaller(lambda call: patch(call["payload"]["output_patch_contract"]), repair)
        result = self.controller(caller, selection).reflect(default_information_plan(), prior, batch)
        self.assertEqual(len(caller.calls), 2)
        self.assertEqual(result.value, prior)
        self.assertEqual(result.metadata["need_dispositions"]["items"], [{**row, "prior_need": prior.next_information_needs[0]}])

    def test_partial_measurement_can_fully_answer_narrow_question(self):
        prior, selection, batch = self.inputs()
        prior = replace(prior, next_information_needs=("Was revenue guidance reaffirmed?",))
        batch = replace(batch, results=(replace(batch.results[0], coverage=SignalCoverage.PARTIAL),))
        ref = {"signal_ref": selection.signal_ref, "evidence_group": "supporting", "evidence_index": 0}
        row = {"need_index": 0, "answer_scope": "full", "residual_need": None,
               "evidence_refs": [ref], "reason": "The narrow revenue-guidance question is answered exactly."}
        caller = PatchCaller(lambda call: patch(call["payload"]["output_patch_contract"],
            {"op": "append", "path": "supporting_evidence", "value": {
                "kind": "signal", "claim": "Revenue guidance was reaffirmed.", **ref}},
            {"op": "remove", "path": "next_information_needs[0]"},
            {"op": "replace", "path": "decision", "value": "finalize"},
            {"op": "append", "path": "need_dispositions", "value": row},
        ))
        result = self.controller(caller, selection).reflect(default_information_plan(), prior, batch)
        self.assertEqual(result.value.next_information_needs, ())
        self.assertEqual(result.metadata["need_dispositions"]["items"][0]["answer_scope"], "full")

    def test_multiple_missing_dispositions_fit_one_native_correction(self):
        prior, selection, batch = self.inputs()
        prior = replace(prior, next_information_needs=("What revenue guidance is available?", "What margin guidance is available?"))
        second_selection = replace(selection, signal_ref="margin_guidance:v1", target_need_indices=(1,))
        batch = replace(batch, results=(*batch.results, replace(batch.results[0], signal_id="margin_guidance")), signal_calls=2)
        rows = [{"need_index": index, "answer_scope": "unanswered", "residual_need": None,
                 "evidence_refs": [], "reason": "No answer evidence was adopted for this occurrence."}
                for index in (0, 1)]
        caller = PatchCaller(
            lambda call: patch(call["payload"]["output_patch_contract"]),
            lambda call: patch(call["payload"]["output_patch_contract"], *[
                {"op": "append", "path": "need_dispositions", "value": row} for row in rows]),
        )
        controller = self.controller(caller, selection)
        controller.set_reflection_runtime_context(
            selections=(selection, second_selection), must_finalize=False, termination_trigger=None,
        )
        result = controller.reflect(default_information_plan(), prior, batch)
        self.assertEqual(len(caller.calls), 2)
        self.assertEqual(result.value, prior)
        self.assertEqual([row["need_index"] for row in result.metadata["need_dispositions"]["items"]], [0, 1])

    def test_invalid_disposition_is_repaired_before_success_metadata_is_retained(self):
        prior, selection, batch = self.inputs()
        invalid = {"need_index": 0, "answer_scope": "unanswered", "residual_need": None,
                   "evidence_refs": [], "reason": ""}
        caller = PatchCaller(
            lambda call: patch(call["payload"]["output_patch_contract"],
                {"op": "append", "path": "need_dispositions", "value": invalid}),
            lambda call: patch(call["payload"]["output_patch_contract"],
                {"op": "replace", "path": "need_dispositions[0].reason", "value": "No answer evidence was adopted."}),
        )
        result = self.controller(caller, selection).reflect(default_information_plan(), prior, batch)
        self.assertEqual(len(caller.calls), 2)
        self.assertEqual(result.value, prior)
        self.assertEqual(result.metadata["need_dispositions"]["items"][0]["reason"], "No answer evidence was adopted.")
        self.assertEqual(invalid["reason"], "")

    def test_anchor_and_missing_disposition_share_one_native_correction_frontier(self):
        prior, selection, batch = self.inputs()
        prior = replace(prior, hypotheses=("Retain the original thesis.",),
            next_information_needs=("What revenue guidance is available?", "What margin guidance is available?"))
        second = replace(selection, signal_ref="margin_guidance:v1", target_need_indices=(1,))
        batch = replace(batch, results=(*batch.results, replace(batch.results[0], signal_id="margin_guidance")), signal_calls=2)
        rows = [{"need_index": index, "answer_scope": "unanswered", "residual_need": None,
                 "evidence_refs": [], "reason": "No answer evidence was adopted for this occurrence."}
                for index in (0, 1)]

        def initial(call):
            return patch(call["payload"]["output_patch_contract"],
                {"op": "append", "path": "need_dispositions", "value": rows[0]},
                {"op": "append", "path": "resolved_questions", "value": "The operative starting reference baseline price is 1.44."},
            )

        def repair(call):
            feedback = call["payload"]["validation_feedback"]
            obligations = feedback["obligations"]
            by_code = {row["issue_code"]: row for row in obligations}
            self.assertEqual(by_code["research_state_anchor_value_invalid"]["must_change_paths"], ["resolved_questions[0]"])
            self.assertEqual(by_code["research_need_disposition_invalid"]["must_change_paths"], ["need_dispositions"])
            self.assertEqual(feedback["invalid_output"]["need_dispositions"], [rows[0]])
            permissions = call["payload"]["output_patch_contract"]["allowed_operations"]
            self.assertFalse(any(p["path"].startswith(("need_dispositions[0]", "hypotheses", "next_information_needs")) for p in permissions))
            return patch(call["payload"]["output_patch_contract"],
                {"op": "remove", "path": "resolved_questions[0]"},
                {"op": "append", "path": "need_dispositions", "value": rows[1]},
            )

        caller = PatchCaller(initial, repair)
        caller.max_structured_corrections = 1
        controller = self.controller(caller, selection)
        controller.set_reflection_runtime_context(selections=(selection, second), must_finalize=False, termination_trigger=None)
        controller.set_evaluation_context(datetime(2025, 9, 30, tzinfo=timezone.utc))
        controller.set_evaluation_anchor({"status": "available", "mean_adjusted_close": 1.57,
            "doubling_threshold": 3.14, "recent_close": 2.18, "recent_close_date": "2025-09-29"})
        result = controller.reflect(default_information_plan(), prior, batch)
        self.assertEqual(len(caller.calls), 2)
        self.assertEqual(result.value, prior)
        self.assertEqual(result.metadata["need_dispositions"]["items"], [
            {**row, "prior_need": prior.next_information_needs[row["need_index"]]} for row in rows])

    def test_raw_disposition_diagnostics_do_not_grant_unadopted_answer_authority(self):
        prior, selection, batch = self.inputs()
        row = {"need_index": 0, "answer_scope": "full", "residual_need": None,
               "evidence_refs": [{"signal_ref": selection.signal_ref, "evidence_group": "supporting", "evidence_index": 0}],
               "reason": "The answer needs adopted evidence before acceptance."}
        self.assertEqual(raw_need_disposition_issues([row], previous_state=prior,
            selections=(selection,), batch=batch), ())
        with self.assertRaises(StructuredValidationError):
            validate_need_dispositions([row], previous_state=prior, state=prior,
                selections=(selection,), batch=batch)
        invalid = {**row, "evidence_refs": [{**row["evidence_refs"][0], "evidence_index": 99}]}
        issues = raw_need_disposition_issues([invalid], previous_state=prior, selections=(selection,), batch=batch)
        self.assertEqual(issues[0].paths, ("need_dispositions[0].evidence_refs[0]",))
