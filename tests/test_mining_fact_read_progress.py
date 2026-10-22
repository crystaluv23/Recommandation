"""Whole already-read fact receipts reach subsequent native model decisions."""
from copy import deepcopy
from dataclasses import replace
from unittest import TestCase

from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.research.mining_controller import InvalidMiningAction
from stock_opportunity_agent.research.mining_role_model import MiningAgentRoleModel
from stock_opportunity_agent.research.stage_contracts import json_bytes
from tests.evolution_runtime_test_support import ScriptedRoleCaller
from tests.test_mining_controller import _controller, _fixture_store


class MiningFactReadProgressTests(TestCase):
    def controller(self):
        cases, store = _fixture_store()
        controller = _controller(store, cases, object(), seed="discovery", heavy_action_limit=30)
        controller._execute_fetch({"action": "fetch_evidence", "rationale": ["Inspect source."],
            "case_refs": ["case-001", "case-002"], "source_families": ["company_facts"], "max_documents": 1})
        return controller

    def read(self, controller, fact_ref):
        controller._read_fact_span({"action": "read_span", "rationale": ["Read exact binding."], "fact_ref": fact_ref})

    def test_two_native_reads_survive_compare_and_reach_actual_role_adapter(self):
        controller = self.controller()
        facts = list(controller._facts.values())[:2]
        self.read(controller, facts[0].fact_ref)
        first = deepcopy(controller._last_action_result)
        self.read(controller, facts[1].fact_ref)
        second = deepcopy(controller._last_action_result)
        controller._execute_compare({"action": "compare_groups", "rationale": ["Compare."], "concepts": [facts[0].concept]})
        caller = ScriptedRoleCaller([{"action": "record_deferred", "rationale": ["End this fixture."]}])
        MiningAgentRoleModel(caller).next_action(controller._model_view())
        page = caller.calls[0]["payload"]["structured_read_progress"]
        self.assertTrue(page["selection_is_exhaustive"])
        self.assertEqual(page["counts"]["available"], 2)
        self.assertEqual(page["items"], [
            {**{k: v for k, v in row.items() if k != "action"}, "read_count": 1}
            for row in (second, first)
        ])
        self.assertEqual(caller.calls[0]["payload"]["last_action_result"]["action"], "compare_groups")
        self.assertIn("structured_read_progress", caller.calls[0]["system_prompt"])
        self.assertEqual(controller.ledger.entries[1].output_hash,
            canonical_json_hash({k: v for k, v in first.items() if k != "action"}))

    def test_only_read_facts_are_disclosed_and_view_mutation_cannot_rewrite_history(self):
        controller = self.controller()
        self.assertNotIn("structured_read_progress", controller._model_view())
        fact = next(iter(controller._facts.values()))
        self.read(controller, fact.fact_ref)
        page = controller._model_view()["structured_read_progress"]
        self.assertEqual(len(page["items"]), 1)
        page["items"][0]["fact"]["taxonomy"] = "invented"
        self.assertEqual(controller._model_view()["structured_read_progress"]["items"][0]["fact"]["taxonomy"], "us-gaap")

    def test_repeat_reads_reorder_and_count_without_extra_units_or_free_budget(self):
        controller = self.controller()
        refs = list(controller._facts)[:2]
        for ref in (*refs, refs[0]):
            self.read(controller, ref)
        page = controller._model_view()["structured_read_progress"]
        self.assertEqual([r["fact_ref"] for r in page["items"]], refs)
        self.assertEqual([r["read_count"] for r in page["items"]], [2, 1])
        self.assertEqual(controller._heavy_used, 4)
        self.assertEqual(sum(e.action == "read_span" for e in controller.ledger.entries), 3)

    def test_changed_receipt_same_ref_rejects_without_reusing_read_proof(self):
        controller = self.controller()
        fact = next(iter(controller._facts.values()))
        self.read(controller, fact.fact_ref)
        before = deepcopy(controller._fact_read_progress)
        ledger, heavy = controller.ledger.entries, controller._heavy_used
        controller._facts[fact.fact_ref] = replace(fact, taxonomy="other")
        with self.assertRaisesRegex(InvalidMiningAction, "same fact_ref"):
            self.read(controller, fact.fact_ref)
        self.assertEqual(controller._fact_read_progress, before)
        self.assertEqual(controller.ledger.entries, ledger)
        self.assertEqual(controller._heavy_used, heavy)

    def test_oversized_receipt_is_explicit_and_does_not_hide_smaller_unit(self):
        controller = self.controller()
        facts = list(controller._facts.values())[:2]
        self.read(controller, facts[0].fact_ref)
        huge = replace(facts[1], exact_span="长" * 3000)
        controller._facts[huge.fact_ref] = huge
        self.read(controller, huge.fact_ref)
        page = controller._model_view()["structured_read_progress"]
        self.assertLessEqual(json_bytes(page["items"]), 8000)
        self.assertEqual([r["fact_ref"] for r in page["items"]], [facts[0].fact_ref])
        self.assertFalse(page["selection_is_exhaustive"])
        self.assertEqual(page["counts"]["oversized"], 1)
        self.assertEqual(page["oversized_entries"][0]["fact_ref"], huge.fact_ref)
        self.assertGreater(page["oversized_entries"][0]["required_bytes"], 8000)
        self.assertEqual(controller._last_action_result["masked"], huge.exact_span)

    def test_deterministic_action_reconstruction_preserves_receipts_and_counts(self):
        def replay():
            controller = self.controller()
            refs = list(controller._facts)[:2]
            for ref in (*refs, refs[0]):
                self.read(controller, ref)
            return controller
        original, restored = replay(), replay()
        self.assertEqual(original._model_view(), restored._model_view())
        self.assertEqual(original.ledger.to_dict(), restored.ledger.to_dict())
