"""Mechanical patch edits preserve valid operations and the original role validator."""

from copy import deepcopy
from types import SimpleNamespace
from unittest import TestCase

from stock_opportunity_agent.models import StructuredValidationError, ValidationError, ValidationIssue
from stock_opportunity_agent.research.evolution_core import CandidateExecutionRejected, ResearchState
from stock_opportunity_agent.research.evolution_output_validation import _complete_parsed_role
from stock_opportunity_agent.research.evolution_plan_roles import _DocumentChannelCaller
from stock_opportunity_agent.research.evolution_state_patch import (
    apply_state_patch, state_patch_contract, state_patch_hash, state_patch_mechanics_contract)
from stock_opportunity_agent.research.stage_contracts import validate_stage_input
from tests.test_evolution_state_patch import PatchCaller, obligation, patch


class PatchMechanicsRepairTests(TestCase):
    def setUp(self):
        self.base = ResearchState(hypotheses=("Preserved thesis",),
                                  next_information_needs=("Old unresolved need",)).to_dict()
        self.contract = state_patch_contract(self.base)
        self.native = patch(self.contract,
            {"op": "append", "path": "current_beliefs", "value": "Already authored observation"},
            {"op": "replace", "path": "next_information_needs[0]", "value": "Narrowed unresolved need"},
            {"op": "remove", "path": "next_information_needs[0]"},
            {"op": "replace", "path": "decision", "value": "finalize"})

    def test_all_conflicting_operations_are_named_and_correct_siblings_are_immutable(self):
        repair = state_patch_mechanics_contract(self.base, self.native, contract=self.contract)
        self.assertEqual([item["operation_index"] for item in repair["issues"]], [1, 2])
        nested = repair["output_patch_contract"]
        fixed = apply_state_patch(self.native, patch(nested,
            {"op": "remove", "path": "operations[2]"}), contract=nested)
        self.assertEqual(fixed["operations"][0], self.native["operations"][0])
        self.assertEqual(fixed["operations"][-1], self.native["operations"][-1])
        merged = apply_state_patch(self.base, fixed, contract=self.contract)
        self.assertEqual(merged["hypotheses"], self.base["hypotheses"])
        self.assertEqual(merged["next_information_needs"], ["Narrowed unresolved need"])
        for operation in ({"op": "replace", "path": "operations[0].value", "value": "drift"},
                          {"op": "append", "path": "operations", "value": self.native["operations"][0]},
                          {"op": "replace", "path": "base_hash", "value": "stale"}):
            with self.subTest(operation=operation), self.assertRaises(ValidationError):
                apply_state_patch(self.native, patch(nested, operation), contract=nested)

    def test_shape_errors_and_group_append_limits_share_the_complete_frontier(self):
        base = {"rows": ["old"]}
        contract = state_patch_contract(base, mode="correction", obligations=[
            obligation("rows", repairs=("add",))])
        native = patch(contract, 3, {"op": "append", "path": "rows", "value": "a"},
                       {"op": "append", "path": "rows", "value": "b"})
        with self.assertRaises(ValidationError):
            apply_state_patch(base, native, contract=contract)
        repair = state_patch_mechanics_contract(base, native, contract=contract)
        self.assertEqual([item["operation_index"] for item in repair["issues"]], [0, 1, 2])
        duplicate = patch(contract, native["operations"][1], native["operations"][1])
        self.assertIsNone(state_patch_mechanics_contract(base, duplicate, contract=contract))
        self.assertEqual(apply_state_patch(base, duplicate, contract=contract)["rows"], ["old", "a"])

    def test_stale_hash_invalid_envelope_and_identity_guard_cannot_get_repair_authority(self):
        for native in ({**self.native, "base_hash": "stale"},
                       {**self.native, "extra": True},
                       {**self.native, "operations": "wrong"},
                       {**self.native, "operations": [float("nan")]}):
            with self.subTest(native=native):
                self.assertIsNone(state_patch_mechanics_contract(self.base, native, contract=self.contract))
        guarded = {**self.contract, "identity_guards": [{"path": "hypotheses[0]", "field": "ref", "value": "wrong"}]}
        self.assertIsNone(state_patch_mechanics_contract(self.base, self.native, contract=guarded))
        unauthorized = patch(self.contract, {"op": "replace", "path": "foreign", "value": "drift"})
        self.assertIsNone(state_patch_mechanics_contract(self.base, unauthorized, contract=self.contract))

    def run_role(self, caller, parser=ResearchState.from_dict):
        return _complete_parsed_role(caller, stage="research_controller_reflect", system_prompt="Research.",
            payload={"research_state": self.base, "signal_batch": [], "need_transition_contract": {}},
            parser=parser, allow_outcomes=False, output_patch_base=self.base,
            patch_corrections=True, stable_correction_prefix=True)

    def test_role_repairs_only_patch_operations_and_document_catalog_is_not_repeated(self):
        snapshots = []
        def catalog():
            snapshots.append(True)
            return {"items": ["large directory " * 1000]}
        def correction(call):
            payload = call["payload"]
            self.assertNotIn("document_catalog", payload)
            self.assertNotIn("validation_feedback", payload)
            self.assertEqual(payload["invalid_patch"], self.native)
            self.assertEqual(payload["original_patch_base"], self.base)
            audit = validate_stage_input(call["stage"], payload, allow_outcomes=False)
            self.assertEqual(audit["phase"], "patch_mechanics")
            return patch(payload["output_patch_contract"], {"op": "remove", "path": "operations[2]"})
        caller = PatchCaller(self.native, correction)
        caller.max_structured_corrections = 1
        wrapper = _DocumentChannelCaller(caller, SimpleNamespace(catalog_view=catalog))
        result, usage = self.run_role(wrapper)
        self.assertEqual(result.current_beliefs, ("Already authored observation",))
        self.assertEqual(result.next_information_needs, ("Narrowed unresolved need",))
        self.assertEqual(result.hypotheses, ("Preserved thesis",))
        self.assertEqual(usage.llm_calls, 2)
        self.assertEqual(len(snapshots), 1)

    def test_mechanical_success_does_not_bypass_original_semantic_validation(self):
        validations = []
        def parser(value):
            validations.append(deepcopy(value))
            raise StructuredValidationError([ValidationIssue(code="unsupported_fact",
                message="Authored observation lacks required evidence.", paths=("current_beliefs[0]",))])
        caller = PatchCaller(self.native, lambda call: patch(call["payload"]["output_patch_contract"],
            {"op": "remove", "path": "operations[2]"}))
        caller.max_structured_corrections = 1
        with self.assertRaises(CandidateExecutionRejected):
            self.run_role(caller, parser)
        self.assertTrue(validations)
        self.assertEqual(validations[0]["current_beliefs"], ["Already authored observation"])
        self.assertEqual(self.base["current_beliefs"], [])

    def test_blind_boundary_and_normal_dependencies_survive_mechanics_phase(self):
        repair = state_patch_mechanics_contract(self.base, self.native, contract=self.contract)
        payload = {"invalid_patch": self.native, "original_patch_base": self.base,
            "original_patch_contract": self.contract, "patch_mechanics_repair": repair,
            "output_patch_contract": repair["output_patch_contract"]}
        with self.assertRaises(ValidationError):
            validate_stage_input("research_controller_reflect_patch_mechanics_correction", payload, allow_outcomes=True)
        with self.assertRaises(ValidationError):
            validate_stage_input("research_controller_reflect", payload, allow_outcomes=False)
