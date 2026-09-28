"""Offline tests for sourced reflection identity, scope and bounded disclosure."""

import json
import unittest
from copy import deepcopy

from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_core import (
    PlanReflection,
    PredictionSelfReflection,
    RoundMetaEntry,
)
from stock_opportunity_agent.research.evolution_reflection_memory import (
    ReflectionItem,
    ReflectionMemoryIndex,
    ReflectionValidationError,
)


def byte_size(value):
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())


def case(identity="case:a", *, correct=False, technical=False):
    return {
        "source_identity": identity,
        "candidate_judgment_feedback": {"binary_correct": correct},
        "magnitude_feedback": {"magnitude_applicable": True, "magnitude_correct": False},
        **({"technical_exclusion": {"research_attribution_allowed": False}} if technical else {}),
    }


def authored(source, *, category="plan_issues", level="case"):
    return {
        "category": category, "kind": "action",
        "brief": "Check the existing counterexample before repeating this rule.",
        "detail": "Read the saved counterexample and compare evidence coverage before changing the rule.",
        "scope": {"case_refs": source["case_refs"], "plan_refs": source["plan_refs"], "conditions": "When the same evidence gap recurs."},
        "limitations": ["This is an untested attribution, not a demonstrated improvement."],
        "source_refs": [source["source_ref"]], "counter_refs": [], "outcome_claims": [],
    }


