"""Source-set normalization at initial and scoped Plan proposal boundaries."""

from copy import deepcopy
from unittest import TestCase

from tests.evolution_runtime_test_support import ScriptedRoleCaller
from stock_opportunity_agent.research.evolution_core import default_information_plan, CandidateProposalRejected
from stock_opportunity_agent.research.evolution_plan_roles import LLMInformationPlanProposer
from stock_opportunity_agent.research.repair import mechanical_repair_candidate


class PlanSourceSetRepairTests(TestCase):
    def output(self):
        parent = default_information_plan()
        return {"used_experience_refs": [], "B": parent.basic_info_policy.to_dict(), "H_init": parent.initial_research_skill,
                "H_reflect": parent.reflection_skill, "H_analyse": parent.analysis_prompt}

    def propose(self, outputs):
        caller = ScriptedRoleCaller(outputs)
        plan = LLMInformationPlanProposer(caller).propose(round_id=1, candidate_index=1,
            candidate_count=1, proposal_attempt=1, forbidden_plan_ids=(), parents=(), meta_info=(), prior="Fixed prior.")
        return plan, caller

    def test_initial_duplicates_preserve_membership_and_original(self):
        output = self.output()
        output["B"]["requests"][1]["source_types"] = ["filing", "filing_body", "filing", "sec_filing"]
        original = deepcopy(output)
        plan, caller = self.propose([output])
        self.assertEqual(plan.basic_info_policy.requests[1].source_types, ("filing", "filing_body", "sec_filing"))
        self.assertEqual(output, original)
        self.assertEqual(len(caller.calls), 1)
        self.assertEqual(plan.initial_research_skill, output["H_init"])

    def test_duplicates_introduced_by_scoped_correction_are_repaired(self):
        invalid = self.output()
        invalid["B"]["requests"][1]["source_types"] = ["filing", "10-k", "20-f", "10-q"]
        corrected = deepcopy(invalid)
        corrected["B"]["requests"][1]["source_types"] = ["filing", "filing_body", "sec_filing", "filing"]
        plan, caller = self.propose([invalid, corrected])
        self.assertEqual(len(caller.calls), 2)
        self.assertEqual(plan.basic_info_policy.requests[1].source_types, ("filing", "filing_body", "sec_filing"))
        self.assertEqual(plan.basic_info_policy.requests[0].to_dict(), invalid["B"]["requests"][0])
        self.assertEqual(plan.reflection_skill, invalid["H_reflect"])

    def test_unknown_values_and_unrelated_content_are_not_repaired(self):
        output = self.output()
        output["B"]["requests"][1]["source_types"] = ["filing", "10-k", "10-k", "FILING"]
        repaired, operations = mechanical_repair_candidate(output)
        self.assertEqual(repaired["B"]["requests"][1]["source_types"], ["filing", "10-k", "FILING"])
        self.assertEqual(len(operations), 1)
        with self.assertRaises(CandidateProposalRejected):
            self.propose([repaired, repaired])
        malformed = deepcopy(output)
        malformed["B"]["requests"][1]["source_types"] = ["filing", "filing", None]
        self.assertEqual(mechanical_repair_candidate(malformed), (malformed, []))
        unrelated = {"source_types": ["filing", "filing"], "observations": ["same", "same"]}
        self.assertEqual(mechanical_repair_candidate(unrelated), (unrelated, []))
