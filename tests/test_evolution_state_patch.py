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
    def test_initial_temporal_and_source_errors_share_the_first_repair_frontier(self):
        from datetime import datetime
        from stock_opportunity_agent.research.compute_tools import format_computed_card_readable
        from stock_opportunity_agent.research.evolution_core import default_information_plan
        from stock_opportunity_agent.research.evolution_plan_roles import LLMResearchController
        from stock_opportunity_agent.research.evolution_research_validation import (
            _normalize_research_state_output,
        )

        basic = {'requests': [{'projections': [
            {'projection_id': 'p', 'exact_text': 'The issuer develops products.'},
        ]}]}
        good = {'kind': 'basic_info', 'claim': 'The issuer develops products.',
                'projection_id': 'p', 'exact_text': 'The issuer develops products.'}
        metric = {'metric': 'price_shape', 'params': {'window_days': 180},
                  'values': {'return_pct': 22.4}, 'labels': {'trend': 'uptrend'}}
        bad = {'kind': 'basic_info', 'claim': 'Market momentum is favourable.',
               'projection_id': 'p', 'exact_text': format_computed_card_readable(metric)}
        invalid = ResearchState(
            current_beliefs=(good['claim'],),
            next_information_needs=(
                'What actual revenue results will be reported in 2026?',
                'Which customer contracts were disclosed by 2025-09-30?',
            ),
        ).to_dict()
        invalid['supporting_evidence'] = [good, bad]
        context = {'prediction_time': '2025-09-30T00:00:00+00:00'}
        with self.assertRaises(StructuredValidationError) as caught:
            _normalize_research_state_output(invalid, initialize=True,
                basic_info=basic, evaluation_context=context)
        self.assertEqual([issue.code for issue in caught.exception.issues],
                         ['future_information_unavailable', 'basic_literal_not_grounded'])
        self.assertEqual(caught.exception.issues[1].paths, ('supporting_evidence[1]',))

        corrected = 'Which delivery schedules for 2026 were disclosed by 2025-09-30?'
        def repair(call):
            feedback = call['payload']['validation_feedback']
            base = feedback['invalid_output']
            self.assertEqual(base['supporting_evidence'], [good])
            self.assertEqual(base['current_beliefs'], invalid['current_beliefs'])
            self.assertEqual(base['next_information_needs'][1], invalid['next_information_needs'][1])
            return patch(call['payload']['output_patch_contract'],
                         {'op': 'replace', 'path': 'next_information_needs[0]', 'value': corrected})
        caller = PatchCaller(invalid, repair)
        controller = LLMResearchController(caller)
        controller.set_evaluation_context(datetime.fromisoformat(context['prediction_time']))
        controller.set_computed_metrics([metric])
        plan = default_information_plan()
        state = controller.initialize(plan, basic).value
        self.assertEqual(len(caller.calls), 2)
        self.assertEqual(state.next_information_needs, (corrected, invalid['next_information_needs'][1]))
        self.assertEqual(state.current_beliefs, tuple(invalid['current_beliefs']))
        self.assertEqual([ref.to_dict() for ref in state.supporting_evidence], [good])

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