class SourcedReflectionMemoryTests(unittest.TestCase):
    def test_case_reference_survives_generation_archival_and_import(self):
        snapshot = case()
        initial = ReflectionMemoryIndex.from_case_rows([snapshot], owner_ref="case:a")
        source = initial.source_catalog()[0]
        item = initial.create_items([authored(source)], level="case", owner_ref="case:a")[0]
        reflection = PredictionSelfReflection(
            False, reflection_items=(item,), source_identity="case:a", source_snapshot=snapshot
        )
        saved = PredictionSelfReflection.from_dict(reflection.to_dict())
        row = {**snapshot, "case_index": 1, "self_reflection": saved.to_dict()}
        entry = {"round_id": 4, "plan_reflections": [{"plan_id": "plan_1", "plan": {"B": []}, "original_case_reflections": [row], "vertical_plan_reflection": {}}]}
        index = ReflectionMemoryIndex.from_entries([entry])
        disclosed = index.read_refs([source["source_ref"]], role="proposer")
        self.assertEqual(disclosed["sources"][0]["content"], snapshot)
        self.assertEqual(index.select_items([item.item_ref]), (item,))
        rebased = deepcopy(entry)
        rebased["round_id"] = -8
        self.assertEqual(index.source_catalog(), ReflectionMemoryIndex.from_entries([rebased]).source_catalog())

    def test_same_outcome_different_cases_never_share_fact_source(self):
        index = ReflectionMemoryIndex.from_case_rows([case("case:a"), case("case:b")], owner_ref="plan")
        refs = [x["source_ref"] for x in index.source_catalog()]
        self.assertEqual(len(refs), 2)
        self.assertEqual(len(set(refs)), 2)

    def test_false_success_and_technical_research_claim_fail(self):
        for technical in (False, True):
            with self.subTest(technical=technical):
                index = ReflectionMemoryIndex.from_case_rows([case(technical=technical)], owner_ref="plan")
                source = index.source_catalog()[0]
                value = authored(source, category="successful_patterns", level="plan")
                value["outcome_claims"] = [{"source_ref": source["source_ref"], "axis": "binary", "correct": True}]
                with self.assertRaises(ReflectionValidationError) as caught:
                    index.create_items([value], level="plan", owner_ref="plan")
                self.assertEqual(caught.exception.path, "reflection_items[0].outcome_claims[0]")
                self.assertIn("reflection_items[0].category", caught.exception.dependency_paths)

    def test_invalid_counter_reference_never_grants_supporting_source_scope(self):
        index = ReflectionMemoryIndex.from_case_rows([case()], owner_ref="case:a")
        value = authored(index.source_catalog()[0])
        value["counter_refs"] = ["reflection_source:unknown"]
        original_sources = list(value["source_refs"])
        with self.assertRaises(ReflectionValidationError) as caught:
            index.create_items([value], level="case", owner_ref="case:a")
        self.assertEqual(caught.exception.path, "reflection_items[0].counter_refs")
        self.assertEqual(caught.exception.dependency_paths, ())
        value["counter_refs"] = []
        accepted = index.create_items([value], level="case", owner_ref="case:a")[0]
        self.assertEqual(accepted.source_refs, tuple(original_sources))

    def test_malformed_authored_fields_raise_typed_errors_before_hash_or_resolve(self):
        index = ReflectionMemoryIndex.from_case_rows([case()], owner_ref="case:a")
        source = index.source_catalog()[0]
        for field, malformed in (("kind", []), ("category", {}), ("source_refs", None),
                                 ("counter_refs", 1), ("brief", None)):
            with self.subTest(field=field):
                value = authored(source)
                value[field] = malformed
                with self.assertRaises(ReflectionValidationError) as caught:
                    index.create_items([value], level="case", owner_ref="case:a")
                self.assertEqual(caught.exception.path, f"reflection_items[0].{field}")
                self.assertEqual(caught.exception.dependency_paths, ())
                if isinstance(malformed, (list, dict)):
                    self.assertEqual(caught.exception.invalid_container_paths, (f"reflection_items[0].{field}",))
        value = authored(source)
        value["outcome_claims"] = [{"source_ref": source["source_ref"], "axis": [], "correct": False}]
        with self.assertRaises(ReflectionValidationError) as caught:
            index.create_items([value], level="case", owner_ref="case:a")
        self.assertEqual(caught.exception.path, "reflection_items[0].outcome_claims[0].axis")

    def test_source_and_scope_conflicts_declare_real_outcome_dependencies(self):
        index = ReflectionMemoryIndex.from_case_rows([case()], owner_ref="case:a")
        source = index.source_catalog()[0]
        value = authored(source)
        value["source_refs"] = ["reflection_source:unknown"]
        with self.assertRaises(ReflectionValidationError) as caught:
            index.create_items([value], level="case", owner_ref="case:a")
        self.assertEqual(caught.exception.path, "reflection_items[0].source_refs")
        self.assertEqual(caught.exception.dependency_paths, ("reflection_items[0].scope", "reflection_items[0].outcome_claims"))
        value = authored(source)
        value["scope"]["case_refs"] = ["case:unknown"]
        with self.assertRaises(ReflectionValidationError) as caught:
            index.create_items([value], level="case", owner_ref="case:a")
        self.assertEqual(caught.exception.path, "reflection_items[0].scope.case_refs")
        self.assertIn("reflection_items[0].source_refs", caught.exception.dependency_paths)

    def test_production_reflection_repairs_only_the_malformed_authored_field(self):
        from stock_opportunity_agent.research.evolution_core import MagnitudeClass
        from stock_opportunity_agent.research.evolution_plan_roles import LLMBlindPredictor
        from tests.scheme_evolution_test_support import make_trajectory
        from tests.test_evolution_state_patch import PatchCaller, patch

        trajectory = make_trajectory("malformed_reflection", 15.0, True, MagnitudeClass.TWO_TO_THREE)
        for field, malformed in (("kind", []), ("source_refs", None),
                                 ("counter_refs", ["reflection_source:unknown"])):
            with self.subTest(field=field):
                original = {}

                def initial(request):
                    original.update(authored(request["payload"]["source_catalog"][0]))
                    invalid = deepcopy(original)
                    invalid[field] = malformed
                    return {"reflection_items": [invalid], "selected_reflection_refs": []}

                def correct(request):
                    contract = request["payload"]["output_patch_contract"]
                    field_path = f"reflection_items[0].{field}"
                    self.assertTrue(contract["allowed_operations"])
                    self.assertTrue(all(
                        permission["path"] == field_path or permission["path"].startswith(field_path + "[")
                        for permission in contract["allowed_operations"]
                    ))
                    if field == "kind":
                        self.assertTrue(any(
                            permission["op"] == "replace"
                            and permission["path"] == field_path
                            and permission.get("invalid_container") is True
                            for permission in contract["allowed_operations"]
                        ))
                    operation = (
                        {"op": "remove", "path": field_path + "[0]"}
                        if field == "counter_refs" else
                        {"op": "replace", "path": field_path, "value": original[field]}
                    )
                    return patch(contract, operation)

                caller = PatchCaller(initial, correct)
                result = LLMBlindPredictor(caller).reflect(
                    {"summary": "Direction evidence is available."},
                    trajectory.prediction, trajectory.ground_truth,
                )
                self.assertEqual(len(caller.calls), 2)
                self.assertEqual(result.usage.llm_calls, 2)
                accepted = result.value.reflection_items[0].to_dict()
                self.assertEqual({name: accepted[name] for name in original}, original)

    def test_outcome_scope_and_level_are_enforced(self):
        index = ReflectionMemoryIndex.from_case_rows([case("case:a"), case("case:b")], owner_ref="plan")
        a, b = index.source_catalog()
        value = authored(a, category="failed_patterns")
        value["source_refs"].append(b["source_ref"])
        value["scope"]["case_refs"] += b["case_refs"]
        value["outcome_claims"] = [{"source_ref": a["source_ref"], "axis": "binary", "correct": False}]
        with self.assertRaisesRegex(ValidationError, "cover"):
            index.create_items([value], level="plan", owner_ref="plan")
        value["outcome_claims"].append({"source_ref": b["source_ref"], "axis": "binary", "correct": False})
        item = index.create_items([value], level="plan", owner_ref="plan")[0]
        self.assertEqual(item.evidence_status, "sources_checked")
        higher = authored(index.source_catalog()[-1], category="next_explorations")
        with self.assertRaisesRegex(ValidationError, "lower-level"):
            index.create_items([higher], level="plan", owner_ref="another_plan")

    def test_legacy_is_verbatim_unreviewed_and_old_serialization_unchanged(self):
        old = PredictionSelfReflection(False, plan_issues=("An unsupported original interpretation.",)).to_dict()
        self.assertNotIn("reflection_items", old)
        self.assertEqual(PredictionSelfReflection.from_dict(old).to_dict(), old)
        plan = PlanReflection(failed_patterns=("Historical attribution.",)).to_dict()
        self.assertEqual(PlanReflection.from_dict(plan).to_dict(), plan)
        round_value = RoundMetaEntry(1, evidence_refs=("plan",)).to_dict()
        self.assertEqual(RoundMetaEntry.from_dict(round_value).to_dict(), round_value)
        index = ReflectionMemoryIndex.from_case_rows([{**case(), "self_reflection": old}], owner_ref="case:a")
        item = index.brief_view()["items"][0]
        self.assertEqual(item["brief"], old["plan_issues"][0])
        self.assertEqual(item["evidence_status"], "legacy_unreviewed")

    def test_complete_reads_fail_closed_for_role_path_and_budget(self):
        index = ReflectionMemoryIndex.from_case_rows([case()], owner_ref="case:a")
        ref = index.source_catalog()[0]["source_ref"]
        result = index.read_refs([ref], role="proposer")
        self.assertEqual(result["byte_count"], byte_size(result))
        for role, refs, budget in [("blind_predictor", [ref], 16000), ("proposer", ["/tmp/anything"], 16000), ("proposer", [ref], 20)]:
            with self.subTest(role=role, refs=refs, budget=budget), self.assertRaises(ValidationError):
                index.read_refs(refs, role=role, max_bytes=budget)
        with self.assertRaisesRegex(ValidationError, "forbidden"):
            ReflectionMemoryIndex.from_case_rows([{**case(), "final_context": {"x": 1}}], owner_ref="case:a")

    def test_brief_and_paginated_directory_stay_bounded_and_discoverable(self):
        rows = [{**case(f"case:{i}"), "self_reflection": {"plan_issues": [f"Original action {i}. " + "细节" * 40]}} for i in range(30)]
        index = ReflectionMemoryIndex.from_case_rows(rows, owner_ref="plan")
        view = index.brief_view(max_bytes=3000, max_items=2)
        self.assertLessEqual(byte_size(view), 3000)
        self.assertLessEqual(len(view["items"]), 2)
        cursor = view["directory"]["cursor"]
        seen = set()
        while cursor is not None:
            page = index.directory(cursor=cursor, max_bytes=3000)
            self.assertLessEqual(byte_size(page), 3000)
            seen.update(x["item_ref"] for x in page["items"])
            self.assertNotEqual(page["next_cursor"], cursor)
            cursor = page["next_cursor"]
        self.assertEqual(len(seen), 30)

    def test_hash_and_source_identity_tampering_fail(self):
        index = ReflectionMemoryIndex.from_case_rows([case()], owner_ref="case:a")
        item = index.create_items([authored(index.source_catalog()[0])], level="case", owner_ref="case:a")[0]
        changed = item.to_dict()
        changed["brief"] = "Different meaning."
        with self.assertRaisesRegex(ValidationError, "hash"):
            ReflectionItem.from_dict(changed)
        with self.assertRaisesRegex(ValidationError, "identity"):
            PredictionSelfReflection(False, source_identity="case:b", source_snapshot=case())

    def test_catalog_has_bounded_counts_and_exact_read_costs(self):
        rows = [{**case(f"case:{i}"), "self_reflection": {"plan_issues": ["Saved original " + "x" * 6000]}} for i in range(20)]
        index = ReflectionMemoryIndex.from_case_rows(rows, owner_ref="plan")
        view = index.catalog_view(max_bytes=3000)
        self.assertLessEqual(byte_size(view), 3000)
        self.assertGreater(view["counts"]["deferred"], 0)
        for source in view["sources"]:
            self.assertEqual(source["source_kind"], "canonical_case_facts")
            self.assertEqual(source["read_bytes"], index.read_refs([source["source_ref"]], role="proposer")["byte_count"])
        page = index.directory(level="case", max_bytes=3000)
        self.assertEqual(page["level"], "case")
        self.assertTrue(page["oversized_refs"])
        self.assertNotEqual(page["next_cursor"], 0)
        with self.assertRaises(ReflectionValidationError) as caught:
            index.create_items({}, level="case", owner_ref="case:empty")
        self.assertEqual(caught.exception.path, "reflection_items")


