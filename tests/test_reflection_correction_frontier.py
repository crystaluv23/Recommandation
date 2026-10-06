"""Complete typed frontiers preserve reflection siblings and outcome provenance."""

from copy import deepcopy
from unittest import TestCase

from stock_opportunity_agent.models import StructuredValidationError, ValidationError
from stock_opportunity_agent.research.evolution_output_validation import (
    _complete_parsed_role, _validation_obligations,
)
from stock_opportunity_agent.research.evolution_plan_roles import (
    _structured_reflection_contract, _structured_reflection_items,
)
from stock_opportunity_agent.research.evolution_state_patch import (
    apply_state_patch, state_patch_contract,
)
from tests.test_evolution_state_patch import PatchCaller, patch
from tests.test_reflection_statistics import registered, statistical_item


class ReflectionCorrectionFrontierTests(TestCase):
    def package(self):
        index = registered()
        good = statistical_item(index, "binary_f1=0.733.")
        failed = statistical_item(index, "underestimate_count=6.", "magnitude_diagnostics")
        failed["category"] = "failed_patterns"
        success = statistical_item(index, "binary_f1=0.733.")
        success.update(category="successful_patterns", detail="Observed binary_f1=0.733.")
        counter = statistical_item(index, "missed_surge_count=2.", "magnitude_diagnostics")
        counter["counter_refs"] = ["unissued:counter"]
        return index, {"reflection_items": [good, failed, success, counter],
                       "selected_reflection_refs": [], "no_findings_reason": None}

    def test_one_correction_receives_all_independent_rows_and_preserves_sibling(self):
        index, package = self.package()
        original = deepcopy(package)

        def parse(value):
            return _structured_reflection_items(value, index=index, level="plan", owner_ref="plan:a")

        def correct(request):
            feedback = request["payload"].get("validation_feedback", request["payload"])
            self.assertEqual(feedback["obligation_count"], 3)
            self.assertEqual([row["must_change_paths"] for row in feedback["obligations"]], [
                ["reflection_items[1].outcome_claims"],
                ["reflection_items[2].outcome_claims"],
                ["reflection_items[3].counter_refs"],
            ])
            return patch(request["payload"]["output_patch_contract"],
                {"op": "replace", "path": "reflection_items[1].category", "value": "repeated_failure_modes"},
                {"op": "replace", "path": "reflection_items[2].category", "value": "repeated_failure_modes"},
                {"op": "remove", "path": "reflection_items[3].counter_refs[0]"})

        caller = PatchCaller(package, correct)
        result, usage = _complete_parsed_role(caller, stage="plan_critic",
            system_prompt=_structured_reflection_contract("plan"), payload={},
            parser=parse, allow_outcomes=True, patch_corrections=True)
        self.assertEqual(len(caller.calls), 2)
        self.assertEqual(usage.llm_calls, 2)
        self.assertEqual(len(result[0]), 4)
        for i, item in enumerate(result[0]):
            expected = deepcopy(original["reflection_items"][i])
            if i in (1, 2):
                expected["category"] = "repeated_failure_modes"
            if i == 3:
                expected["counter_refs"] = []
            self.assertEqual({key: item.to_dict()[key] for key in expected}, expected)
        self.assertEqual(package, original)

    def test_claim_append_remains_bounded_and_canonical_revalidation_remains(self):
        index, package = self.package()
        with self.assertRaises(StructuredValidationError) as caught:
            _structured_reflection_items(package, index=index, level="plan", owner_ref="plan:a")
        obligations = _validation_obligations(caught.exception, package)["obligations"]
        contract = state_patch_contract(package, mode="correction", obligations=obligations)
        source_ref = package["reflection_items"][1]["source_refs"][0]
        operation = {"op": "append", "path": "reflection_items[1].outcome_claims",
                     "value": {"source_ref": source_ref, "axis": "magnitude", "correct": False}}
        invalid = apply_state_patch(package, patch(contract, operation), contract=contract)
        with self.assertRaises(ValidationError):
            apply_state_patch(package, patch(contract, operation,
                {**operation, "value": {**operation["value"], "axis": "binary"}}), contract=contract)
        with self.assertRaises(StructuredValidationError) as caught:
            _structured_reflection_items(invalid, index=index, level="plan", owner_ref="plan:a")
        self.assertIn("contradicts canonical feedback", str(caught.exception))
        for level in ("plan", "round"):
            self.assertIn("Aggregate statistic sources have no individual canonical outcome booleans",
                          _structured_reflection_contract(level))

    def test_case_first_frontier_includes_every_independent_outcome_row(self):
        from tests.test_evolution_reflection_memory import authored, case
        from stock_opportunity_agent.research.evolution_reflection_memory import ReflectionMemoryIndex

        index = ReflectionMemoryIndex.from_case_rows([case()], owner_ref="plan:a")
        source = index.source_catalog()[0]
        good = authored(source)
        failed = authored(source, category="why_prediction_failed")
        success = authored(source, category="decision_drivers")
        with self.assertRaises(StructuredValidationError) as caught:
            _structured_reflection_items({"reflection_items": [good, failed, success],
                "selected_reflection_refs": []}, index=index, level="case", owner_ref="case:a")
        self.assertEqual([issue.paths for issue in caught.exception.issues], [
            ("reflection_items[1].outcome_claims",), ("reflection_items[2].outcome_claims",)])
        self.assertEqual(index.brief_view()["items"], [])
