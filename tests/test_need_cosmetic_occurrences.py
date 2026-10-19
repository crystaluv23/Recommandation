"""Cosmetic retention cannot contradict exact preserve/residual obligations."""

from types import SimpleNamespace
from unittest import TestCase
from datetime import datetime, timezone

from stock_opportunity_agent.llm.agent import AgentUsage
from stock_opportunity_agent.research.evolution_core import ResearchState, SignalSelectionDecision, default_information_plan
from stock_opportunity_agent.research.evolution_plan_roles import LLMResearchController
from stock_opportunity_agent.signal_library import SignalBatchResult, SignalEvidence, SignalResult, SignalValue

from stock_opportunity_agent.research.evolution_research_validation import (
    _targeted_answer_need_transition_errors,
)


class NeedCosmeticOccurrenceTests(TestCase):
    target = "What revenue gross margin guidance figures has the issuer disclosed?"
    similar = "Which revenue gross margin guidance figures has the issuer disclosed in available statements?"

    def errors(self, prior, returned, selections, dispositions):
        refs = {selection.signal_ref for selection in selections}
        return _targeted_answer_need_transition_errors(
            SimpleNamespace(next_information_needs=prior),
            SimpleNamespace(next_information_needs=returned), selections, refs, refs,
            need_dispositions=dispositions)

    def disposition(self, index, scope, *, residual=None, ref="guidance:v1"):
        return {"need_index": index, "answer_scope": scope, "residual_need": residual,
            "evidence_refs": [{"signal_ref": ref, "evidence_group": "supporting", "evidence_index": 0}],
            "reason": "Explicit post-execution test judgment."}

    def selection(self, index, *, partial=False, residual=None, ref="guidance:v1"):
        return SimpleNamespace(reason_code="answer_need", signal_ref=ref,
            target_need_indices=[index], answer_scope="partial" if partial else "full",
            residual_need=residual)

    def test_reserved_untargeted_paraphrase_survives_full_answer(self):
        selection = self.selection(1)
        actual = (self.disposition(1, "full"),)
        self.assertEqual(self.errors([self.similar, self.target], [self.similar], (selection,), actual), [])
        errors = self.errors([self.similar, self.target], [], (selection,), actual)
        self.assertEqual(errors[0]["required_action"], "restore_exactly")
        # Keeping the target itself, alongside its untouched sibling, still fails.
        errors = self.errors([self.similar, self.target], [self.similar, self.target], (selection,), actual)
        self.assertEqual(errors[0]["required_action"], "remove_exact_target")

    def test_surplus_copy_and_new_paraphrase_keep_correct_returned_coordinate(self):
        selection = self.selection(1)
        actual = (self.disposition(1, "full"),)
        errors = self.errors([self.similar, self.target], [self.similar, self.similar], (selection,), actual)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["issue"], "targeted need changed only cosmetically")
        self.assertEqual(errors[0]["returned_path"], "next_information_needs[1]")
        self.assertEqual(errors[0]["returned_need"], self.similar)
        errors = self.errors(["Unrelated unresolved need.", self.target],
            ["Unrelated unresolved need.", self.similar], (selection,), actual)
        self.assertEqual(errors[0]["returned_path"], "next_information_needs[1]")

    def test_exact_partial_residual_is_reserved_before_other_full_answer(self):
        partial = self.selection(0, partial=True, residual=self.similar, ref="other:v1")
        full = self.selection(1)
        actual = (self.disposition(0, "partial", residual=self.similar, ref="other:v1"),
                  self.disposition(1, "full"))
        self.assertEqual(self.errors(["Other compound question.", self.target], [self.similar],
            (partial, full), actual), [])
        errors = self.errors(["Other compound question.", self.target], [], (partial, full), actual)
        self.assertEqual(errors[0]["required_action"], "replace_with_exact_residual")

    def test_production_controller_preserves_similar_need_without_spending_correction(self):
        target = "What revenue guidance range has the issuer disclosed?"
        similar = "Which revenue guidance range has the issuer disclosed in available statements?"
        previous = ResearchState(next_information_needs=(similar, target))
        quote = "Management expects revenue of $19 million to $21 million."
        result = SignalResult(signal_id="guidance_acceleration", version=1,
            value=SignalValue.NEUTRAL, confidence=0.7, interpretation="Current guidance is available.",
            supporting_evidence=(SignalEvidence(document_id="guidance-document", exact_span=quote,
                timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc)),))
        selection = SignalSelectionDecision(signal_ref=result.ref, reason_code="answer_need",
            selection_reason="Read the disclosed current revenue range.",
            applicability_hypothesis="Management guidance is disclosed.", expected_role="primary",
            context_tags=(), target_need_indices=(1,), answer_scope="full")

        class NativeCaller:
            calls = 0

            def complete_json(self, **kwargs):
                self.calls += 1
                return {"base_hash": kwargs["payload"]["output_patch_contract"]["base_hash"],
                    "operations": [{"op": "append", "path": "supporting_evidence", "value": {
                        "kind": "signal", "signal_ref": result.ref, "claim": quote,
                        "evidence_group": "supporting", "evidence_index": 0}},
                        {"op": "remove", "path": "next_information_needs[1]"},
                        {"op": "append", "path": "need_dispositions", "value": {
                            "need_index": 1, "answer_scope": "full", "residual_need": None,
                            "evidence_refs": [{"signal_ref": result.ref, "evidence_group": "supporting", "evidence_index": 0}],
                            "reason": "The disclosed revenue range fully answers this narrow question.",
                        }}]}, AgentUsage()

        caller = NativeCaller()
        controller = LLMResearchController(caller)
        controller.set_reflection_runtime_context(selections=(selection,), must_finalize=False,
            termination_trigger=None)
        reflected = controller.reflect(default_information_plan(), previous,
            SignalBatchResult(results=(result,), signal_calls=1))
        self.assertEqual(reflected.value.next_information_needs, (similar,))
        self.assertEqual(reflected.value.supporting_evidence[0].claim, quote)
        self.assertEqual(caller.calls, 1)
