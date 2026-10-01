"""Offline contracts for incremental state updates and partial repair progress."""

from copy import deepcopy
from unittest import TestCase

from stock_opportunity_agent.llm.agent import AgentUsage
from stock_opportunity_agent.models import StructuredValidationError, ValidationError, ValidationIssue
from stock_opportunity_agent.research.evolution_core import (
    CandidateExecutionRejected,
    ResearchState,
    RuntimeBudgetExceeded,
)
from stock_opportunity_agent.research.evolution_output_validation import (
    _blind_prediction_from_role,
    _blind_prediction_with_baseline,
    _complete_parsed_role,
)
from stock_opportunity_agent.research.evolution_state_patch import (
    apply_state_patch,
    recorded_response_patch,
    state_patch_contract,
    state_patch_hash,
)
from stock_opportunity_agent.research.evolution_transport import StructuredOutputInvalid
from stock_opportunity_agent.research.evolution_research_validation import (
    _validate_raw_information_plan_request_fields,
)


def obligation(path, *, repairs=("replace",), dependencies=(), **context):
    return {
        "issue_code": "test_invalid_value", "must_change_paths": [path],
        "permitted_dependency_paths": list(dependencies), "allowed_repairs": list(repairs),
        **context,
    }


def patch(contract, *operations):
    return {"base_hash": contract["base_hash"], "operations": list(operations)}


class PatchCaller:
    """Return explicitly scripted new-protocol replies; never normalize fixtures."""

    max_structured_corrections = 2

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    def complete_json(self, **kwargs):
        self.calls.append(deepcopy(kwargs))
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        value = answer(kwargs) if callable(answer) else answer
        return value, AgentUsage(llm_calls=1, tokens=10)


