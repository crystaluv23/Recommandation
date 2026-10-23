"""One fixture contract across candidate and stable capability boundaries."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import json
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.signal_evolution import SignalCandidateValidator
from stock_opportunity_agent.signal_library import SignalRegistry, _audit_deterministic_fixture
from tests.test_signal_measurement_input_selection import AS_OF, document, fact, spec


class SignalFixtureExecutionTests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.registry = SignalRegistry(Path(self.temp.name) / 'signals')
        self.validator = SignalCandidateValidator(self.registry, llm_runner=None)
        self.spec = replace(spec('financial.cash_reserves'), signal_id='cash_fixture')
        doc = document('explicit-source', [fact('CashAndCashEquivalentsAtCarryingValue', '2025-03-31', 100)])
        self.fixture = {'name': 'bound-cash', 'company_id': 'cik_0000000001',
            'as_of': AS_OF.isoformat(), 'expected': 'positive', 'documents': [doc.to_dict()]}
        for target in ('socket.socket', 'socket.create_connection'):
            guard = patch(target, side_effect=AssertionError('network forbidden'))
            guard.start(); self.addCleanup(guard.stop)

    def both(self, fixture):
        self.validator._execute_fixture(self.spec, None, fixture, index=0)
        _audit_deterministic_fixture(self.spec, fixture, index=0)

    def reject_both(self, fixture):
        with self.assertRaises(ValidationError):
            self.validator._execute_fixture(self.spec, None, fixture, index=0)
        with self.assertRaises(ValidationError):
            _audit_deterministic_fixture(self.spec, fixture, index=0)

    def test_compatible_typed_source_passes_both_and_real_freeze(self):
        self.both(self.fixture)
        self.registry.register_stable(self.spec, tests=[self.fixture])
        self.assertEqual(self.registry.freeze().specs[0].ref, self.spec.ref)

    def test_explicit_canonical_company_is_not_replaced_by_an_opaque_alias(self):
        row = deepcopy(self.fixture)
        row['documents'][0]['source_type'] = 'financials'
        row['documents'][0]['metadata'] = {}
        self.both(row)

    def test_wrong_declared_company_cannot_be_hidden_by_metadata(self):
        row = deepcopy(self.fixture)
        row['documents'][0]['source_type'] = 'financials'
        row['company_id'] = 'cik_0000000002'
        self.reject_both(row)

    def test_validation_failure_does_not_pass_expected_unavailable(self):
        row = deepcopy(self.fixture)
        row['documents'][0]['source_type'] = 'financials'
        row['documents'][0]['metadata']['cik'] = '0000000002'
        row['expected'] = 'unavailable'
        self.reject_both(row)

    def test_source_objects_are_not_coerced_to_text(self):
        for content in ({'facts': []}, ['not text'], None, 123):
            with self.subTest(content=content):
                row = deepcopy(self.fixture)
                row['documents'][0]['source_type'] = 'financials'
                row['documents'][0]['content'] = content
                row['expected'] = 'unavailable'
                self.reject_both(row)

    def test_missing_issuer_proof_remains_rejected(self):
        row = deepcopy(self.fixture)
        row['documents'][0]['source_type'] = 'financials'
        row.pop('company_id')
        row['documents'][0]['metadata'] = {}
        content = json.loads(row['documents'][0]['content']); content.pop('cik')
        row['documents'][0]['content'] = json.dumps(content)
        self.reject_both(row)

    def test_unrelated_source_and_naive_cutoff_remain_rejected(self):
        row = deepcopy(self.fixture); row['documents'][0]['source_type'] = 'market_data'
        self.reject_both(row)
        row = deepcopy(self.fixture); row['as_of'] = '2025-05-30T00:00:00'
        self.reject_both(row)

    def test_closed_future_corpus_is_domain_unavailable(self):
        row = deepcopy(self.fixture)
        row['expected'] = 'unavailable'
        row['documents'][0]['published_at'] = '2025-06-01T00:00:00+00:00'
        row['documents'][0]['available_at'] = '2025-06-02T00:00:00+00:00'
        self.both(row)