class RuntimePriceContractTests(TestCase):
    """Exercise numeric guard, typed patches and production reflection salvage."""

    anchor = {"status": "available", "mean_adjusted_close": 6.494,
              "doubling_threshold": 12.988, "recent_close": 6.3}
    wrong = "Reaching 12.988 requires roughly a 106% gain from the baseline."
    correct = "Reaching 12.988 requires a 100% gain from the baseline."

    def test_named_anchors_and_unambiguous_targets_share_one_arithmetic_guard(self):
        from stock_opportunity_agent.research.evolution_output_validation import _price_reasoning_issues
        valid = (
            self.correct,
            "Reaching 12.988 requires a 106.16% gain from the most recent close.",
            "A 100% gain from baseline to the doubling threshold is definition arithmetic.",
            "A 106% gain from baseline is an uncertain scenario without a target.",
            "Reaching 12.988 is one scenario. A 106% gain from baseline is another.",
            "Reaching 12.988 or reaching 15.0 involves a 106% gain from baseline.",
            "Reaching 12.988 requires not a 106% gain from baseline.",
            "Reaching 12.988 requires a 106% gain from baseline is incorrect.",
        )
        self.assertEqual(_price_reasoning_issues(enumerate_text(valid), self.anchor), [])
        bad = _price_reasoning_issues((("reflection_items[2].brief", self.wrong),), self.anchor)
        self.assertEqual(bad[0].paths, ("reflection_items[2].brief",))
        self.assertEqual(bad[0].repair_context["expected_percent_change"], 100)
        for anchor in ({"status": "unavailable"}, {**self.anchor, "mean_adjusted_close": 0},
                       {**self.anchor, "mean_adjusted_close": float("nan")},
                       {**self.anchor, "mean_adjusted_close": True}):
            self.assertEqual(_price_reasoning_issues((("text", self.wrong),), anchor), [])
        decline = {"status": "available", "mean_adjusted_close": 10}
        self.assertEqual(_price_reasoning_issues((("text", "To 8 requires a 20% decline from baseline."),), decline), [])

    def test_baseline_multiple_is_checked_before_ordinary_value_and_state_codes_survive(self):
        from stock_opportunity_agent.research.evolution_research_validation import _anchor_restatement_issues
        issues = _anchor_restatement_issues(
            {"current_beliefs": ["Twice the baseline price is 6.494.", self.wrong]},
            {"evaluation_anchor": self.anchor},
        )
        self.assertEqual([i.code for i in issues],
                         ["research_state_anchor_arithmetic_invalid", "price_anchor_percent_change_invalid"])
        self.assertEqual([i.paths for i in issues], [("current_beliefs[0]",), ("current_beliefs[1]",)])
        self.assertTrue(all(i.allowed_repairs == ("replace", "remove") for i in issues))
        self.assertTrue(all(i.source_refs == ("evaluation_anchor",) for i in issues))

    def prediction(self):
        return {"candidate_judgment": "unlikely", "magnitude": None,
                "confidence": {"level": "medium"}, "session_id": "anonymous",
                "key_reasons": [self.wrong, "Source-backed operating deterioration."],
                "uncertainties": ["Unchanged coverage uncertainty."]}

    def test_predictor_patch_preserves_judgment_and_other_fields(self):
        from stock_opportunity_agent.research.evolution_plan_roles import LLMBlindPredictor
        original = self.prediction()
        def repair(call):
            self.assertEqual(call["payload"]["required_change_paths"], ["key_reasons[0]"])
            return patch(call["payload"]["output_patch_contract"],
                         {"op": "replace", "path": "key_reasons[0]", "value": self.correct})
        caller = PatchCaller(original, repair)
        result = LLMBlindPredictor(caller).predict({"prediction_baseline": self.anchor}).value
        self.assertEqual(result.key_reasons, (self.correct, original["key_reasons"][1]))
        self.assertEqual(result.uncertainties, tuple(original["uncertainties"]))
        self.assertEqual(result.candidate_judgment.value, original["candidate_judgment"])
        self.assertIn("named denominator", caller.calls[0]["system_prompt"])

    def reflection_inputs(self):
        from stock_opportunity_agent.research.evolution_core import GroundTruth
        original = self.prediction()
        original["key_reasons"][0] = self.correct
        return {"prediction_baseline": self.anchor}, _blind_prediction_from_role(original), GroundTruth(1.1)

    def reflection_package(self, call):
        source = call["payload"]["source_catalog"][0]
        row = {"category": "missing_information", "kind": "hypothesis",
               "brief": self.wrong, "detail": self.wrong,
               "scope": {"case_refs": source["case_refs"], "plan_refs": source["plan_refs"],
                         "conditions": "The runtime anchor is available."},
               "limitations": ["Not a causal conclusion."], "source_refs": [source["source_ref"]],
               "counter_refs": [], "outcome_claims": []}
        sibling = {**deepcopy(row), "brief": "Source coverage needs review.",
                   "detail": "The original packet may omit relevant disclosures."}
        return {"reflection_items": [row, sibling], "selected_reflection_refs": [], "no_findings_reason": None}

    def test_posthoc_brief_and_detail_receive_incremental_checks_not_copied_facts(self):
        from stock_opportunity_agent.research.evolution_plan_roles import LLMBlindPredictor
        saved = {}
        def initial(call):
            saved.update(self.reflection_package(call))
            return saved
        def repair_brief(call):
            self.assertEqual(call["payload"]["required_change_paths"],
                             ["reflection_items[0].brief", "reflection_items[0].detail"])
            return patch(call["payload"]["output_patch_contract"],
                         {"op": "replace", "path": "reflection_items[0].brief", "value": self.correct})
        def repair_detail(call):
            failed = call["payload"]["invalid_output"]
            self.assertEqual(failed["reflection_items"][0]["brief"], self.correct)
            self.assertEqual(failed["reflection_items"][1], saved["reflection_items"][1])
            self.assertEqual(call["payload"]["required_change_paths"], ["reflection_items[0].detail"])
            return patch(call["payload"]["output_patch_contract"],
                         {"op": "replace", "path": "reflection_items[0].detail", "value": self.correct})
        caller = PatchCaller(initial, repair_brief, repair_detail)
        context, prediction, truth = self.reflection_inputs()
        result = LLMBlindPredictor(caller).reflect(context, prediction, truth).value
        self.assertEqual(result.reflection_items[0].detail, self.correct)
        self.assertEqual(result.reflection_items[1].detail, saved["reflection_items"][1]["detail"])
        self.assertEqual(result.missing_information, (self.correct, saved["reflection_items"][1]["detail"]))
        self.assertIn("Do not copy incorrect saved numerical reasoning", caller.calls[0]["system_prompt"])
        self.assertEqual(prediction.key_reasons[0], self.correct)

    def test_posthoc_salvage_revalidates_role_arithmetic_and_retains_valid_sibling(self):
        from stock_opportunity_agent.research.evolution_plan_roles import LLMBlindPredictor
        caller = PatchCaller(self.reflection_package, lambda call: patch(
            call["payload"]["output_patch_contract"],
            {"op": "replace", "path": "reflection_items[0].brief",
             "value": self.wrong.replace("106%", "107%")},
        ))
        caller.max_structured_corrections = 1
        context, prediction, truth = self.reflection_inputs()
        result = LLMBlindPredictor(caller).reflect(context, prediction, truth).value
        self.assertEqual(len(result.reflection_items), 1)
        self.assertEqual(result.reflection_items[0].brief, "Source coverage needs review.")
        self.assertEqual(len(caller.calls), 2)

    def test_mechanical_scope_repair_cannot_bypass_role_numeric_check(self):
        from stock_opportunity_agent.research.evolution_reflection_memory import ReflectionMemoryIndex
        from stock_opportunity_agent.research.evolution_plan_roles import _reflection_salvage_fallback
        from stock_opportunity_agent.research.evolution_output_validation import _price_reasoning_issues
        index = ReflectionMemoryIndex.from_case_rows(
            [{"source_identity": "case:price", "candidate_judgment_feedback": {"binary_correct": True}}],
            owner_ref="case:price",
        )
        call = {"payload": {"source_catalog": index.source_catalog()}}
        package = self.reflection_package(call)
        package["reflection_items"][0]["scope"]["case_refs"] = ["case:unknown"]
        def validate(items):
            issues = _price_reasoning_issues(
                ((f"reflection_items[{i}].{field}", getattr(item, field))
                 for i, item in enumerate(items) for field in ("brief", "detail")), self.anchor,
            )
            if issues:
                raise StructuredValidationError(issues)
        next_output, _actions = _reflection_salvage_fallback(
            index, "case", "case:price", item_validator=validate,
        )(package, ValidationError("source scope and arithmetic are invalid"))
        self.assertEqual(next_output["reflection_items"], [package["reflection_items"][1]])
        restored = index.create_items(next_output["reflection_items"], level="case", owner_ref="case:price")
        validate(restored)


def enumerate_text(values):
    """Bind standalone numeric guard fixtures to exact source text positions."""
    return ((f"text[{index}]", text) for index, text in enumerate(values))
