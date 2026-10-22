"""Executed comparison locators remain reachable without stale measurement authority."""
from copy import deepcopy
from dataclasses import replace
from unittest import TestCase
from unittest.mock import patch

from stock_opportunity_agent.research.mining_controller import InvalidMiningAction
from stock_opportunity_agent.research.mining_role_model import MiningAgentRoleModel
from stock_opportunity_agent.research.stage_contracts import json_bytes
from tests.evolution_runtime_test_support import ScriptedRoleCaller
from tests import test_mining_fact_read_progress as read_support


CONCEPT = "CashAndCashEquivalentsAtCarryingValue"


def visible_operand(view, concept, role):
    """Select only from the current disclosed payload, never a saved/private ref."""
    page = view.get("comparison_progress", {})
    if page.get("snapshot_status") == "current":
        for item in page["items"]:
            if item["concept"] == concept:
                return next(row[role][case]["fact_ref"] for row in item["groups"].values()
                    for case in sorted(row[role]))
    last = view.get("last_action_result", {})
    if last.get("action") == "compare_groups" and "groups" in last:
        return next(row["concepts"][concept][role][case]["fact_ref"]
            for row in last["groups"].values() for case in sorted(row["concepts"][concept][role]))
    raise LookupError("No current disclosed concept/operand locator")


