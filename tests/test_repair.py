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
        # Union semantics: a declared-but-uncited case is dropped and a
        # cited source's coverage replaces the declaration entirely.
        ghost_package = {
            "reflection_items": [
                {
                    "category": "missing_information",
                    "source_refs": ["reflection:a"],
                    "outcome_claims": [],
                    "scope": {
                        "case_refs": ["case:ghost"],
                        "plan_refs": [],
                        "conditions": "x",
                    },
                }
            ],
        }
        repaired_ghost, _ops = scope_narrow_to_support(ghost_package, resolver)
        self.assertEqual(
            repaired_ghost["reflection_items"][0]["scope"]["case_refs"],
            ["case:1"],
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


class UnifiedLadderWiringTests(unittest.TestCase):
    def test_v148_frontier_scope_repair_with_resolver(self):
        # End-to-end: a plan-critic package with an over-broad scope is
        # accepted on the first answer through the index-aware L2 rung —
        # no LLM correction round is spent.
        import sys

        sys.path.insert(0, "tests")
        from tests.evolution_runtime_test_support import (
            LLMPlanCritic,
            ScriptedRoleCaller,
            default_information_plan,
            PlanMetrics,
        )
        from tests.scheme_evolution_test_support import (
            make_trajectory,
            MagnitudeClass,
        )
        from stock_opportunity_agent.research.evolution_reflection_memory import (
            ReflectionMemoryIndex,
        )

        snapshot = {
            "source_identity": "case:scope",
            "candidate_judgment_feedback": {"binary_correct": False},
            "magnitude_feedback": {
                "magnitude_applicable": True,
                "magnitude_correct": False,
            },
        }
        from stock_opportunity_agent.research.evolution_plan_roles import (
            CaseReflectionEvidence,
        )

        trajectory = make_trajectory(
            "scope", 1.5, True, MagnitudeClass.TWO_TO_THREE
        )
        plan = default_information_plan()
        from stock_opportunity_agent.artifacts import canonical_json_hash

        critic_owner = "reflection_plan:" + canonical_json_hash(
            plan.canonical_dict()
        )
        source_rows = [
            CaseReflectionEvidence.from_trajectory(
                trajectory, case_index=1
            ).to_model_dict()
        ]
        index_hint = ReflectionMemoryIndex.from_case_rows(
            source_rows, owner_ref=critic_owner
        )
        source = index_hint.source_catalog()[0]
        package = {
            "reflection_items": [
                {
                    "category": "repeated_failure_modes",
                    "kind": "fact",
                    "brief": "Both axes failed without a quantified bridge.",
                    "detail": "Binary and magnitude both wrong.",
                    "scope": {
                        "case_refs": list(source["case_refs"]) + ["case:ghost"],
                        "plan_refs": [],
                        "conditions": "Always.",
                    },
                    "limitations": [],
                    "source_refs": [source["source_ref"]],
                    "counter_refs": [],
                    "outcome_claims": [
                        {
                            "source_ref": source["source_ref"],
                            "axis": "binary",
                            "correct": False,
                        }
                    ],
                }
            ],
            "selected_reflection_refs": [],
            "no_findings_reason": None,
        }
        caller = ScriptedRoleCaller([package])
        critic = LLMPlanCritic(caller)
        metrics = PlanMetrics(
            binary_precision=0.5,
            binary_recall=0.5,
            binary_f1=0.5,
            magnitude_accuracy=0.5,
            magnitude_macro_f1=0.5,
            true_positive=1,
            false_positive=1,
            true_negative=1,
            false_negative=1,
            sample_count=4,
        )
        reflection = critic.critique(
            plan=plan,
            trajectories=(trajectory,),
            metrics=metrics,
        )
        self.assertEqual(len(reflection.reflection_items), 1)
        # The ghost case was scoped out mechanically; one call, no correction.
        self.assertIsNone(reflection.no_findings_reason)
        self.assertEqual(len(caller.calls), 1)

    def test_v148_salvage_repairs_scope_before_dropping(self):
        from stock_opportunity_agent.research.evolution_plan_roles import (
            _reflection_salvage_fallback,
        )
        from stock_opportunity_agent.research.evolution_reflection_memory import (
            ReflectionMemoryIndex,
        )

        snapshot = {
            "source_identity": "case:salv",
            "candidate_judgment_feedback": {"binary_correct": False},
            "magnitude_feedback": {
                "magnitude_applicable": True,
                "magnitude_correct": False,
            },
        }
        index = ReflectionMemoryIndex.from_case_rows(
            [snapshot], owner_ref="case:salv"
        )
        source = index.source_catalog()[0]
        row = {
            "category": "missing_information",
            "kind": "fact",
            "brief": "Missing forward bridge.",
            "detail": "No quantified bridge was supplied.",
            "scope": {
                "case_refs": ["case:ghost"],
                "plan_refs": [],
                "conditions": "Always.",
            },
            "limitations": [],
            "source_refs": [source["source_ref"]],
            "counter_refs": [],
            "outcome_claims": [],
        }
        salvage = _reflection_salvage_fallback(index, "case", "case:salv")
        result = salvage(
            {
                "reflection_items": [row],
                "selected_reflection_refs": [],
                "no_findings_reason": None,
            },
            ValidationError("scope not covered"),
        )
        self.assertIsNotNone(result)
        next_output, actions = result
        # The row was repaired (scope narrowed), not removed.
        self.assertEqual(len(next_output["reflection_items"]), 1)
        self.assertEqual(actions["removed_paths"], ())
        self.assertTrue(actions["normalized_paths"])
        self.assertIsInstance(next_output["reflection_items"][0], dict)
        restored = index.create_items(next_output["reflection_items"], level="case", owner_ref="case:salv")
        self.assertEqual(restored[0].detail, row["detail"])

    def test_v148_complete_json_repaired_rescues_truncation(self):
        import json as _json

        from stock_opportunity_agent.research.evolution_output_validation import (
            complete_json_repaired,
        )
        from stock_opportunity_agent.research.evolution_transport import (
            StructuredOutputInvalid,
        )
        from tests.evolution_runtime_test_support import AgentUsage

        truncated = (
            '{"spec": {"signal_id": "abc", "definition": "measures gro'
        )

        class TruncatingCaller:
            def complete_json(self, **kwargs):
                raise StructuredOutputInvalid(
                    "truncated",
                    truncated,
                    AgentUsage(llm_calls=1, tokens=50),
                    output_tokens=50,
                    output_token_limit=100,
                )

        def parse(value):
            assert value["spec"]["signal_id"] == "abc"
            return value

        value, usage = complete_json_repaired(
            TruncatingCaller(), parse=parse, stage="unit"
        )
        self.assertEqual(value["spec"]["signal_id"], "abc")
        self.assertEqual(usage.tokens, 50)


class PromotedFallbackTests(unittest.TestCase):
    def test_v149_promotion_gated_to_mechanical_quantity_codes(self):
        # 数值断言失败（claim_quantity_not_supported）被提升 fallback
        # 在首答解决；语义类失败不提升（仍走 LLM 纠错）。
        import sys

        sys.path.insert(0, "tests")
        from tests.evolution_runtime_test_support import (
            LLMResearchController,
            ScriptedRoleCaller,
            default_information_plan,
        )
        from tests.scheme_evolution_test_support import NOW

        exact_claim = "The adjusted close was 24.37."
        literal = '{"adjusted_close":24.37,"as_of_date":"2025-09-29"}'
        invalid = {
            "hypotheses": ["Market state may anchor the thesis."],
            "current_beliefs": [
                "The adjusted close was 24.37, near the recent high."
            ],
            "supporting_evidence": [
                {
                    "kind": "basic_info",
                    "claim": exact_claim,
                    "projection_id": "projection_market",
                    "exact_text": literal,
                }
            ],
            "contradictions": [],
            "resolved_questions": [],
            "open_questions": [],
            "next_information_needs": [
                "What disclosures could change expectations?"
            ],
            "decision": "continue",
        }
        caller = ScriptedRoleCaller([invalid])
        from datetime import timezone

        initialized = LLMResearchController(caller).initialize(
            default_information_plan(),
            {
                "requests": [
                    {
                        "projections": [
                            {
                                "projection_id": "projection_market",
                                "exact_text": literal,
                            }
                        ]
                    }
                ]
            },
        )
        # One call, no LLM correction; the surviving belief is the exact
        # claim copy or nothing (removal), never the unsupported rewrite.
        self.assertEqual(len(caller.calls), 1)
        beliefs = initialized.value.current_beliefs
        self.assertTrue(
            all(belief == exact_claim for belief in beliefs), beliefs
        )

    def test_v149_flatten_text_array_objects_extracts_unique_prose(self):
        from stock_opportunity_agent.research.repair import (
            flatten_text_array_objects,
        )

        state = {
            "contradictions": [
                {"claim": "Orders contradicted the thesis.", "group": "counter"},
                {"claim": "Ambiguous.", "note": "other", "text": "strings"},
                "Already text.",
            ],
            "next_information_needs": ["Check orders."],
        }
        repaired, ops = flatten_text_array_objects(state)
        # claim 字段优先于其余字符串字段，包括多候选情形（唯一散文域）。
        self.assertEqual(
            repaired["contradictions"],
            [
                "Orders contradicted the thesis.",
                "Ambiguous.",
                "Already text.",
            ],
        )
        self.assertEqual(len(ops), 2)
        self.assertEqual(ops[0].path, "contradictions[0]")
        self.assertEqual(ops[1].path, "contradictions[1]")
        self.assertEqual(ops[0].action, "flatten_text_array_object")
        self.assertEqual(ops[0].path, "contradictions[0]")


class GeneralityTests(unittest.TestCase):
    def test_v150_text_fields_derive_from_owning_model(self):
        # 单一事实源：给 ResearchState 增加一个 tuple[str, ...] 字段，
        # 修复链自动覆盖（这里验证派生函数的判据本身）。
        import dataclasses
        import typing
        from stock_opportunity_agent.research.repair import _TEXT_ARRAY_FIELDS

        self.assertIn("open_questions", _TEXT_ARRAY_FIELDS)
        self.assertNotIn("supporting_evidence", _TEXT_ARRAY_FIELDS)
        self.assertNotIn("decision", _TEXT_ARRAY_FIELDS)

    def test_v150_registry_accepts_new_shape_family(self):
        from stock_opportunity_agent.research.repair import (
            REPAIR_CHAIN_REGISTRY,
            apply_mechanical_repairs,
            mechanical_repairs_for,
            register_repair_chain,
        )
        from stock_opportunity_agent.models import ValidationError

        def is_widget(value):
            return isinstance(value, dict) and "widget_rows" in value

        def drop_empty_widget_rows(value, resolver, level_categories=None):
            def repair(mapping):
                kept = [
                    row
                    for row in mapping["widget_rows"]
                    if isinstance(row, str) and row.strip()
                ]
                if len(kept) == len(mapping["widget_rows"]):
                    return dict(mapping), []
                result = dict(mapping)
                result["widget_rows"] = kept
                return result, ["dropped"]

            return [repair]

        register_repair_chain(is_widget, drop_empty_widget_rows)
        try:
            widget = {"widget_rows": ["real row", ""]}
            self.assertTrue(mechanical_repairs_for(widget))

            def parse(value):
                if any(not row.strip() for row in value["widget_rows"]):
                    raise ValidationError("empty row")
                return value

            result = apply_mechanical_repairs(widget, parse)
            self.assertIsNotNone(result)
            self.assertEqual(result[0]["widget_rows"], ["real row"])
        finally:
            REPAIR_CHAIN_REGISTRY.pop()

    def test_v150_split_respects_level_categories(self):
        from stock_opportunity_agent.research.repair import (
            split_mixed_axis_items,
        )

        package = {
            "reflection_items": [
                {
                    "category": "failed_patterns",
                    "brief": "Mixed outcome.",
                    "detail": "Both axes.",
                    "source_refs": ["reflection:a"],
                    "counter_refs": [],
                    "outcome_claims": [
                        {"source_ref": "reflection:a", "axis": "binary", "correct": True},
                        {"source_ref": "reflection:a", "axis": "magnitude", "correct": False},
                    ],
                    "scope": {"case_refs": ["c"], "plan_refs": [], "conditions": "z"},
                    "limitations": [],
                }
            ],
        }
        # case 层没有 failed_patterns/successful_patterns：传入层级词汇后
        # 不再产出该层不存在的类别，行留给下一梯级。
        case_categories = {
            "decision_drivers", "why_prediction_failed", "misleading_signals",
            "ignored_evidence", "missing_information", "plan_issues",
        }
        repaired, ops = split_mixed_axis_items(package, case_categories)
        self.assertEqual(len(repaired["reflection_items"]), 1)
        self.assertEqual(ops, [])
        # plan 层两类都存在：正常拆分。
        plan_categories = {
            "successful_patterns", "failed_patterns", "repeated_failure_modes",
        }
        repaired, ops = split_mixed_axis_items(package, plan_categories)
        self.assertEqual(len(repaired["reflection_items"]), 2)
        self.assertEqual(len(ops), 1)

    def test_v150_gate_codes_single_sourced(self):
        from stock_opportunity_agent.research.repair import (
            MECHANICAL_FALLBACK_CODES,
        )
        from stock_opportunity_agent.research.evolution_output_validation import (
            MECHANICAL_FALLBACK_CODES as frontier_codes,
        )

        self.assertIs(MECHANICAL_FALLBACK_CODES, frontier_codes)
        self.assertIn("claim_quantity_not_supported", MECHANICAL_FALLBACK_CODES)


class PartialMechanicalProgressTests(unittest.TestCase):
    def test_partial_shape_repair_is_correction_base_while_semantic_issue_remains(self):
        from stock_opportunity_agent.models import StructuredValidationError, ValidationIssue
        from stock_opportunity_agent.research.evolution_output_validation import _complete_parsed_role
        from stock_opportunity_agent.research.evolution_core import AgentUsage

        class Caller:
            max_structured_corrections = 1
            def __init__(self):
                self.payloads = []
            def complete_json(self, **kwargs):
                self.payloads.append(kwargs["payload"])
                return ({"next_information_needs": ["Need guidance."], "open_questions": ["Need guidance."], "decision": "wrong"} if len(self.payloads) == 1 else
                        {"next_information_needs": ["Need guidance."], "open_questions": [], "decision": "continue"}), AgentUsage(llm_calls=1)
        def parse(value):
            issues = []
            if value["open_questions"]:
                issues.append(ValidationIssue(code="duplicate_question", message="Duplicated need", paths=("open_questions[0]",), allowed_repairs=("remove",)))
            if value["decision"] != "continue":
                issues.append(ValidationIssue(code="bad_decision", message="Decision invalid", paths=("decision",)))
            if issues:
                raise StructuredValidationError(issues)
            return value
        caller = Caller()
        result, _ = _complete_parsed_role(caller, stage="partial_test", system_prompt="Return object", payload={}, parser=parse, allow_outcomes=False, stable_correction_prefix=True)
        feedback = caller.payloads[1]["validation_feedback"]
        self.assertEqual(feedback["invalid_output"]["open_questions"], [])
        self.assertEqual([o["issue_code"] for o in feedback["obligations"]], ["bad_decision"])
        self.assertEqual(result["next_information_needs"], ["Need guidance."])
