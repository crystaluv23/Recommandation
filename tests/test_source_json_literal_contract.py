"""Strict scoped source restoration runs before semantic correction."""

from copy import deepcopy
from dataclasses import replace
from unittest import TestCase

from stock_opportunity_agent.models import StructuredValidationError, ValidationIssue
from stock_opportunity_agent.research.evolution_core import CandidateExecutionRejected
from stock_opportunity_agent.research.repair import unique_json_source_literal
from stock_opportunity_agent.research.evolution_output_validation import _exact_value_fallback
from stock_opportunity_agent.research.evolution_signal_roles import (
    LLMSignalUpdateModel, _update_visible_comparisons, _update_comparison_gap_issues,
)
from tests.evolution_runtime_test_support import ScriptedRoleCaller


class SourceJsonLiteralTests(TestCase):
    def test_whole_typed_equivalence_and_ambiguity(self):
        source = '{"a":1,"b":[{"x":true,"y":2.0}]}'
        reordered = '{"b":[{"y":2.0,"x":true}],"a":1}'
        self.assertEqual(unique_json_source_literal(reordered, [source, source]), source)
        self.assertIsNone(unique_json_source_literal(reordered, [source, reordered]))
        for invalid in ('{"a":1}', '{"a":true,"b":[{"x":true,"y":2.0}]}',
                        '{"a":1,"b":[{"x":true,"y":2}]}',
                        '{"a":0,"a":1,"b":[{"x":true,"y":2.0}]}',
                        '{"a":1.0,"a":1,"b":[{"x":true,"y":2.0}]}',
                        '{"a":1,"b":[{"x":true,"y":NaN}]}', '1',
                        '{"a":1,"b":[{"x":true,"y":1e400}]}'):
            with self.subTest(invalid=invalid):
                self.assertIsNone(unique_json_source_literal(invalid, [source]))
        self.assertIsNone(unique_json_source_literal('{"a":1}', ['{"a":0,"a":1}']))
        self.assertEqual(unique_json_source_literal('{"a":1,"a":1,"b":[{"x":true,"y":2.0}]}', [source]), source)
        self.assertIsNone(unique_json_source_literal('{"a":1}', ['{"a":1,"a":1}']))

    def test_leaf_permission_and_snapshot_are_required(self):
        base = {"facts": [{"exact_span": '{"b":2,"a":1}'}], "rationale": ["Keep"]}
        issue = ValidationIssue(code="source_json_literal_not_exact", message="Copy original",
            paths=("facts[0].exact_span",), allowed_repairs=("replace",),
            repair_context={"mechanical_action": "restore_source_json_literal",
                            "original_text": base["facts"][0]["exact_span"],
                            "required_text": '{"a":1,"b":2}'})
        result, actions = _exact_value_fallback(base, StructuredValidationError([issue]))
        self.assertEqual(result["facts"][0]["exact_span"], '{"a":1,"b":2}')
        self.assertEqual(result["rationale"], base["rationale"])
        self.assertEqual(actions["restore_source_json_literal"], ("facts[0].exact_span",))
        self.assertIsNone(_exact_value_fallback(base, StructuredValidationError([
            replace(issue, allowed_repairs=("remove",))])))
        stale = deepcopy(base); stale["facts"][0]["exact_span"] = '{"a":3}'
        self.assertIsNone(_exact_value_fallback(stale, StructuredValidationError([issue])))

    def test_update_restores_same_scope_before_any_llm_correction(self):
        output, payload = self._example()
        original = deepcopy(output)
        caller = ScriptedRoleCaller([output])
        events = []
        caller.on_progress = lambda event: events.append(event)
        result = LLMSignalUpdateModel(caller).update(payload)
        expected = deepcopy(output["case_diagnostics"])
        expected[0]["facts"][0]["exact_span"] = '{"a":1,"b":2}'
        self.assertEqual(result.value.case_diagnostics, tuple(expected))
        self.assertEqual(result.value.rationale, tuple(output["rationale"]))
        self.assertEqual(result.usage.llm_calls, 1)
        self.assertEqual(output, original)
        self.assertTrue(any(e.get("event_type") == "mechanical_repair_progress" for e in events))

    def test_mixed_defect_correction_base_preserves_restored_literal(self):
        output, payload = self._example()
        output["case_diagnostics"][0]["outcome_relation"] = "aligned"
        corrected = deepcopy(output)
        corrected["case_diagnostics"][0]["outcome_relation"] = "not_assessable"
        corrected["case_diagnostics"][0]["facts"][0]["exact_span"] = '{"a":1,"b":2}'
        caller = ScriptedRoleCaller([output, corrected])
        result = LLMSignalUpdateModel(caller).update(payload)
        self.assertEqual(result.value.case_diagnostics, tuple(corrected["case_diagnostics"]))
        feedback = caller.calls[1]["payload"]["validation_feedback"]
        self.assertNotIn('"b":2,"a":1', str(feedback))
        self.assertEqual(result.usage.llm_calls, 2)

    def test_other_case_source_does_not_grant_literal_restoration(self):
        output, payload = self._example()
        payload["induction_cases"][0]["evidence_observation"]["executed_evidence"][0]["exact_span"] = '{"a":9,"b":2}'
        corrected = deepcopy(output)
        corrected["case_diagnostics"][0]["facts"] = []
        caller = ScriptedRoleCaller([output, corrected])
        result = LLMSignalUpdateModel(caller).update(payload)
        self.assertEqual(result.usage.llm_calls, 2)
        self.assertEqual(result.value.case_diagnostics, tuple(corrected["case_diagnostics"]))

    def test_comparison_inventory_requires_executed_scope_dates_and_cutoff(self):
        packet = self._comparison_packet()
        rows = _update_visible_comparisons(packet)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["prior"]["start"], "2023-01-01")
        for variant in ("other_document", "future_filing", "different_duration", "not_executed"):
            changed = deepcopy(packet)
            observation = changed["evidence_observation"]
            if variant == "other_document": observation["evidence"][0]["document_ref"] = "document-02"
            if variant == "not_executed": observation["executed_evidence"] = []
            if variant in {"future_filing", "different_duration"}:
                row = observation["evidence"][0]["structured_context"]["concepts"][0]["records"][1]
                row["exact_span"] = row["exact_span"].replace("2025-01-20", "2025-03-01") if variant == "future_filing" else row["exact_span"].replace("2023-01-01", "2023-07-01")
            with self.subTest(variant=variant): self.assertEqual(_update_visible_comparisons(changed), [])

    def test_absence_guard_is_named_case_local_and_semantic_not_mechanical(self):
        rows = _update_visible_comparisons(self._comparison_packet())
        claim = "The visible evidence does not show a prior-year comparable operating-cash-flow duration."
        issues = _update_comparison_gap_issues([claim], rows, path="case_diagnostics[0]")
        self.assertEqual(issues[0].paths, ("case_diagnostics[0].evidence_gaps[0]",))
        self.assertIsNone(_exact_value_fallback({"case_diagnostics": [{"evidence_gaps": [claim]}]}, StructuredValidationError(issues)))
        self.assertEqual(_update_comparison_gap_issues([claim], [], path="case_diagnostics[1]"), [])
        for statement in ("If no prior-year comparable operating cash flow is visible, review source coverage.",
                          "It is incorrect that no prior-year comparable operating cash flow is visible.",
                          "No prior-year comparable operating cash flow is needed to compute this ratio.",
                          "No prior-year revenue is visible.", "No prior-year cash balance is visible."):
            with self.subTest(statement=statement):
                self.assertEqual(_update_comparison_gap_issues([statement], rows, path="case_diagnostics[0]"), [])
        continuing = deepcopy(rows); continuing[0]["concept"] += "ContinuingOperations"
        self.assertEqual(_update_comparison_gap_issues([claim], continuing, path="case_diagnostics[0]"), [])

    def test_adapter_discloses_prior_and_corrects_only_false_gap(self):
        output, payload = self._example()
        packet = self._comparison_packet()
        payload["induction_cases"][0] = packet
        source = packet["evidence_observation"]["executed_evidence"][0]["exact_span"]
        row = output["case_diagnostics"][0]
        row["facts"][0]["exact_span"] = source
        row["evidence_verdict"] = "supported"
        row["evidence_gaps"] = ["The visible evidence does not show a prior-year comparable operating-cash-flow duration."]
        corrected = deepcopy(output); corrected["case_diagnostics"][0]["evidence_gaps"] = []
        original_payload = deepcopy(payload)
        caller = ScriptedRoleCaller([output, lambda kwargs: {
            "base_hash": kwargs["payload"]["output_patch_contract"]["base_hash"],
            "operations": [{"op": "remove", "path": "case_diagnostics[0].evidence_gaps[0]"}],
        }])
        result = LLMSignalUpdateModel(caller).update(payload)
        self.assertEqual(result.value.case_diagnostics, tuple(corrected["case_diagnostics"]))
        self.assertEqual(result.usage.llm_calls, 2)
        self.assertEqual(payload, original_payload)
        sent = caller.calls[0]["payload"]["induction_cases"][0]["evidence_observation"]
        self.assertEqual(len(sent["visible_prior_year_comparisons"]), 1)
        self.assertEqual(caller.calls[1]["payload"]["validation_feedback"]["required_change_paths"], ["case_diagnostics[0].evidence_gaps[0]"])

    def test_gap_patch_cannot_rewrite_an_existing_fact(self):
        output, payload = self._example()
        packet = self._comparison_packet(); payload["induction_cases"][0] = packet
        output["case_diagnostics"][0]["facts"][0]["exact_span"] = packet["evidence_observation"]["executed_evidence"][0]["exact_span"]
        output["case_diagnostics"][0]["evidence_gaps"] = ["No prior-year comparable operating cash flow is visible."]
        caller = ScriptedRoleCaller([output, lambda kwargs: {
            "base_hash": kwargs["payload"]["output_patch_contract"]["base_hash"],
            "operations": [{"op": "replace", "path": "case_diagnostics[0].facts[0].exact_span", "value": "invented"}],
        }])
        with self.assertRaisesRegex(CandidateExecutionRejected, "outside typed authority"):
            LLMSignalUpdateModel(caller).update(payload)

    def test_invalid_extra_diagnostic_is_not_silently_discarded(self):
        output, payload = self._example()
        output["case_diagnostics"].append(None)
        caller = ScriptedRoleCaller([output, lambda kwargs: {
            "base_hash": kwargs["payload"]["output_patch_contract"]["base_hash"],
            "operations": [{"op": "remove", "path": "case_diagnostics[2]"}],
        }])
        result = LLMSignalUpdateModel(caller).update(payload)
        self.assertEqual(result.usage.llm_calls, 2)
        self.assertEqual(len(result.value.case_diagnostics), 2)
        self.assertEqual(caller.calls[1]["payload"]["validation_feedback"]["required_change_paths"], ["case_diagnostics[2]"])

    def test_insufficient_verdict_can_change_when_every_gap_is_proven_false(self):
        output, payload = self._example()
        packet = self._comparison_packet(); payload["induction_cases"][0] = packet
        output["case_diagnostics"][0]["facts"][0]["exact_span"] = packet["evidence_observation"]["executed_evidence"][0]["exact_span"]
        output["case_diagnostics"][0]["evidence_gaps"] = ["No prior-year comparable operating cash flow is visible."]
        caller = ScriptedRoleCaller([output, lambda kwargs: {
            "base_hash": kwargs["payload"]["output_patch_contract"]["base_hash"],
            "operations": [{"op": "replace", "path": "case_diagnostics[0].evidence_verdict", "value": "supported"},
                           {"op": "remove", "path": "case_diagnostics[0].evidence_gaps[0]"}],
        }])
        result = LLMSignalUpdateModel(caller).update(payload)
        self.assertEqual(result.value.case_diagnostics[0]["evidence_verdict"], "supported")
        self.assertEqual(result.value.case_diagnostics[0]["facts"], output["case_diagnostics"][0]["facts"])
        self.assertEqual(caller.calls[1]["payload"]["validation_feedback"]["permitted_dependency_paths"], ["case_diagnostics[0].evidence_verdict"])

    def test_duplicate_case_can_be_removed_without_reassigning_identity(self):
        output, payload = self._example()
        output["case_diagnostics"].append(deepcopy(output["case_diagnostics"][0]))
        caller = ScriptedRoleCaller([output, lambda kwargs: {
            "base_hash": kwargs["payload"]["output_patch_contract"]["base_hash"],
            "operations": [{"op": "remove", "path": "case_diagnostics[2]"}],
        }])
        result = LLMSignalUpdateModel(caller).update(payload)
        self.assertEqual(result.usage.llm_calls, 2)
        self.assertEqual([row["case_ref"] for row in result.value.case_diagnostics], ["update-case-001", "update-case-002"])
        self.assertEqual(result.value.case_diagnostics[1], output["case_diagnostics"][1])

    @staticmethod
    def _comparison_packet():
        current = '{"start":"2024-01-01","end":"2024-12-31","filed":"2025-01-20","val":-20}'
        prior = '{"start":"2023-01-01","end":"2023-12-31","filed":"2025-01-20","val":-10}'
        return {"case_ref": "update-case-001", "outcome_relation": {"current_signal_relation": "not_assessable"},
                "evidence_observation": {"prediction_time": "2025-02-01T00:00:00+00:00",
                    "executed_evidence": [{"document_ref": "document-01", "exact_span": current}],
                    "evidence": [{"document_ref": "document-01", "structured_context": {"concepts": [{
                        "concept": "NetCashProvidedByUsedInOperatingActivities", "taxonomy": "us-gaap", "unit": "USD",
                        "records": [{"exact_span": current}, {"exact_span": prior}]}]}}]}}

    @staticmethod
    def _example():
        rows = [{"case_ref": f"update-case-00{i}", "evidence_verdict": "insufficient",
                 "facts": [{"document_ref": "document-01", "exact_span": literal}],
                 "evidence_gaps": ["No comparative period is supplied."],
                 "outcome_relation": "not_assessable",
                 "outcome_explanation": "Unavailable results do not establish association."}
                for i, literal in ((1, '{"b":2,"a":1}'), (2, '{"a":1,"b":2}'))]
        output = {"signal_ref": "cash_reserves:v1", "disposition": "defer",
                  "problem_type": "insufficient_evidence", "rationale": ["Keep this rationale."],
                  "changed_paths": [], "candidate": None, "case_diagnostics": rows}
        payload = {"target": {"signal_ref": output["signal_ref"]},
                   "induction_cases": [{"case_ref": row["case_ref"],
                       "evidence_observation": {"executed_evidence": [{
                           "document_ref": "document-01", "exact_span": '{"a":1,"b":2}'}]},
                       "outcome_relation": {"current_signal_relation": "not_assessable"}}
                       for row in rows]}
        return output, payload