class MiningComparisonProgressTests(TestCase):
    def controller(self):
        return read_support.MiningFactReadProgressTests().controller()

    def compare(self, controller, concepts=(CONCEPT,)):
        controller._execute_compare({"action": "compare_groups", "concepts": list(concepts),
            "rationale": ["Compare fetched facts only."]})

    def read(self, controller, ref):
        controller._read_fact_span({"action": "read_span", "fact_ref": ref,
            "rationale": ["Read currently disclosed operand."]})

    def test_next_operand_is_selected_only_from_each_current_native_payload(self):
        for roles in (("latest", "comparable_prior"), ("comparable_prior", "latest")):
            with self.subTest(roles=roles):
                controller = self.controller()
                self.assertNotIn("comparison_progress", controller._model_view())
                self.compare(controller)
                caller = ScriptedRoleCaller([{"action": "record_deferred", "rationale": ["Fixture stop."]}] * 3)
                model = MiningAgentRoleModel(caller)
                for role in roles:
                    model.next_action(controller._model_view())
                    self.read(controller, visible_operand(caller.calls[-1]["payload"], CONCEPT, role))
                model.next_action(controller._model_view())
                payload = caller.calls[-1]["payload"]
                receipts = payload["structured_read_progress"]["items"]
                self.assertEqual(len(receipts), 2)
                self.assertEqual({r["fact"]["value"] for r in receipts}, {"800", "1000"})
                self.assertIn("comparison_progress", caller.calls[-1]["system_prompt"])
                # An opaque ref inventory cannot substitute for the missing mapping.
                without_mapping = deepcopy(payload)
                without_mapping.pop("comparison_progress")
                with self.assertRaises(LookupError):
                    visible_operand(without_mapping, CONCEPT, roles[-1])

    def test_all_concept_groups_and_empty_unresolved_branches_are_preserved(self):
        controller = self.controller()
        first = next(iter(controller._facts.values()))
        controller._facts[first.fact_ref] = replace(first, taxonomy="conflicting-namespace")
        self.compare(controller, ("Missing", CONCEPT, "Missing"))
        page = controller._model_view()["comparison_progress"]
        self.assertEqual([r["concept"] for r in page["items"]], [CONCEPT, "Missing"])
        last = controller._last_action_result["groups"]
        for item in page["items"]:
            self.assertEqual(set(item["groups"]), {"positive", "control"})
            for group, row in item["groups"].items():
                self.assertEqual(row, {"case_count": last[group]["case_count"],
                    **last[group]["concepts"][item["concept"]]})
        self.assertTrue(any(row["unresolved_basis_cases"] for row in page["items"][0]["groups"].values()))
        before = controller._heavy_used
        self.compare(controller, ("Missing",))
        self.assertEqual([r["concept"] for r in controller._model_view()["comparison_progress"]["items"]],
            ["Missing", CONCEPT])
        self.assertEqual(controller._heavy_used, before + 1)
        self.assertNotIn("structured_read_progress", controller._model_view())

    def test_context_changes_hide_every_stale_copy_and_refresh_clears_old_generation(self):
        changes = {
            "value": lambda c, f: c._facts.update({f.fact_ref: replace(f, value="changed")}),
            "taxonomy": lambda c, f: c._facts.update({f.fact_ref: replace(f, taxonomy="other")}),
            "period": lambda c, f: c._facts.update({f.fact_ref: replace(f, period="changed")}),
            "source": lambda c, f: c._facts.update({f.fact_ref: replace(f, content_hash="changed")}),
            "added": lambda c, f: c._facts.update({"new": replace(f, fact_ref="new")}),
            "removed": lambda c, f: c._facts.pop(f.fact_ref),
            "group": lambda c, f: c._label_map.update({f.case_ref: "positive"}),
            "axis": lambda c, f: setattr(c, "research_axis", {"direction": "different-axis"}),
        }
        for name, change in changes.items():
            with self.subTest(name=name):
                controller = self.controller()
                self.compare(controller, (CONCEPT, "OldEmpty"))
                original = deepcopy(controller._last_action_result)
                first = next(iter(controller._facts.values()))
                change(controller, first)
                view = controller._model_view()
                self.assertEqual(view["comparison_progress"]["snapshot_status"], "invalidated")
                self.assertEqual(view["comparison_progress"]["items"], [])
                self.assertEqual(view["comparison_progress"]["invalidated_comparisons"], 2)
                self.assertFalse(view["comparison_progress"]["selection_is_exhaustive"])
                self.assertNotIn("groups", view["last_action_result"])
                self.assertEqual(controller._last_action_result, original)
                with self.assertRaises(LookupError):
                    visible_operand(view, CONCEPT, "comparable_prior")
                self.compare(controller)
                page = controller._model_view()["comparison_progress"]
                self.assertEqual(page["snapshot_status"], "current")
                self.assertEqual([r["concept"] for r in page["items"]], [CONCEPT])

    def test_views_do_not_recompute_or_change_proof_and_nested_mutation_is_isolated(self):
        controller = self.controller()
        self.compare(controller)
        original = deepcopy(controller._model_view())
        last = deepcopy(controller._last_action_result)
        ledger, heavy = controller.ledger.to_dict(), controller._heavy_used
        controller._facts = dict(reversed(list(controller._facts.items())))
        controller._label_map = dict(reversed(list(controller._label_map.items())))
        with patch.object(controller, "_group_summary", side_effect=AssertionError("view recomputed")):
            view = controller._model_view()
        self.assertEqual(view, original)
        view["comparison_progress"]["items"][0]["groups"].clear()
        view["last_action_result"]["groups"].clear()
        self.assertEqual(controller._model_view(), original)
        self.assertEqual(controller._last_action_result, last)
        self.assertEqual(controller.ledger.to_dict(), ledger)
        self.assertEqual(controller._heavy_used, heavy)
        # An actual idempotent fetch and repeated reads leave the fact generation intact.
        controller._execute_fetch({"action": "fetch_evidence", "rationale": ["Same source."],
            "case_refs": ["case-001", "case-002"], "source_families": ["company_facts"], "max_documents": 1})
        self.read(controller, visible_operand(original, CONCEPT, "latest"))
        self.read(controller, visible_operand(original, CONCEPT, "latest"))
        self.assertEqual(controller._model_view()["comparison_progress"], original["comparison_progress"])

    def test_inputs_changed_during_calculation_reject_before_acceptance(self):
        controller = self.controller()
        self.compare(controller, ("OldEmpty",))
        before = deepcopy((controller._last_action_result, controller._comparison_progress,
            controller._comparison_snapshot, controller.ledger.to_dict(), controller._heavy_used))
        native = controller._group_summary
        def changing(concepts):
            result = native(concepts)
            fact = next(iter(controller._facts.values()))
            controller._facts[fact.fact_ref] = replace(fact, taxonomy="changed-during-comparison")
            return result
        with patch.object(controller, "_group_summary", side_effect=changing):
            with self.assertRaisesRegex(InvalidMiningAction, "inputs changed during"):
                self.compare(controller)
        self.assertEqual((controller._last_action_result, controller._comparison_progress,
            controller._comparison_snapshot, controller.ledger.to_dict(), controller._heavy_used), before)
        self.assertEqual(controller._model_view()["comparison_progress"]["snapshot_status"], "invalidated")

    def test_whole_unit_caps_unicode_oversized_and_paid_refresh(self):
        controller = self.controller()
        names = [f"Empty-{i:02}" for i in range(15)]
        self.compare(controller, names)
        page = controller._model_view()["comparison_progress"]
        self.assertEqual(len(page["items"]), 12)
        self.assertEqual(page["counts"]["omitted_after"], 3)
        self.assertFalse(page["selection_is_exhaustive"])
        self.assertLessEqual(json_bytes(page["items"]), 8000)
        self.assertNotIn(names[-1], [r["concept"] for r in page["items"]])
        before = controller._heavy_used
        self.compare(controller, (names[-1],))
        self.assertEqual(controller._heavy_used, before + 1)
        self.assertEqual(controller._model_view()["comparison_progress"]["items"][0]["concept"], names[-1])
        huge = "长" * 3000
        self.compare(controller, (huge,))
        page = controller._model_view()["comparison_progress"]
        self.assertEqual(page["oversized_entries"][0]["concept"], huge)
        self.assertGreater(page["oversized_entries"][0]["required_bytes"], 8000)
        self.assertTrue(page["items"])
        self.assertNotIn(huge, [r["concept"] for r in page["items"]])
        self.assertLessEqual(json_bytes(page["items"]), 8000)

    def test_deterministic_reconstruction_replays_current_view_and_choice(self):
        results = []
        for _ in range(2):
            controller = self.controller()
            self.compare(controller)
            for role in ("latest", "comparable_prior"):
                self.read(controller, visible_operand(controller._model_view(), CONCEPT, role))
            self.compare(controller, ("Other",))
            results.append((controller._model_view(), controller.ledger.to_dict()))
        self.assertEqual(*results)