class IdentityEgressMaskingTests(unittest.TestCase):
    """Identity masking must project views, never the indexed graph.

    item_ref and source_ref are content hashes over the authoritative
    unmasked rows. Masking entries before index construction both breaks
    hash verification and rewrites source refs so persisted items stop
    resolving. The production pattern is: build from unmasked entries,
    mask only the model-facing views (V142 live mining failure).
    """

    GUARDS = ("Acme Aerospace Systems", "ACME")

    def _index_with_identity_bearing_item(self):
        snapshot = case("case:acme")
        index = ReflectionMemoryIndex.from_case_rows([snapshot], owner_ref="case:acme")
        source = index.source_catalog()[0]
        raw = authored(source)
        raw["detail"] = (
            "Acme Aerospace Systems disclosed a diluted launch calendar; "
            "treat the acceleration claim as unverified."
        )
        item = index.create_items([raw], level="case", owner_ref="case:acme")[0]
        entry = {
            "round_id": 3,
            "plan_reflections": [{
                "plan_id": "plan_1", "plan": {"B": []},
                "original_case_reflections": [{
                    **snapshot, "case_index": 1,
                    "self_reflection": {
                        "reflection_items": [item.to_dict()],
                        "selected_reflection_refs": [],
                        "no_findings_reason": None,
                    },
                }],
                "vertical_plan_reflection": {},
            }],
        }
        return entry, item

    def test_masked_input_construction_is_rejected_not_silently_accepted(self):
        from stock_opportunity_agent.research.evolution_core import _mask_identity_values

        entry, _ = self._index_with_identity_bearing_item()
        masked = _mask_identity_values(deepcopy(entry), self.GUARDS)
        with self.assertRaisesRegex(ValidationError, "hash"):
            ReflectionMemoryIndex.from_entries([masked])

    def test_unmasked_index_and_masked_views_keep_refs_resolvable(self):
        from stock_opportunity_agent.research.evolution_core import _mask_identity_values

        entry, item = self._index_with_identity_bearing_item()
        index = ReflectionMemoryIndex.from_entries([entry])
        self.assertEqual(index.select_items([item.item_ref]), (item,))

        view = _mask_identity_values(index.brief_view(), self.GUARDS)
        catalog = _mask_identity_values(index.catalog_view(), self.GUARDS)
        for payload in (view, catalog):
            self.assertNotIn("Acme Aerospace Systems", json.dumps(payload))
        # Refs survive masking, so on-demand reads and higher-layer selections
        # still resolve against the authoritative index.
        refs = {item.item_ref, *item.source_refs}
        for row in catalog["sources"]:
            refs.add(row["source_ref"])
        disclosed = _mask_identity_values(
            index.read_refs(sorted(refs)[:2], role="proposer", max_bytes=48_000),
            self.GUARDS,
        )
        self.assertNotIn("Acme Aerospace Systems", json.dumps(disclosed))
        self.assertTrue(disclosed["sources"])


if __name__ == "__main__":
    unittest.main()
