"""Runtime-owned aggregate provenance and incremental reflection acceptance."""
import json
from copy import deepcopy
from dataclasses import replace
from unittest import TestCase

from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.research.evolution_core import (
    MagnitudeClass, PlanMetaReflection, RoundMetaEntry, score_predictions,
)
from stock_opportunity_agent.research.evolution_plan_roles import LLMPlanCritic, LLMRoundReflector
from stock_opportunity_agent.research.evolution_reflection_memory import (
    ReflectionItem, ReflectionMemoryIndex, ReflectionValidationError,
)
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_state_patch import apply_state_patch, state_patch_contract
from tests.scheme_evolution_test_support import make_record, make_trajectory
from tests.test_evolution_reflection_memory import authored, case
from tests.test_evolution_state_patch import PatchCaller, patch


def registered(completed=22):
    index = ReflectionMemoryIndex.from_case_rows([case()], owner_ref="plan:a")
    values = {
        "metrics": {"binary_f1": 0.7333333333333334, "false_negative": 3},
        "magnitude_diagnostics": {"underestimate_count": 6, "missed_surge_count": 2},
        "technical_completion": {"scored_case_count": 24, "research_completed_case_count": completed,
                                 "technical_exclusion_count": 24-completed, "technical_completion_rate": completed/24},
        "evaluation": {"metrics_by_cohort": {"anchor": {"binary_f1": 0.761904761904762}}},
    }
    index.register_plan_statistics(values, plan_ref="plan:a", plan_id="plan_a")
    return index


def statistical_item(index, text, group="metrics"):
    source = next(row for row in index.source_catalog() if row.get("statistics", {}).get("group") == group)
    value = authored(source)
    value.update(category="repeated_failure_modes", kind="fact", brief=text, detail=text)
    value["scope"]["conditions"] = "Per-Plan runtime observation."
    return value