class StatePatchTests(TestCase):
    def test_snapshot_indices_survive_multiple_removals_and_append(self):
        base = {"rows": ["same", "edit", "same", "last"], "keep": {"unchanged": True}}
        contract = state_patch_contract(base, mode="correction", obligations=[
            obligation("rows[0]", repairs=("remove",)),
            obligation("rows[1]"),
            obligation("rows[2]", repairs=("remove",)),
            obligation("rows", repairs=("add",)),
        ])
        result = apply_state_patch(base, patch(contract,
            {"op": "remove", "path": "rows[0]"},
            {"op": "replace", "path": "rows[1]", "value": "edited"},
            {"op": "remove", "path": "rows[2]"},
            {"op": "append", "path": "rows", "value": "new"},
        ), contract=contract)
        self.assertEqual(result["rows"], ["edited", "last", "new"])
        self.assertEqual(base["rows"], ["same", "edit", "same", "last"])
        self.assertEqual(result["keep"], base["keep"])
        self.assertIsNot(result["keep"], base["keep"])

    def test_missing_dictionary_field_requires_add(self):
        base = {"row": {"valid": 1}}
        contract = state_patch_contract(base, mode="correction", obligations=[
            obligation("row.missing", repairs=("add",)),
        ])
        result = apply_state_patch(base, patch(contract,
            {"op": "add", "path": "row.missing", "value": 2},
        ), contract=contract)
        self.assertEqual(result, {"row": {"valid": 1, "missing": 2}})
        with self.assertRaises(ValidationError):
            apply_state_patch(base, patch(contract,
                {"op": "replace", "path": "row.missing", "value": 2},
            ), contract=contract)

    def test_stale_base_leaf_parent_drift_and_full_object_are_rejected(self):
        base = {"rows": [{"claim": "bad", "id": "stable"}], "keep": "yes"}
        contract = state_patch_contract(base, mode="correction", obligations=[
            obligation("rows[0].claim", repairs=("replace", "remove")),
        ])
        invalid = [
            {"base_hash": "0" * 64, "operations": []},
            base,
            patch(contract, {"op": "remove", "path": "rows[0]"}),
            patch(contract, {"op": "replace", "path": "rows[0]", "value": {"claim": "ok"}}),
            patch(contract, {"op": "replace", "path": "keep", "value": "no"}),
        ]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValidationError):
                apply_state_patch(base, value, contract=contract)
        changed = deepcopy(base)
        changed["rows"][0]["id"] = "different"
        with self.assertRaisesRegex(ValidationError, "base_hash"):
            apply_state_patch(changed, patch(contract), contract=contract)

    def test_component_permission_cannot_replace_an_existing_list(self):
        base = {"rows": ["a", "b"]}
        contract = state_patch_contract(base, mode="correction", obligations=[obligation("rows")])
        with self.assertRaises(ValidationError):
            apply_state_patch(base, patch(contract,
                {"op": "replace", "path": "rows", "value": ["new"]},
            ), contract=contract)

    def test_duplicate_overlapping_edits_identity_guard_and_append_budget(self):
        base = {"rows": [{"id": "one", "claim": "bad"}]}
        contract = state_patch_contract(base, mode="correction", obligations=[
            obligation("rows[0]", repairs=("replace", "add"), item_id="one", item_id_field="id",
                       permitted_append_paths=["rows"]),
        ])
        for edits in (
            [{"op": "replace", "path": "rows[0]", "value": {"id": "one"}},
             {"op": "replace", "path": "rows[0].claim", "value": "ok"}],
            [{"op": "append", "path": "rows", "value": {"id": "two"}},
             {"op": "append", "path": "rows", "value": {"id": "three"}}],
        ):
            with self.subTest(edits=edits), self.assertRaises(ValidationError):
                apply_state_patch(base, patch(contract, *edits), contract=contract)
        bad_contract = deepcopy(contract)
        bad_contract["identity_guards"][0]["value"] = "other"
        with self.assertRaisesRegex(ValidationError, "identity"):
            apply_state_patch(base, patch(contract), contract=bad_contract)

    def test_explicit_compaction_does_not_grant_list_root_scope(self):
        base = {"rows": ["a", "b", "c"]}
        contract = state_patch_contract(base, mode="correction", obligations=[
            obligation("rows", repairs=("replace", "remove"), minimum_removed_items=1,
                       required_compaction_remove_paths=["rows[1]"]),
        ])
        self.assertEqual(contract["allowed_operations"], [
            {"op": "remove", "path": "rows[1]", "descendants": False},
        ])

    def test_prior_need_restore_never_overwrites_same_index_sibling(self):
        base = {"next_information_needs": ["valid sibling"]}
        contract = state_patch_contract(base, mode="correction", obligations=[
            obligation("next_information_needs[0]", repairs=("replace",),
                       required_action="restore_exactly", required_need="missing", required_need_occurrences=1),
        ])
        result = apply_state_patch(base, patch(contract,
            {"op": "append", "path": "next_information_needs", "value": "missing"},
        ), contract=contract)
        self.assertEqual(result["next_information_needs"], ["valid sibling", "missing"])
        with self.assertRaises(ValidationError):
            apply_state_patch(base, patch(contract,
                {"op": "append", "path": "next_information_needs", "value": "invented"},
            ), contract=contract)

    def test_recording_conversion_remains_an_explicit_offline_step(self):
        base = ResearchState(next_information_needs=("Unanswered need",)).to_dict()
        changed = deepcopy(base)
        changed["hypotheses"] = ["New supported hypothesis"]
        delta = recorded_response_patch(base, changed)
        contract = state_patch_contract(base)
        self.assertEqual(apply_state_patch(base, delta, contract=contract), changed)
        self.assertEqual(delta["operations"], [
            {"op": "append", "path": "hypotheses", "value": "New supported hypothesis"},
        ])

    def test_missing_nested_field_does_not_authorize_new_list_member(self):
        base = {"selections": [{"signal_ref": "known:v1"}]}
        contract = state_patch_contract(base, mode="correction", obligations=[
            obligation("selections[0].context_tags", repairs=("add",)),
        ])
        result = apply_state_patch(base, patch(contract,
            {"op": "add", "path": "selections[0].context_tags", "value": []},
        ), contract=contract)
        self.assertEqual(result["selections"], [{"signal_ref": "known:v1", "context_tags": []}])
        with self.assertRaisesRegex(ValidationError, "outside typed authority"):
            apply_state_patch(base, patch(contract,
                {"op": "append", "path": "selections", "value": {"signal_ref": "other:v1"}},
            ), contract=contract)

    def test_restore_budget_is_per_exact_literal_not_pooled(self):
        base = {"next_information_needs": ["valid"]}
        contract = state_patch_contract(base, mode="correction", obligations=[
            obligation("next_information_needs[0]", repairs=("add",), required_action="restore_exactly",
                       required_need=need, required_need_occurrences=1)
            for need in ("missing a", "missing b", "missing a")
        ])
        # Exact-duplicate appends are mechanically deduplicated before the
        # budget check fires; the surviving single occurrence is the
        # model's intended repair and passes the per-literal budget.
        result = apply_state_patch(base, patch(contract,
            {"op": "append", "path": "next_information_needs", "value": "missing a"},
            {"op": "append", "path": "next_information_needs", "value": "missing a"},
        ), contract=contract)
        self.assertEqual(
            result["next_information_needs"], ["valid", "missing a"]
        )
        result = apply_state_patch(base, patch(contract,
            {"op": "append", "path": "next_information_needs", "value": "missing a"},
            {"op": "append", "path": "next_information_needs", "value": "missing b"},
        ), contract=contract)
        self.assertEqual(result["next_information_needs"], ["valid", "missing a", "missing b"])

    def test_removing_last_invalid_need_only_allows_decision_dependency(self):
        base = {"next_information_needs": ["bad"], "decision": "continue"}
        contract = state_patch_contract(base, mode="correction", obligations=[
            obligation("next_information_needs[0]", repairs=("remove",), dependencies=("decision",),
                       dependency_allowed_repairs={"decision": ["replace"]}),
        ])
        result = apply_state_patch(base, patch(contract,
            {"op": "remove", "path": "next_information_needs[0]"},
            {"op": "replace", "path": "decision", "value": "finalize"},
        ), contract=contract)
        self.assertEqual(result, {"next_information_needs": [], "decision": "finalize"})
        with self.assertRaisesRegex(ValidationError, "outside typed authority"):
            apply_state_patch(base, patch(contract,
                {"op": "replace", "path": "next_information_needs[0]", "value": "new unrelated"},
            ), contract=contract)

    def test_identity_guard_binds_owning_row_not_nested_index_or_dependency(self):
        base = {"rows": [{"id": "one", "tags": ["bad"]}], "beliefs": ["bad"]}
        contract = state_patch_contract(base, mode="correction", obligations=[
            obligation("rows[0].tags[0]", dependencies=("beliefs[0]",), item_id="one", item_id_field="id"),
        ])
        self.assertEqual(contract["identity_guards"], [{"path": "rows[0]", "field": "id", "value": "one"}])
        result = apply_state_patch(base, patch(contract,
            {"op": "replace", "path": "rows[0].tags[0]", "value": "good"},
            {"op": "replace", "path": "beliefs[0]", "value": "good"},
        ), contract=contract)
        self.assertEqual(result["rows"][0]["id"], "one")


