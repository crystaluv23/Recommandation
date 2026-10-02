"""Shared native correction preserves already-correct mining arguments."""

from copy import deepcopy
from unittest import TestCase

from tests.test_mining_controller import _controller, _fixture_store, ScriptedMiningDecisionModel


def fetch_action():
    return {"action": "fetch_evidence", "case_refs": ["case-001"],
            "source_families": ["financial"], "max_documents": 1}


def native_patch(view, *operations):
    contract = view["last_invalid_action"]["output_patch_contract"]
    return {"base_hash": contract["base_hash"], "operations": list(operations)}


STOP = {"action": "record_deferred", "rationale": ["Retain the collected evidence for later work."]}


class MiningActionPatchTests(TestCase):
    def test_invalid_fetch_is_not_completed_exploration(self):
        cases, store = _fixture_store()
        controller = _controller(store, cases, None, seed="discovery")
        controller._record_invalid("fetch_evidence", fetch_action(), "missing rationale")
        self.assertEqual(controller.ledger.fetch_count(), 0)
        self.assertEqual(controller._model_view()["evidence_digest"]["fetches"], 0)
        self.assertEqual(controller.ledger.evidence_refs(), set())

    def run_actions(self, actions):
        cases, store = _fixture_store()
        model = ScriptedMiningDecisionModel(actions)
        controller = _controller(store, cases, model, seed="discovery")
        return controller, model, controller.run()

    def test_missing_reason_is_added_without_replacing_action_or_parameters(self):
        original = fetch_action()
        def correct(view):
            failure = view["last_invalid_action"]
            self.assertEqual(failure["invalid_output"], original)
            self.assertEqual(failure["validation_feedback"]["required_change_paths"], ["rationale"])
            return native_patch(view, {"op": "add", "path": "rationale", "value": ["Read the requested financial evidence."]})
        controller, model, result = self.run_actions([original, correct, STOP])
        self.assertEqual(result.terminal_kind, "evidence_unavailable")
        self.assertEqual(controller._heavy_used, 1)
        self.assertEqual(controller.ledger.fetch_count(), 1)
        self.assertNotIn("rationale", original)
        self.assertEqual(len(model.views), 3)

    def test_unauthorized_patch_retains_original_base_and_next_valid_repair(self):
        hashes = []
        def unauthorized(view):
            hashes.append(view["last_invalid_action"]["output_patch_contract"]["base_hash"])
            return native_patch(view, {"op": "replace", "path": "case_refs[0]", "value": "case-002"})
        def correct(view):
            self.assertIn("patch_error", view["last_invalid_action"])
            self.assertEqual(view["last_invalid_action"]["output_patch_contract"]["base_hash"], hashes[0])
            self.assertEqual(view["budget"]["heavy_remaining"], 12)
            return native_patch(view, {"op": "add", "path": "rationale", "value": ["Fetch the unchanged case."]})
        controller, _, result = self.run_actions([fetch_action(), unauthorized, correct, STOP])
        self.assertEqual(result.terminal_kind, "evidence_unavailable")
        self.assertEqual(controller._heavy_used, 1)

    def test_valid_reason_siblings_are_not_regenerated(self):
        original = {**fetch_action(), "rationale": ["Keep this valid reason.", {"wrong": "shape"}]}
        def correct(view):
            self.assertEqual(view["last_invalid_action"]["validation_feedback"]["required_change_paths"], ["rationale[1]"])
            return native_patch(view, {"op": "replace", "path": "rationale[1]", "value": "Use the selected point-in-time documents."})
        controller, model, result = self.run_actions([deepcopy(original), correct, STOP])
        self.assertEqual(result.terminal_kind, "evidence_unavailable")
        self.assertEqual(controller._heavy_used, 1)
        self.assertEqual(model.views[1]["last_invalid_action"]["invalid_output"], original)

    def test_scalar_reason_is_mechanically_wrapped_and_journaled(self):
        original = {**fetch_action(), "rationale": "Read the financial evidence."}
        controller, model, result = self.run_actions([original, STOP])
        self.assertEqual(result.terminal_kind, "evidence_unavailable")
        self.assertEqual(len(model.views), 2)
        repairs = [row for row in controller.ledger.entries if row.action == "mechanical_repair"]
        self.assertEqual(len(repairs), 1)
        self.assertEqual(repairs[0].coverage["repairs"][0]["before"], original["rationale"])
        self.assertEqual(repairs[0].coverage["repairs"][0]["after"], [original["rationale"]])

    def test_empty_reason_array_only_allows_bounded_append(self):
        def correct(view):
            return native_patch(view, {"op": "append", "path": "rationale", "value": "Read source-backed records."})
        controller, _, result = self.run_actions([{**fetch_action(), "rationale": []}, correct, STOP])
        self.assertEqual(result.terminal_kind, "evidence_unavailable")
        self.assertEqual(controller._heavy_used, 1)

    def test_corrected_reason_does_not_bypass_action_budget_validation(self):
        cases, store = _fixture_store()
        original = {"action": "inspect_catalog", "scope": "signals"}
        model = ScriptedMiningDecisionModel([original,
            lambda view: native_patch(view, {"op": "add", "path": "rationale", "value": ["Read the catalog."]}), STOP])
        controller = _controller(store, cases, model, seed="discovery", light_action_limit=0)
        result = controller.run()
        self.assertEqual(result.terminal_kind, "evidence_unavailable")
        self.assertEqual(controller._light_used, 0)
        self.assertIn("light action budget exhausted", model.views[2]["last_invalid_action"]["issue"])
