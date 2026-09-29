"""Content-level tests for the mechanical repair ladder."""

import unittest

from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.repair import (
    RepairOp,
    apply_mechanical_repairs,
    claim_refs_into_source_refs,
    complete_truncated_json,
    drop_duplicate_open_questions,
    drop_empty_text_rows,
    mechanical_repairs_for,
    scope_narrow_to_support,
    split_mixed_axis_items,
    strip_json_fences,
)


class L0JsonRepairTests(unittest.TestCase):
    def test_v147_truncated_json_closes_brackets_and_strings(self):
        truncated = '{"reflection_items": [{"brief": "order catalysts underestim'
        repair = complete_truncated_json(truncated)
        self.assertIsNotNone(repair)
        candidate, ops = repair
        self.assertEqual(ops[0].action, "complete_truncated_json")
        self.assertTrue(candidate.endswith('"}]}'))
        import json

        value = json.loads(candidate)
        self.assertEqual(
            value["reflection_items"][0]["brief"],
            "order catalysts underestim",
        )

    def test_v147_dangling_comma_and_colon_are_dropped(self):
        import json

        candidate, _ops = complete_truncated_json('{"a": [1, 2,')
        self.assertEqual(json.loads(candidate), {"a": [1, 2]})

    def test_v147_fences_stripped_and_complete_json_untouched(self):
        self.assertEqual(strip_json_fences('```json\n{"a": 1}\n```'), '{"a": 1}')
        # Already-complete JSON is not a truncation candidate.
        self.assertIsNone(complete_truncated_json('{"a": 1}'))
        # Plain prose is never treated as truncated JSON.
        self.assertIsNone(complete_truncated_json("The thesis is unsupported."))


class L2MechanicalRepairTests(unittest.TestCase):
    def test_v147_claim_refs_registered_into_source_refs(self):
        package = {
            "reflection_items": [
                {
                    "category": "repeated_failure_modes",
                    "source_refs": ["reflection:a"],
                    "outcome_claims": [
                        {"source_ref": "reflection:a", "axis": "binary", "correct": False},
                        {"source_ref": "reflection:b", "axis": "binary", "correct": False},
                    ],
                }
            ],
            "selected_reflection_refs": [],
        }
        repaired, ops = claim_refs_into_source_refs(package)
        self.assertEqual(
            repaired["reflection_items"][0]["source_refs"],
            ["reflection:a", "reflection:b"],
        )
        self.assertEqual(ops[0].action, "claim_refs_into_source_refs")
        self.assertEqual(
            ops[0].path, "reflection_items[0].source_refs"
        )

    def test_v147_scope_narrows_to_resolvable_citation_closure(self):
        def resolver(ref):
            return {
                "reflection:a": {"case_refs": ["case:1"], "plan_refs": []},
                "reflection:b": {"case_refs": ["case:2"], "plan_refs": []},
            }.get(ref)

        package = {
            "reflection_items": [
                {
                    "category": "repeated_failure_modes",
                    "source_refs": ["reflection:a"],
                    "outcome_claims": [
                        {"source_ref": "reflection:b", "axis": "binary", "correct": False},
                    ],
                    "scope": {
                        "case_refs": ["case:1", "case:2", "case:3"],
                        "plan_refs": [],
                        "conditions": "x",
                    },
                }
            ],
        }
        repaired, ops = scope_narrow_to_support(package, resolver)
        self.assertEqual(
            repaired["reflection_items"][0]["scope"]["case_refs"],
            ["case:1", "case:2"],
        )
        self.assertEqual(ops[0].action, "scope_narrow_to_support")

    def test_v147_mixed_axis_item_splits_into_single_axis_forms(self):
        package = {
            "reflection_items": [
                {
                    "category": "why_prediction_failed",
                    "brief": "Direction right, magnitude underestimated.",
                    "detail": "binary correct while class wrong.",
                    "source_refs": ["reflection:a"],
                    "outcome_claims": [
                        {"source_ref": "reflection:a", "axis": "binary", "correct": True},
                        {"source_ref": "reflection:a", "axis": "magnitude", "correct": False},
                    ],
                    "scope": {"case_refs": ["case:1"], "plan_refs": [], "conditions": "c"},
                }
            ],
        }
        repaired, ops = split_mixed_axis_items(package)
        self.assertEqual(len(repaired["reflection_items"]), 2)
        categories = [row["category"] for row in repaired["reflection_items"]]
        self.assertEqual(
            sorted(categories), ["decision_drivers", "why_prediction_failed"]
        )
        for row in repaired["reflection_items"]:
            self.assertEqual(row["brief"], "Direction right, magnitude underestimated.")
            self.assertEqual(len(row["outcome_claims"]), 1)
        self.assertEqual(ops[0].action, "split_mixed_axis_item")

    def test_v147_duplicate_open_questions_removed_deterministically(self):
        state = {
            "next_information_needs": ["Check order disclosures."],
            "open_questions": [
                "Check order disclosures.",
                "Will adoption accelerate?",
            ],
        }
        repaired, ops = drop_duplicate_open_questions(state)
        self.assertEqual(repaired["open_questions"], ["Will adoption accelerate?"])
        self.assertEqual(ops[0].action, "drop_duplicate_open_question")

    def test_v147_empty_text_rows_dropped(self):
        state = {
            "hypotheses": ["Real hypothesis.", "   "],
            "current_beliefs": [],
        }
        repaired, ops = drop_empty_text_rows(state)
        self.assertEqual(repaired["hypotheses"], ["Real hypothesis."])
        self.assertEqual(ops[0].path, "hypotheses[1]")

    def test_v147_apply_accepts_only_full_validator_pass(self):
        package = {
            "reflection_items": [
                {
                    "category": "repeated_failure_modes",
                    "source_refs": ["reflection:a"],
                    "outcome_claims": [
                        {"source_ref": "reflection:a", "axis": "binary", "correct": False},
                        {"source_ref": "reflection:b", "axis": "binary", "correct": False},
                    ],
                }
            ],
            "selected_reflection_refs": [],
        }

        def strict_parse(value):
            for row in value["reflection_items"]:
                claim_refs = {
                    claim["source_ref"] for claim in row["outcome_claims"]
                }
                if not claim_refs <= set(row["source_refs"]):
                    raise ValidationError("claim outside source_refs")
            return value

        result = apply_mechanical_repairs(package, strict_parse)
        self.assertIsNotNone(result)
        parsed, ops = result
        self.assertEqual(len(ops), 1)

        def rejecting_parse(value):
            raise ValidationError("semantic failure no repair can fix")

        self.assertIsNone(
            apply_mechanical_repairs(package, rejecting_parse)
        )

    def test_v147_repair_chain_selects_by_output_shape(self):
        self.assertTrue(mechanical_repairs_for({"reflection_items": []}))
        self.assertTrue(mechanical_repairs_for({"next_information_needs": []}))
        self.assertEqual(mechanical_repairs_for({"unrelated": 1}), [])


if __name__ == "__main__":
    unittest.main()