class IncrementalRoleTests(TestCase):
    def test_explicit_percent_change_checks_signed_changes_without_joining_windows(self):
        from stock_opportunity_agent.research.evolution_output_validation import _explicit_percent_change_issues

        correct = (
            "Price rose from $48.60 on 2025-02-24 to $113.50 on 2025-09-29, a 133.5% return.",
            "Price fell from $10.00 to $8.00, a 20% decline.",
            "Price rose from $10 to $12, a 20% increase.",
            "Price rose from $10 to $12; a different window returned 30%.",
            "Profit rose from 0 to 12, a 20% return is not computable.",
        )
        self.assertEqual(_explicit_percent_change_issues((("key_reasons", correct),)), [])
        wrong = "Price rose from $41.33 on 2025-08-01 to $113.50 on 2025-09-29, a 133.5% return."
        issues = _explicit_percent_change_issues((("key_reasons", (wrong, correct[0])),))
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].paths, ("key_reasons[0]",))
        self.assertIn("174.619", issues[0].message)

    def test_percent_change_repair_uses_one_item_and_preserves_prediction_siblings(self):
        from stock_opportunity_agent.research.evolution_plan_roles import LLMBlindPredictor

        invalid = {"candidate_judgment": "possible", "magnitude": "2-3x",
                   "confidence": {"level": "low"}, "session_id": "test",
                   "key_reasons": ["Price rose from $41.33 on 2025-08-01 to $113.50 on 2025-09-29, a 133.5% return that could support repricing.",
                                   "A supported catalyst could drive share-price repricing."],
                   "uncertainties": ["Keep the existing uncertainty."]}
        corrected = "Price rose from $48.60 on 2025-02-24 to $113.50 on 2025-09-29, a 133.5% return that could support repricing."
        def repair(call):
            contract = call["payload"]["output_patch_contract"]
            self.assertEqual(call["payload"]["required_change_paths"], ["key_reasons[0]"])
            return patch(contract, {"op": "replace", "path": "key_reasons[0]", "value": corrected})
        caller = PatchCaller(invalid, repair)
        result = LLMBlindPredictor(caller).predict({}).value
        self.assertEqual(result.key_reasons, (corrected, invalid["key_reasons"][1]))
        self.assertEqual(result.uncertainties, tuple(invalid["uncertainties"]))
        self.assertEqual(result.candidate_judgment.value, "possible")
        self.assertEqual(result.magnitude.value, "2-3x")

    def run_role(self, caller, parser, **kwargs):
        return _complete_parsed_role(
            caller, stage="test_role", system_prompt="Return role contract.",
            payload=kwargs.pop("payload", {}), parser=parser, allow_outcomes=False,
            patch_corrections=True, stable_correction_prefix=True, **kwargs,
        )

    def test_successful_sibling_persists_after_another_obligation_fails(self):
        invalid = {"a": "bad", "b": "bad", "keep": {"nested": "exact"}}

        def parse(value):
            issues = [ValidationIssue(code="bad_field", message="Change bad value.", paths=(key,))
                      for key in ("a", "b") if value[key] != "good"]
            if issues:
                raise StructuredValidationError(issues)
            return value

        def repair_a(call):
            contract = call["payload"]["output_patch_contract"]
            return patch(contract, {"op": "replace", "path": "a", "value": "good"})

        def repair_b(call):
            feedback = call["payload"]["validation_feedback"]
            self.assertEqual(feedback["invalid_output"], {**invalid, "a": "good"})
            self.assertEqual(feedback["required_change_paths"], ["b"])
            contract = call["payload"]["output_patch_contract"]
            self.assertFalse(any(row["path"] == "a" for row in contract["allowed_operations"]))
            return patch(contract, {"op": "replace", "path": "b", "value": "good"})

        caller = PatchCaller(invalid, repair_a, repair_b)
        result, usage = self.run_role(caller, parse, max_request_tokens=100)
        self.assertEqual(result, {"a": "good", "b": "good", "keep": invalid["keep"]})
        self.assertEqual(usage.llm_calls, 3)
        self.assertEqual([call["max_request_tokens"] for call in caller.calls], [100, 90, 80])
        self.assertIn("incremental", caller.calls[0]["system_prompt"])

    def test_predictor_enum_and_coupled_fields_have_typed_partial_repairs(self):
        invalid = {"candidate_judgment": "likely", "magnitude": None,
                   "confidence": {"level": "certain"}, "key_reasons": ["Unchanged source reason"],
                   "uncertainties": [], "session_id": "test"}
        caller = PatchCaller(invalid, lambda call: patch(call["payload"]["output_patch_contract"],
            {"op": "replace", "path": "magnitude", "value": "2-3x"},
            {"op": "replace", "path": "confidence.level", "value": "low"},
        ))
        result, _ = self.run_role(caller, _blind_prediction_from_role)
        self.assertEqual(result.key_reasons, ("Unchanged source reason",))
        self.assertEqual(result.magnitude.value, "2-3x")

    def test_predictor_semantic_alternative_never_requires_unrelated_rewrite(self):
        invalid = {"candidate_judgment": "likely", "magnitude": "2-3x",
                   "confidence": {"level": "low"}, "key_reasons": ["The evidence does not support doubling."],
                   "uncertainties": ["Exact existing uncertainty"], "session_id": "test"}
        caller = PatchCaller(invalid, lambda call: patch(call["payload"]["output_patch_contract"],
            {"op": "replace", "path": "candidate_judgment", "value": "unlikely"},
            {"op": "replace", "path": "magnitude", "value": None},
        ))
        result, _ = self.run_role(caller, lambda value: _blind_prediction_with_baseline(value, {}))
        self.assertFalse(result.is_surge)
        self.assertEqual(result.uncertainties, ("Exact existing uncertainty",))

    def test_plan_shape_correction_only_adds_missing_request_field(self):
        invalid = {"B": {"requests": [{"request_id": "market", "description": "Market context",
                                       "source_types": ["market_data"]}]},
                   "H_init": "Unchanged init", "H_reflect": "Unchanged reflect", "H_analyse": "Unchanged analysis"}

        def parse(value):
            _validate_raw_information_plan_request_fields(value)
            return value

        caller = PatchCaller(invalid, lambda call: patch(call["payload"]["output_patch_contract"],
            {"op": "add", "path": "B.requests[0].max_documents", "value": 1},
        ))
        result, _ = self.run_role(caller, parse)
        self.assertEqual(result["H_reflect"], invalid["H_reflect"])
        contract = caller.calls[1]["payload"]["output_patch_contract"]
        self.assertEqual(contract["allowed_operations"], [
            {"op": "add", "path": "B.requests[0].max_documents", "descendants": False},
        ])

    def test_plan_outcome_field_guard_uses_original_exact_coordinate(self):
        value = {"B": {"requests": [{"request_id": "future_return", "description": "Issuer evidence",
                                     "source_types": ["market_data"], "max_documents": 1}]},
                 "H_init": "Keep init", "H_reflect": "Keep reflect", "H_analyse": "Keep analysis"}
        with self.assertRaises(StructuredValidationError) as caught:
            _validate_raw_information_plan_request_fields(value)
        self.assertEqual(caught.exception.issues[0].code, "plan_outcome_data_forbidden")
        self.assertEqual(caught.exception.issues[0].paths, ("B.requests[0].request_id",))

    def test_wrong_type_container_can_be_replaced_only_under_shape_authority(self):
        invalid = {"B": {"requests": [{"request_id": "market", "description": "Market context",
                                       "source_types": ["market_data"], "max_documents": 1}]},
                   "H_init": [], "H_reflect": "Keep reflect", "H_analyse": "Keep analysis"}

        def parse(value):
            _validate_raw_information_plan_request_fields(value)
            return value

        caller = PatchCaller(invalid, lambda call: patch(call["payload"]["output_patch_contract"],
            {"op": "replace", "path": "H_init", "value": "Executable init"},
        ))
        result, _ = self.run_role(caller, parse)
        self.assertEqual(result, {**invalid, "H_init": "Executable init"})
        self.assertEqual(caller.calls[1]["payload"]["output_patch_contract"]["allowed_operations"], [
            {"op": "replace", "path": "H_init", "descendants": False, "invalid_container": True},
        ])

    def test_linked_dependency_can_be_repaired_atomically(self):
        invalid = {"evidence": {"claim": "bad", "id": "unchanged"}, "belief": "bad"}
        issue = ValidationIssue(code="unsupported", message="Claim and belief need repair.",
                                paths=("evidence.claim",), dependent_paths=("belief",))

        def parse(value):
            if value["evidence"]["claim"] != "good" or value["belief"] != "good":
                raise StructuredValidationError([issue])
            return value

        caller = PatchCaller(invalid, lambda call: patch(call["payload"]["output_patch_contract"],
            {"op": "replace", "path": "evidence.claim", "value": "good"},
            {"op": "replace", "path": "belief", "value": "good"},
        ))
        result, _ = self.run_role(caller, parse)
        self.assertEqual(result["evidence"]["id"], "unchanged")
        self.assertEqual(result["belief"], "good")

    def test_invalid_patch_preserves_semantic_frontier_and_retries_it(self):
        invalid = {"value": "bad", "keep": "fixed"}

        def parse(value):
            if value["value"] == "bad":
                raise StructuredValidationError([ValidationIssue(
                    code="bad_field", message="Repair value.", paths=("value",))])
            return value

        def last(call):
            payload = call["payload"]
            self.assertIn("outside typed authority", payload["patch_validation_error"])
            self.assertEqual(payload["validation_feedback"]["invalid_output"], invalid)
            return patch(payload["output_patch_contract"],
                         {"op": "replace", "path": "value", "value": "good"})

        caller = PatchCaller(invalid, lambda call: patch(call["payload"]["output_patch_contract"],
            {"op": "replace", "path": "keep", "value": "drift"}), last)
        result, _ = self.run_role(caller, parse)
        self.assertEqual(result, {"value": "good", "keep": "fixed"})

    def test_initial_state_delta_rejects_full_reply_and_preserves_untouched_state(self):
        base = ResearchState(hypotheses=("Already validated",),
                             next_information_needs=("Unanswered need",)).to_dict()
        caller = PatchCaller(base, lambda call: patch(call["payload"]["output_patch_contract"],
            {"op": "append", "path": "current_beliefs", "value": "New supported observation"},
            {"op": "replace", "path": "decision", "value": "finalize"},
        ))
        result, _ = self.run_role(caller, ResearchState.from_dict,
                                 output_patch_base=base, payload={"research_state": base})
        self.assertEqual(result.hypotheses, ("Already validated",))
        self.assertEqual(result.current_beliefs, ("New supported observation",))
        self.assertNotIn("output_patch_base", caller.calls[0]["payload"])
        self.assertEqual(caller.calls[1]["payload"]["output_patch_contract"]["base_hash"], state_patch_hash(base))

    def test_only_unparseable_initial_response_allows_complete_reanswer(self):
        caller = PatchCaller(StructuredOutputInvalid("bad JSON", "broken", AgentUsage(llm_calls=1)),
                             {"value": "ok"})
        result, _ = self.run_role(caller, dict)
        self.assertEqual(result, {"value": "ok"})
        self.assertNotIn("output_patch_contract", caller.calls[1]["payload"])

    def test_empty_parseable_object_still_requires_delta_for_missing_field(self):
        def parse(value):
            if "required" not in value:
                raise StructuredValidationError([ValidationIssue(
                    code="missing_field", message="Add required field.",
                    paths=("required",), allowed_repairs=("add",))])
            return value
        caller = PatchCaller({}, lambda call: patch(call["payload"]["output_patch_contract"],
            {"op": "add", "path": "required", "value": "present"}))
        result, _ = self.run_role(caller, parse)
        self.assertEqual(result, {"required": "present"})

    def test_parseable_failure_without_typed_authority_does_not_guess_paths(self):
        caller = PatchCaller({"value": "bad"})
        def parse(_value):
            raise ValidationError("Please replace value and all its siblings")
        with self.assertRaises(CandidateExecutionRejected):
            self.run_role(caller, parse)
        self.assertEqual(len(caller.calls), 1)

    def test_budget_and_provider_failures_do_not_become_research_values(self):
        invalid = {"value": "bad"}
        def parse(_value):
            raise StructuredValidationError([ValidationIssue(
                code="bad_field", message="Repair value.", paths=("value",))])
        for error in (RuntimeBudgetExceeded("no tokens"), RuntimeError("provider unavailable")):
            caller = PatchCaller(invalid, error)
            with self.subTest(error=error), self.assertRaises(type(error)):
                self.run_role(caller, parse)
