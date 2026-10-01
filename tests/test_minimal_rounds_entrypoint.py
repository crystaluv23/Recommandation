"""Acceptance entry point must freeze an executable production contract."""
from dataclasses import replace
from unittest import TestCase

from scripts.run_minimal_rounds import _evaluation
from tests.evolution_runtime_test_support import make_contract


class MinimalCycleContractTests(TestCase):
    def test_diagnostic_evaluation_obeys_production_v8_floor(self):
        template = make_contract()
        contract = replace(template, limits={**template.limits, 'evaluation': _evaluation().to_dict()})
        self.assertTrue(contract.executable)
        self.assertEqual(_evaluation().cases_per_round, 24)
        self.assertEqual(_evaluation().anchor_cases, 16)
        self.assertEqual(_evaluation().random_cases, 8)
        self.assertTrue(_evaluation().require_finalized)
        self.assertTrue(_evaluation().require_source_evidence)
