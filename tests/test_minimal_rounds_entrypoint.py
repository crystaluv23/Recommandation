"""Acceptance entry point must freeze an executable production contract."""
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from scripts.run_minimal_rounds import _evaluation, prepare
from stock_opportunity_agent.models import ValidationError
from tests.evolution_runtime_test_support import make_contract


class MinimalCycleContractTests(TestCase):
    def test_prepared_registry_seed_cannot_silently_change(self):
        with TemporaryDirectory() as temp:
            root = Path(temp) / 'run'
            root.mkdir()
            (root / 'input_manifest.json').write_text('{}')
            seed = Path(temp) / 'seed'
            frozen = {'registry_source': str(seed)}
            with patch('scripts.run_minimal_rounds._verify_inputs', return_value=frozen):
                self.assertEqual(prepare(root, seed_registry=seed), frozen)
                self.assertEqual(prepare(root), frozen)
                with self.assertRaises(ValidationError):
                    prepare(root, seed_registry=Path(temp) / 'different')

    def test_missing_registry_seed_fails_without_creating_a_source(self):
        with TemporaryDirectory() as temp:
            seed = Path(temp) / 'missing'
            with self.assertRaises(ValidationError):
                prepare(Path(temp) / 'run', seed_registry=seed)
            self.assertFalse(seed.exists())

    def test_partial_registry_is_not_silently_promoted_to_prepared_inputs(self):
        with TemporaryDirectory() as temp:
            seed = Path(temp) / 'seed'
            seed.mkdir()
            (seed / 'registry.json').write_text('{"version":7}')
            root = Path(temp) / 'run'
            (root / 'signals').mkdir(parents=True)
            with self.assertRaises(ValidationError):
                prepare(root, seed_registry=seed)
            self.assertFalse((root / 'input_manifest.json').exists())

    def test_diagnostic_evaluation_obeys_production_v8_floor(self):
        template = make_contract()
        contract = replace(template, limits={**template.limits, 'evaluation': _evaluation().to_dict()})
        self.assertTrue(contract.executable)
        self.assertEqual(_evaluation().cases_per_round, 24)
        self.assertEqual(_evaluation().anchor_cases, 16)
        self.assertEqual(_evaluation().random_cases, 8)
        self.assertTrue(_evaluation().require_finalized)
        self.assertTrue(_evaluation().require_source_evidence)
