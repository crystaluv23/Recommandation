"""Preserve ratio definitions while screening wrong measurement descriptions."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import shutil
import tempfile
from unittest import TestCase

from stock_opportunity_agent.research.signal_evolution import (
    SignalCandidateValidator, signal_description_concept_contracts,
)
from stock_opportunity_agent.signal_library import SignalRegistry


class SignalDescriptionRatioTests(TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        source = Path(__file__).resolve().parents[1] / 'runs/cold_start/minimal_rounds_v182_integrated/signals'
        root = Path(self.directory.name) / 'signals'
        shutil.copytree(source, root)
        self.registry = SignalRegistry(root)
        self.prior = self.registry.load_spec('operating_cash_flow_margin:v2')
        self.candidate = replace(self.prior, version=3)
        self.original = self.registry.load_tests(self.prior.ref)
        self.fixtures = deepcopy(self.original)
        for fixture in self.fixtures:
            for doc in fixture['documents']:
                body = json.loads(doc['content'])
                body['cik'] = '0001999991'
                doc['metadata'] = {**doc.get('metadata', {}), 'cik': '0001999991'}
                doc['content'] = json.dumps(body, sort_keys=True, separators=(',', ':'))
        self.validator = SignalCandidateValidator(self.registry, llm_runner=None)

    def test_original_exact_definition_executes_all_identity_repaired_fixtures(self):
        checked = self.validator.validate(self.candidate, skill=None, tests=self.fixtures)
        self.assertTrue(checked.accepted, checked.reasons)
        self.assertEqual(checked.executed_tests, len(self.fixtures))
        self.assertEqual(self.candidate.description, self.prior.description)
        self.assertEqual(self.registry.load_tests(self.prior.ref), self.original)

    def test_ordered_equivalent_ratio_phrases_execute_without_rewriting_definition(self):
        for description in (
            'Measure operating cash flow as a share of revenue.',
            'Measure OPERATING CASH FLOW as a percentage of revenue.',
            'Measure operating cash-flow divided by revenue.',
            'Measure the operating cash flow to revenue ratio.',
            'Measure operating cash flow margin.',
        ):
            with self.subTest(description=description):
                candidate = replace(self.candidate, description=description)
                checked = self.validator.validate(candidate, skill=None, tests=self.fixtures)
                self.assertTrue(checked.accepted, checked.reasons)
                self.assertEqual(checked.executed_tests, len(self.fixtures))
                self.assertEqual(candidate.description, description)

    def test_wrong_numerator_denominator_and_different_concepts_remain_rejected(self):
        for description in (
            'Measure revenue as a share of operating cash flow.',
            'Measure operating cash flow as a share of cash.',
            'Measure net income as a share of revenue.',
            'Measure operating cash flow divided by current liabilities.',
            'Measure operating cash flow growth and revenue growth.',
            'Measure nonoperating cash flow as a share of revenue.',
            'Measure non-operating cash flow as a share of revenue.',
            'Measure not operating cash flow as a share of revenue.',
            'Measure operating cash flow as a share of revenue growth.',
            'Measure operating cash flow divided by revenue growth.',
            'Measure operating cash flow as a percentage of revenue per share.',
            'Measure operating cash flow as a share of revenue minus expenses.',
        ):
            with self.subTest(description=description):
                candidate = replace(self.candidate, description=description)
                checked = self.validator.validate(candidate, skill=None, tests=self.fixtures)
                self.assertFalse(checked.accepted)
                self.assertEqual(checked.executed_tests, 0)
                self.assertTrue(any('definition-to-implementation mismatch' in reason for reason in checked.reasons))

    def test_same_disclosed_table_contains_the_actual_ordered_alternatives(self):
        contract = signal_description_concept_contracts(self.validator.deterministic_functions)
        self.assertIn(['operating cash flow as a share of revenue'],
            contract['financial.operating_cash_flow_margin'])

    def test_wrong_identity_still_fails_even_when_description_is_equivalent(self):
        fixtures = deepcopy(self.fixtures)
        for fixture in fixtures:
            for doc in fixture['documents']:
                doc['metadata']['cik'] = '0001999992'
        checked = self.validator.validate(self.candidate, skill=None, tests=fixtures)
        self.assertFalse(checked.accepted)
