"""Replay frozen failed terminal responses; this does not prove model compliance."""

import json
from pathlib import Path
from unittest import TestCase

from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_core import ResearchState, RuntimeStopReason, default_information_plan
from stock_opportunity_agent.research.evolution_plan_roles import LLMResearchController
from stock_opportunity_agent.research.evolution_state_patch import apply_state_patch
from stock_opportunity_agent.signal_library import SignalBatchResult, SignalResult
from tests.test_evolution_state_patch import PatchCaller, patch


class TerminalDispositionReplayTests(TestCase):
    def test_both_real_terminal_responses_have_executable_remove_only_correction(self):
        fixture = json.loads((Path(__file__).parent / "fixtures/evolution_runtime/answer_scope_terminal_20261019.json").read_text())
        self.assertEqual(len(fixture["cases"]), 2)
        for case in fixture["cases"]:
            with self.subTest(sample=case["sample_id"]):
                prior = ResearchState.from_dict(case["prior_envelope"])
                batch = SignalBatchResult(results=tuple(SignalResult.from_dict(row) for row in case["batch"]["results"]),
                    signal_calls=case["batch"]["signal_calls"])
                self.assertEqual(case["executed_selection_intents"], [])
                first_rows = [operation["value"] for operation in case["first_response"]["operations"]
                              if operation["path"] == "need_dispositions"]
                self.assertEqual(first_rows, case["correction_base"]["need_dispositions"])

                def repair(call):
                    payload = call["payload"]
                    self.assertEqual(payload["need_transition_contract"]["required_disposition_need_indices"], [])
                    self.assertIn("If that list is empty, keep need_dispositions=[]", call["system_prompt"])
                    feedback = payload["validation_feedback"]
                    issues = feedback["obligations"]
                    self.assertEqual(len(issues), len(first_rows))
                    self.assertTrue(all(issue["issue_code"] == "research_need_disposition_invalid" for issue in issues))
                    self.assertTrue(all(issue["required_disposition_need_indices"] == [] for issue in issues))
                    self.assertTrue(all(issue["allowed_repairs"] == ["remove"] for issue in issues))
                    contract = payload["output_patch_contract"]
                    self.assertEqual(contract["allowed_operations"], [
                        {"op": "remove", "path": f"need_dispositions[{index}]", "descendants": False}
                        for index in range(len(first_rows))])
                    # The old response replaced/reindexed rows; even with the
                    # current base hash that action has no authority now.
                    old_correction = {**case["old_correction"], "base_hash": contract["base_hash"]}
                    with self.assertRaisesRegex(ValidationError, "outside typed authority"):
                        apply_state_patch(feedback["invalid_output"], old_correction, contract=contract)
                    return patch(contract, *[
                        {"op": "remove", "path": f"need_dispositions[{index}]"}
                        for index in range(len(first_rows))])

                # The saved wire envelope is anonymous; its original issued
                # hash bound the unmasked runtime snapshot. Rebind only that
                # hash for this explicit offline replay, keeping every saved
                # operation and authored value unchanged.
                caller = PatchCaller(lambda call: {**case["first_response"],
                    "base_hash": call["payload"]["output_patch_contract"]["base_hash"]}, repair)
                caller.max_structured_corrections = 1
                controller = LLMResearchController(caller)
                controller.set_reflection_runtime_context(selections=(), must_finalize=True,
                    termination_trigger=RuntimeStopReason.BUDGET_EXHAUSTED)
                result = controller.reflect(default_information_plan(), prior, batch)
                self.assertEqual(len(caller.calls), 2)
                self.assertEqual(result.value.decision.value, "finalize")
                self.assertEqual(result.value.next_information_needs, prior.next_information_needs)
                self.assertEqual(result.metadata["need_dispositions"]["items"], [])
                # Removing audit rows cannot author an answer or change any
                # ResearchState field from the already validated frontier.
                expected = ResearchState.from_dict(caller.calls[1]["payload"]["validation_feedback"]["invalid_output"])
                self.assertEqual(result.value, expected)
