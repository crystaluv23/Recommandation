"""Actual answer scope follows executed evidence, never routing expectations."""

from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
from unittest import TestCase

from stock_opportunity_agent.models import StructuredValidationError
from stock_opportunity_agent.research.evolution_core import (
    ResearchDecision, ResearchEvidenceRef, ResearchState, SignalSelectionDecision,
)
from stock_opportunity_agent.research.evolution_research_validation import (
    _reflection_need_transition_contract, _validate_research_state_refs,
    validate_need_dispositions,
)
from stock_opportunity_agent.research.evolution_output_validation import _research_need_transition_fallback
from stock_opportunity_agent.signal_library import (
    SignalBatchResult, SignalCoverage, SignalEvidence, SignalResult, SignalValue,
)


class NeedDispositionTests(TestCase):
    """Exercise production validation with independent state/evidence fixtures."""

    def setUp(self):
        self.need = "What are the revenue guidance and operating margin assumptions?"
        self.previous = ResearchState(next_information_needs=(self.need,))
        self.selection = SignalSelectionDecision(
            signal_ref="guidance_acceleration:v3", reason_code="answer_need",
            selection_reason="Expected to cover management guidance.",
            applicability_hypothesis="Guidance may inform the outlook.",
            expected_role="primary", context_tags=("general",),
            target_need_indices=(0,), answer_scope="full",
        )
        self.result = SignalResult(
            signal_id="guidance_acceleration", version=3, value=SignalValue.NEUTRAL,
            confidence=0.5, interpretation="The revenue outlook was reaffirmed.",
            supporting_evidence=(SignalEvidence(
                document_id="guidance-source", exact_span="The revenue outlook was reaffirmed.",
                timestamp=datetime(2025, 6, 25, tzinfo=timezone.utc),
            ),), coverage=SignalCoverage.PARTIAL,
        )
        self.batch = SignalBatchResult(results=(self.result,), signal_calls=1)
        self.ref = {"signal_ref": self.result.ref, "evidence_group": "supporting", "evidence_index": 0}
        self.current = replace(self.previous, supporting_evidence=(ResearchEvidenceRef(
            kind="signal", claim=self.result.supporting_evidence[0].exact_span, **self.ref,
        ),))

    def row(self, scope="unanswered", *, index=0, residual=None):
        return {"need_index": index, "answer_scope": scope, "residual_need": residual,
                "evidence_refs": [] if scope == "unanswered" else [dict(self.ref)],
                "reason": "The executed evidence determines the actual scope."}

    def validate(self, current=None, rows=None, *, previous=None, selections=None, batch=None):
        return _validate_research_state_refs(
            current or self.current, phase="reflect", previous_state=previous or self.previous,
            selections=(self.selection,) if selections is None else selections,
            batch=batch or self.batch, need_dispositions=rows,
        )

    def test_unanswered_can_retain_need_despite_adopted_full_routing(self):
        self.assertEqual(self.validate(rows=[self.row()]), self.current)
        contract = _reflection_need_transition_contract(self.previous, (self.selection,), self.batch)
        self.assertIn("expectation only", contract["need_rules"][0]["required_transition"])

    def test_partial_measurement_can_fully_answer_narrow_need(self):
        completed = replace(self.current, next_information_needs=(), decision=ResearchDecision.FINALIZE)
        self.assertEqual(self.validate(completed, [self.row("full")]), completed)

    def test_sufficient_measurement_can_leave_actual_partial_need(self):
        residual = "What are the operating margin assumptions?"
        partial = replace(self.current, next_information_needs=(residual,))
        batch = SignalBatchResult(results=(replace(self.result, coverage=SignalCoverage.SUFFICIENT),), signal_calls=1)
        self.assertEqual(self.validate(partial, [self.row("partial", residual=residual)], batch=batch), partial)

    def test_none_and_legacy_unindexed_never_authorize_closure(self):
        completed = replace(self.current, next_information_needs=(), decision=ResearchDecision.FINALIZE)
        legacy = replace(self.selection, target_need_indices=(), answer_scope=None)
        for selections in ((self.selection,), (legacy,), ()):
            with self.subTest(selections=selections):
                with self.assertRaises(StructuredValidationError) as caught:
                    self.validate(completed, None, selections=selections)
                self.assertTrue(any(issue.repair_context.get("required_action") == "restore_exactly" for issue in caught.exception.issues))
                self.assertEqual(self.validate(rows=None, selections=selections), self.current)

    def test_missing_row_is_append_only_and_cannot_edit_valid_sibling(self):
        second = "What are the capital expenditure assumptions?"
        previous = replace(self.previous, next_information_needs=(self.need, second))
        current = replace(self.current, next_information_needs=(second,))
        selections = (self.selection, replace(self.selection, target_need_indices=(1,)))
        with self.assertRaises(StructuredValidationError) as caught:
            self.validate(current, [self.row("full")], previous=previous, selections=selections)
        issue = next(item for item in caught.exception.issues if item.code == "research_need_disposition_invalid")
        self.assertEqual(issue.paths, ("need_dispositions",))
        self.assertEqual(issue.allowed_repairs, ("add",))
        self.assertFalse(any(item.code == "research_need_transition_invalid" for item in caught.exception.issues))

    def test_bad_sibling_does_not_revoke_valid_full_answer(self):
        second = "What are the capital expenditure assumptions?"
        previous = replace(self.previous, next_information_needs=(self.need, second))
        current = replace(self.current, next_information_needs=(second,), resolved_questions=(self.need,))
        selections = (self.selection, replace(self.selection, target_need_indices=(1,)))
        bad = self.row(index=1)
        bad["reason"] = ""
        with self.assertRaises(StructuredValidationError) as caught:
            self.validate(current, [self.row("full"), bad], previous=previous, selections=selections)
        self.assertTrue(all(item.code == "research_need_disposition_invalid" for item in caught.exception.issues))

    def test_unselected_duplicate_occurrence_is_preserved(self):
        previous = replace(self.previous, next_information_needs=(self.need, self.need))
        self.assertEqual(self.validate(rows=[self.row("full")], previous=previous), self.current)
        completed = replace(self.current, next_information_needs=(), decision=ResearchDecision.FINALIZE)
        with self.assertRaises(StructuredValidationError):
            self.validate(completed, [self.row("full")], previous=previous)

    def test_duplicate_dispositions_cannot_authorize_removal(self):
        completed = replace(self.current, next_information_needs=(), decision=ResearchDecision.FINALIZE)
        with self.assertRaises(StructuredValidationError) as caught:
            self.validate(completed, [self.row("full"), self.row("full")])
        self.assertTrue(any(item.code == "research_need_disposition_invalid" for item in caught.exception.issues))
        self.assertTrue(any(item.repair_context.get("required_action") == "restore_exactly" for item in caught.exception.issues))

    def test_unavailable_or_not_newly_adopted_evidence_cannot_close(self):
        completed = replace(self.current, next_information_needs=(), decision=ResearchDecision.FINALIZE)
        unavailable = replace(self.result, value=SignalValue.UNAVAILABLE, coverage=SignalCoverage.UNAVAILABLE, supporting_evidence=(), execution_status=None)
        for previous, batch in ((self.current, self.batch), (self.previous, SignalBatchResult(results=(unavailable,), signal_calls=1))):
            with self.subTest(previous=previous, batch=batch):
                with self.assertRaises(StructuredValidationError):
                    self.validate(completed, [self.row("full")], previous=previous, batch=batch)

    def test_scope_and_evidence_failures_are_aggregated(self):
        bad_ref = replace(self.current.supporting_evidence[0], evidence_index=99)
        current = replace(self.current, supporting_evidence=(bad_ref,))
        with self.assertRaises(StructuredValidationError) as caught:
            self.validate(current, [])
        self.assertIn("signal_evidence_coordinate_invalid", {item.code for item in caught.exception.issues})
        self.assertIn("research_need_disposition_invalid", {item.code for item in caught.exception.issues})

    def test_need_restoration_does_not_fabricate_missing_disposition(self):
        completed = replace(self.current, next_information_needs=(), decision=ResearchDecision.FINALIZE)
        with self.assertRaises(StructuredValidationError) as caught:
            self.validate(completed, [])
        failed = {**completed.to_dict(), "need_dispositions": []}
        fallback = _research_need_transition_fallback(failed, caught.exception)
        self.assertIsNotNone(fallback)
        restored = ResearchState.from_dict(fallback[0])
        self.assertEqual(restored.next_information_needs, (self.need,))
        self.assertEqual(fallback[0]["need_dispositions"], [])
        with self.assertRaises(StructuredValidationError) as retried:
            self.validate(restored, fallback[0]["need_dispositions"])
        self.assertTrue(all(issue.code == "research_need_disposition_invalid" for issue in retried.exception.issues))

    def test_cosmetic_restore_uses_only_unreserved_returned_occurrence(self):
        cosmetic = self.need + " given available evidence"
        previous = replace(self.current, next_information_needs=(self.need, self.need))
        current = replace(previous, next_information_needs=(self.need, cosmetic))
        with self.assertRaises(StructuredValidationError) as caught:
            self.validate(current, [], previous=previous, selections=())
        issue = next(item for item in caught.exception.issues if item.code == "research_need_transition_invalid")
        self.assertEqual(issue.repair_context["returned_path"], "next_information_needs[1]")
        self.assertEqual(issue.repair_context["returned_need"], cosmetic)
        self.assertEqual(issue.repair_context["required_need_occurrences"], 2)

    def test_restored_exact_need_does_not_hide_surplus_literal_copy(self):
        previous = self.current
        current = replace(previous, next_information_needs=(self.need, self.need + " given available evidence"))
        with self.assertRaises(StructuredValidationError) as caught:
            self.validate(current, [], previous=previous, selections=())
        issues = [item for item in caught.exception.issues if item.code == "cosmetic_need_update"]
        self.assertEqual([item.paths for item in issues], [("next_information_needs[1]",)])
        self.assertFalse(any(item.repair_context.get("mechanical_action") for item in issues))

    def test_terminal_closure_preserves_need_and_rejects_false_resolution(self):
        previous = self.current
        terminal = replace(previous, decision=ResearchDecision.FINALIZE)
        self.assertEqual(self.validate(terminal, [], previous=previous, selections=()), terminal)
        false_resolved = replace(terminal, resolved_questions=(self.need,))
        with self.assertRaises(StructuredValidationError) as caught:
            self.validate(false_resolved, [], previous=previous, selections=())
        issue = next(item for item in caught.exception.issues if item.code == "stale_resolved_need_retained")
        self.assertEqual(issue.paths, ("resolved_questions[0]",))
        self.assertEqual(issue.repair_context["mechanical_action"], "remove_unsupported_resolution")

    def test_malformed_identity_and_foreign_or_cosmetic_residual_rejected(self):
        variants = []
        for name, value in (("need_index", True), ("answer_scope", "available"), ("reason", "")):
            row = self.row()
            row[name] = value
            variants.append(row)
        variants.extend(self.row("partial", residual=value) for value in (self.need, "What is the lunar orbital period?"))
        for row in variants:
            with self.subTest(row=row), self.assertRaises(StructuredValidationError):
                validate_need_dispositions([row], previous_state=self.previous, state=self.current, selections=(self.selection,), batch=self.batch)

    def test_bumble_original_selection_and_batch_preserve_unanswered_q3(self):
        report = json.loads((Path(__file__).resolve().parents[1] / "reports/v182-executed-answer-scope-contract-review-20261007.json").read_text())
        for plan, original in report["bumble_owning_validator_and_fallback_replay"]["plans"].items():
            with self.subTest(plan=plan):
                result = SignalResult.from_dict(original["guidance_result"])
                selection = replace(SignalSelectionDecision.from_dict(original["actual_selection"]), target_need_indices=(0,))
                previous = ResearchState(next_information_needs=(original["actual_need"],))
                current = replace(previous, supporting_evidence=(ResearchEvidenceRef(
                    kind="signal", claim=result.supporting_evidence[0].exact_span,
                    signal_ref=result.ref, evidence_group="supporting", evidence_index=0,
                ),))
                batch = SignalBatchResult(results=(result,), signal_calls=1)
                self.assertEqual(self.validate(current, [self.row()], previous=previous, selections=(selection,), batch=batch), current)
                closed = replace(current, next_information_needs=(), decision=ResearchDecision.FINALIZE)
                with self.assertRaises(StructuredValidationError):
                    self.validate(closed, [self.row()], previous=previous, selections=(selection,), batch=batch)