class ReflectionStatisticsTests(TestCase):
    def test_exact_append_values_admit_multiple_refs_without_general_append_authority(self):
        base = {"refs": ["old"], "keep": "unchanged"}
        contract = state_patch_contract(base, mode="correction", obligations=[{
            "issue_code": "statistics", "must_change_paths": ["refs"],
            "allowed_repairs": ["add", "remove"],
            "allowed_append_values": {"refs": ["stat:a", "stat:b"]},
        }])
        operations = [{"op": "remove", "path": "refs[0]"},
                      {"op": "append", "path": "refs", "value": "stat:a"},
                      {"op": "append", "path": "refs", "value": "stat:b"}]
        self.assertEqual(apply_state_patch(base, patch(contract, *operations), contract=contract),
                         {"refs": ["stat:a", "stat:b"], "keep": "unchanged"})
        for extra in ("stat:unrelated",):
            with self.subTest(extra=extra), self.assertRaises(ValidationError):
                apply_state_patch(base, patch(contract, *operations, {"op": "append", "path": "refs", "value": extra}), contract=contract)
        self.assertEqual(apply_state_patch(base, patch(contract, *operations, operations[-2]), contract=contract)["refs"], ["stat:a", "stat:b"])
        self.assertEqual(base["refs"], ["old"])

    def test_old_statistical_item_retains_identity_and_discloses_unchecked_status(self):
        plan_ref = "reflection_plan:" + canonical_json_hash({"B": []})
        initial = ReflectionMemoryIndex.from_case_rows([case()], owner_ref=plan_ref)
        value = authored(initial.source_catalog()[0])
        value.update(category="repeated_failure_modes", brief="binary_f1=0.25.")
        content = {**value, "level": "plan", "owner_ref": plan_ref, "evidence_status": "sources_checked"}
        legacy = ReflectionItem.from_dict({"item_ref": "reflection:" + canonical_json_hash(content), **content})
        row = {"plan": {"B": []}, "original_case_reflections": [case()],
               "vertical_plan_reflection": {"reflection_items": [legacy.to_dict()], "selected_reflection_refs": []}}
        index = ReflectionMemoryIndex.from_plan_rows([row], owner_ref="round")
        self.assertEqual(index.read_refs([legacy.item_ref], role="proposer")["sources"][0]["content"], legacy.to_dict())
        self.assertEqual(index.brief_view()["items"][0]["statistics_status"], "legacy_statistics_unchecked")
        self.assertEqual(index.directory(level="plan")["items"][0]["statistics_status"], "legacy_statistics_unchecked")
        with self.assertRaises(ReflectionValidationError):
            index.create_items([value], level="plan", owner_ref=plan_ref)

    def test_case_sources_do_not_support_aggregate_evaluation_claims(self):
        index = registered()
        value = authored(next(row for row in index.source_catalog() if row["level"] == "case"))
        value.update(category="repeated_failure_modes", brief="binary_f1=0.7333 on this Plan.")
        with self.assertRaises(ReflectionValidationError) as caught:
            index.create_items([value], level="plan", owner_ref="plan:a")
        self.assertEqual(caught.exception.path, "reflection_items[0].brief")
        self.assertIn("reflection_items[0].source_refs", caught.exception.dependency_paths)
        self.assertIn("reflection_items[0].scope.case_refs", caught.exception.dependency_paths)

    def test_metrics_accept_rounding_and_reject_different_population_counts(self):
        index = registered()
        good = statistical_item(index, "binary_f1=0.7333; false_negative=3.")
        self.assertTrue(index.create_items([good], level="plan", owner_ref="plan:a"))
        for text in ("binary_f1=0.80.", "binary_f1=1.", "false_negative=2."):
            with self.subTest(text=text), self.assertRaises(ReflectionValidationError):
                index.create_items([statistical_item(index, text)], level="plan", owner_ref="plan:a")
        good = statistical_item(index, "missed_surge_count=2 in completed research.", "magnitude_diagnostics")
        self.assertTrue(index.create_items([good], level="plan", owner_ref="plan:a"))
        good["brief"] = "missed_surge_count=3 in completed research."
        with self.assertRaises(ReflectionValidationError):
            index.create_items([good], level="plan", owner_ref="plan:a")

    def test_distribution_count_cannot_borrow_a_confusion_matrix_cell(self):
        index = registered()
        index.register_plan_statistics({"magnitude_diagnostics": {
            "prediction_distribution": {"predicted_2-3x": 16},
            "confusion_matrix": {"2-3x": {"predicted_2-3x": 7}},
        }}, plan_ref="plan:a", plan_id="plan_a")
        source = next(row for row in reversed(index.source_catalog()) if row.get("statistics", {}).get("group") == "magnitude_diagnostics")
        value = authored(source)
        value.update(category="repeated_failure_modes", brief="predicted_2-3x=7.")
        with self.assertRaises(ReflectionValidationError):
            index.create_items([value], level="plan", owner_ref="plan:a")

    def test_cohort_ownership_does_not_borrow_another_cohort_value(self):
        index = registered()
        value = statistical_item(index, "anchor cohort binary_f1=0.7619.", "metrics_anchor")
        self.assertTrue(index.create_items([value], level="plan", owner_ref="plan:a"))
        value["brief"] = "combined cohort binary_f1=0.7619."
        with self.assertRaises(ReflectionValidationError):
            index.create_items([value], level="plan", owner_ref="plan:a")

    def test_completion_requires_its_runtime_source_and_honors_negation(self):
        for completed in (22, 24):
            index = registered(completed)
            value = statistical_item(index, "The Plan achieved full technical completion.", "technical_completion")
            if completed == 24:
                self.assertTrue(index.create_items([value], level="plan", owner_ref="plan:a"))
            else:
                with self.assertRaises(ReflectionValidationError):
                    index.create_items([value], level="plan", owner_ref="plan:a")
                value.update(brief="The Plan did not achieve full technical completion.", detail="research_completed_case_count=22; scored_case_count=24.")
                self.assertTrue(index.create_items([value], level="plan", owner_ref="plan:a"))

    def test_round_pooling_and_multi_plan_claims_are_not_single_plan_facts(self):
        index = registered()
        for text in ("The combined magnitude_diagnostics for the round show underestimate_count=6.",
                     "Across both Plans, underestimate_count=6.",
                     "Combined evaluation of the two child Plans: underestimate_count=6."):
            value = statistical_item(index, text, "magnitude_diagnostics")
            value["category"] = "useful_signals"
            with self.subTest(text=text), self.assertRaises(ReflectionValidationError):
                index.create_items([value], level="round", owner_ref="round")
        value = statistical_item(index, "plan_a combined cohort binary_f1=0.7333.")
        value["category"] = "useful_signals"
        self.assertTrue(index.create_items([value], level="round", owner_ref="round"))

    def test_each_plan_claim_cannot_borrow_the_other_plans_value(self):
        index = registered()
        index.register_plan_statistics({"metrics": {"binary_f1": 0.6666666666666666}},
                                       plan_ref="plan:b", plan_id="plan_b")
        sources = [row for row in index.source_catalog() if row.get("statistics", {}).get("group") == "metrics"]
        value = authored(sources[0])
        value.update(category="useful_signals", brief="Both Plans have binary_f1=0.7333.")
        value["source_refs"] = [row["source_ref"] for row in sources]
        value["scope"]["plan_refs"] = ["plan:a", "plan:b"]
        with self.assertRaises(ReflectionValidationError):
            index.create_items([value], level="round", owner_ref="round")
        value["brief"] = "plan_a binary_f1=0.7333; plan_b binary_f1=0.6667."
        self.assertTrue(index.create_items([value], level="round", owner_ref="round"))

    def test_runtime_source_does_not_grant_individual_outcome_or_foreign_plan_authority(self):
        index = registered()
        value = statistical_item(index, "binary_f1=0.7333.")
        with self.assertRaises(ReflectionValidationError):
            index.create_items([value], level="plan", owner_ref="plan:b")
        value["category"] = "successful_patterns"
        value["outcome_claims"] = [{"source_ref": value["source_refs"][0], "axis": "binary", "correct": True}]
        with self.assertRaises(ReflectionValidationError):
            index.create_items([value], level="plan", owner_ref="plan:a")

    def test_statistics_prioritized_and_sources_readable_with_bounded_catalog(self):
        index = registered()
        view = index.catalog_view(max_bytes=4000)
        self.assertEqual(view["sources"][0]["source_kind"], "runtime_plan_statistics")
        self.assertLessEqual(len(json.dumps(view, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()), 4000)
        for source in view["sources"]:
            full = index.read_refs([source["source_ref"]], role="round_reflector")
            if source["source_kind"] == "runtime_plan_statistics":
                self.assertEqual(full["sources"][0]["content"], source["statistics"])
                self.assertEqual(source["case_refs"], [])
                self.assertEqual(source["canonical_outcomes"], {})

    def test_production_critic_local_repair_persists_identical_statistic_handles(self):
        trajectory = make_trajectory("statistics", 15.0, True, MagnitudeClass.TWO_TO_THREE)
        record = make_record("plan_stat", 1, (1.0,))
        record = replace(record, trajectories=(trajectory,), metrics=score_predictions((trajectory,)), evaluation=None, fitness=None)
        original = {}
        def first(request):
            payload = request["payload"]
            self.assertIn("runtime_plan_statistics", request["system_prompt"])
            source = next(row for row in payload["source_catalog"] if row["source_kind"] == "canonical_case_facts")
            bad = authored(source)
            bad.update(category="repeated_failure_modes", brief="binary_f1=0.25.", detail="Inspect the source before revising this Plan.")
            good = authored(source)
            good.update(category="next_explorations", brief="Inspect contrary evidence before the next evaluation.")
            original.update(bad=bad, good=good, catalog=payload["source_catalog"])
            return {"reflection_items": [bad, good], "selected_reflection_refs": []}
        def correct(request):
            source = next(row for row in original["catalog"] if row.get("statistics", {}).get("group") == "metrics")
            self.assertTrue(all(not permission["path"].startswith("reflection_items[1]") for permission in request["payload"]["output_patch_contract"]["allowed_operations"]))
            return patch(request["payload"]["output_patch_contract"],
                         {"op": "replace", "path": "reflection_items[0].brief", "value": "binary_f1=1.0 on this Plan's combined cohort."},
                         {"op": "replace", "path": "reflection_items[0].source_refs[0]", "value": source["source_ref"]},
                         {"op": "remove", "path": "reflection_items[0].scope.case_refs[0]"})
        caller = PatchCaller(first, correct)
        result = LLMPlanCritic(caller).critique(plan=record.plan, trajectories=(trajectory,), metrics=record.metrics)
        self.assertEqual(len(caller.calls), 2)
        self.assertEqual(result.reflection_items[1].brief, original["good"]["brief"])
        saved = replace(record, reflection=result)
        row = PlanMetaReflection.from_record(saved)
        entry = RoundMetaEntry(round_id=1, evidence_refs=(record.plan_id,)).append_plan_reflections((row,))
        restored = replace(RoundMetaEntry.from_dict(json.loads(json.dumps(entry.to_dict()))), round_id=-1)
        index = ReflectionMemoryIndex.from_entries([restored.to_model_dict()])
        ref = result.reflection_items[0].source_refs[0]
        self.assertEqual(index.read_refs([ref], role="proposer")["sources"][0]["content"], next(x["statistics"] for x in original["catalog"] if x["source_ref"] == ref))
        self.assertEqual(index.select_items([result.reflection_items[1].item_ref])[0].to_dict(), result.reflection_items[1].to_dict())

    def test_real_round_adapter_can_compare_each_plan_without_pooling(self):
        records = tuple(make_record(name, 1, (1.0,)) for name in ("plan_a", "plan_b"))
        def first(request):
            sources = [row for row in request["payload"]["source_catalog"] if row.get("statistics", {}).get("group") == "metrics"]
            value = authored(sources[0])
            value.update(category="useful_signals", kind="fact", brief="Both Plans have binary_f1=1.0.", detail="Both Plans have binary_f1=1.0 in their own combined cohorts.")
            value["source_refs"] = [x["source_ref"] for x in sources]
            value["scope"]["plan_refs"] = sorted({ref for x in sources for ref in x["plan_refs"]})
            return {"reflection_items": [value], "selected_reflection_refs": []}
        result = LLMRoundReflector(PatchCaller(first)).reflect(round_id=1, records=records, prior="Compare the supplied records.")
        self.assertEqual(len(result.reflection_items), 1)
        self.assertEqual(len(result.reflection_items[0].scope["plan_refs"]), 2)
