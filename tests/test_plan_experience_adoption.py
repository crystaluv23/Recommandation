"""New proposal adoption is explicit while persisted legacy Plans stay readable."""

from copy import deepcopy
from unittest import TestCase

from stock_opportunity_agent.research.evolution_core import (
    CandidateProposalRejected, InformationPlan, default_information_plan,
)
from stock_opportunity_agent.research.evolution_plan_roles import LLMInformationPlanProposer
from tests.test_evolution_state_patch import PatchCaller, patch


class PlanExperienceAdoptionTests(TestCase):
    def output(self):
        """Return a valid strategy with deliberately missing adoption metadata."""
        parent = default_information_plan()
        return {
            "B": parent.basic_info_policy.to_dict(),
            "H_init": parent.initial_research_skill,
            "H_reflect": parent.reflection_skill + " Inspect cash conversion counterevidence.",
            "H_analyse": parent.analysis_prompt,
        }

    def propose(self, caller):
        """Exercise the production proposer and its actual typed patch boundary."""
        return LLMInformationPlanProposer(caller).propose(
            round_id=1, candidate_index=1, candidate_count=1, proposal_attempt=2,
            forbidden_plan_ids=(), parents=(default_information_plan(),),
            meta_info=(), prior="Fixed research prior.",
        )

    def test_missing_metadata_requires_add_only_patch_and_preserves_strategy(self):
        original = self.output()
        retained = deepcopy(original)
        caller = PatchCaller(original, lambda call: patch(
            call["payload"]["output_patch_contract"],
            {"op": "add", "path": "used_experience_refs", "value": []},
        ))
        plan = self.propose(caller)
        self.assertEqual(len(caller.calls), 2)
        contract = caller.calls[1]["payload"]["output_patch_contract"]
        self.assertEqual(contract["allowed_operations"], [
            {"op": "add", "path": "used_experience_refs", "descendants": False},
        ])
        self.assertEqual(caller.calls[1]["payload"]["validation_feedback"]["invalid_output"], retained)
        self.assertEqual(plan.experience_usage["item_refs"], ())
        self.assertEqual(plan.basic_info_policy.to_dict(), original["B"])
        self.assertEqual(plan.initial_research_skill, original["H_init"])
        self.assertEqual(plan.reflection_skill, original["H_reflect"])
        self.assertEqual(plan.analysis_prompt, original["H_analyse"])
        self.assertEqual(original, retained)
        self.assertEqual(InformationPlan.from_dict(plan.to_dict()), plan)

    def test_explicit_empty_is_known_nonuse_without_extra_call(self):
        caller = PatchCaller({**self.output(), "used_experience_refs": []})
        plan = self.propose(caller)
        self.assertEqual(len(caller.calls), 1)
        self.assertEqual(plan.experience_usage["item_refs"], ())

    def test_adoption_patch_cannot_change_strategy(self):
        caller = PatchCaller(self.output(), lambda call: patch(
            call["payload"]["output_patch_contract"],
            {"op": "add", "path": "used_experience_refs", "value": []},
            {"op": "replace", "path": "H_reflect", "value": "Different strategy"},
        ))
        with self.assertRaises(CandidateProposalRejected):
            self.propose(caller)

    def test_added_metadata_is_fully_revalidated(self):
        for adopted in [None, "reflection:unknown", ["reflection:unknown"], [1]]:
            with self.subTest(adopted=adopted):
                caller = PatchCaller(self.output(), lambda call: patch(
                    call["payload"]["output_patch_contract"],
                    {"op": "add", "path": "used_experience_refs", "value": adopted},
                ))
                with self.assertRaises(CandidateProposalRejected):
                    self.propose(caller)

    def test_persisted_legacy_plan_remains_unknown(self):
        legacy = default_information_plan().to_dict()
        self.assertNotIn("experience_usage", legacy)
        restored = InformationPlan.from_dict(legacy)
        self.assertIsNone(restored.experience_usage)
        self.assertNotIn("experience_usage", restored.to_dict())
