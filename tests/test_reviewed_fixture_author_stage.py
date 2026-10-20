"""Offline module wiring and fail-closed boundaries; not fresh model evidence."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
from unittest import TestCase
from unittest.mock import patch

from scripts import run_reviewed_fixture_author_stage as stage
from stock_opportunity_agent.models import ValidationError


def offline_answer():
    """Supply explicit scripted fixtures only to test isolated native wiring."""
    rows = []
    for schema in ('legacy', 'typed'):
        facts = [{'start': f'{year}-01-01', 'end': f'{year}-12-31', 'filed': '2025-02-15',
                  'val': value, 'form': '10-K'} for year, value in ((2023, 120), (2024, 150))]
        if schema == 'legacy':
            body = {'cik': '0000000001', 'facts': {'us-gaap': {'Revenues': {'units': {'USD': facts}}}}}
        else:
            body = {'schema_version': 'sec-company-facts-document-v1', 'cik': '0000000001',
                    'filing_date': '2025-02-15', 'form': '10-K',
                    'facts': [{'taxonomy': 'us-gaap', 'tag': 'Revenues', 'unit': 'USD',
                               'start': fact['start'], 'end': fact['end'], 'filed': fact['filed'],
                               'value': fact['val'], 'form': fact['form']} for fact in facts]}
        rows.append({'name': schema + ' positive', 'as_of': stage.CUTOFF,
                     'company_id': 'synthetic_fixture', 'expected': 'positive',
                     'documents': [{'document_id': schema, 'source_type': 'financials',
                                    'published_at': stage.AVAILABLE, 'available_at': stage.AVAILABLE,
                                    'metadata': {'cik': '0000000001'}, 'content': json.dumps(body, sort_keys=True, separators=(',', ':'))}]})
    return {'tests': rows}


class ReviewedFixtureAuthorStageTests(TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name) / 'stage'
        self.root_patch = patch.object(stage, 'STAGE_ROOT', self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        # Bind the same code list as production. Preparation and dispatch remain
        # entirely under a temporary root, never the formal frozen destination.
        stage.prepare(self.root)

    def answer(self, value):
        pending = stage.resume(self.root)
        self.assertEqual(pending['status'], 'pending_independent_role')
        request = pending['pending']
        Path(request['outbox_path']).write_text(value, encoding='utf-8')
        stage.submit(self.root, request['request_hash'], 'offline-wire-test-only')
        return request

    def test_prepare_and_pending_have_one_native_inbox_and_no_answer(self):
        self.assertFalse((self.root / 'exchange').exists())
        first = stage.resume(self.root)
        second = stage.resume(self.root)
        self.assertEqual(first, second)
        inboxes = list((self.root / 'exchange/inbox').glob('*.json'))
        self.assertEqual(len(inboxes), 1)
        inbox = stage.read(inboxes[0])
        self.assertEqual(inbox['max_output_tokens'], 4000)
        self.assertFalse(list((self.root / 'exchange/outbox').glob('*.txt')))
        payload = json.loads(inbox['messages'][1]['content'])
        self.assertEqual(payload['spec']['signal_id'], 'fixture_author_revenue_growth')
        self.assertEqual(len(payload['cited_evidence']), 6)
        self.assertTrue(all(len(row['exact_span']) <= 600 for row in payload['cited_evidence']))

    def test_native_validator_stages_loads_and_executes_both_original_schemas(self):
        answer = offline_answer()
        request = self.answer(json.dumps(answer))
        result = stage.resume(self.root)
        self.assertEqual(result['status'], 'module_completed_requires_independent_review', result)
        loaded = stage.read(self.root / 'loaded-candidate.json')
        self.assertEqual(loaded['loaded_tests'], answer['tests'])
        self.assertEqual(loaded['schemas'], ['legacy', 'typed'])
        self.assertEqual([row['measurement']['value'] for row in loaded['results']], [.25, .25])
        self.assertLessEqual(result['logical_reservation'], 131072)
        self.assertEqual(stage.read(self.root / 'isolated/signals/registry.json'), {'version': 1})
        before = stage._files(self.root)
        with patch.object(stage, '_engine', side_effect=AssertionError('terminal must not execute')):
            restored = stage.resume(self.root)
        self.assertTrue(restored['restored_without_execution'])
        self.assertEqual(before, stage._files(self.root))
        self.assertEqual(len(list((self.root / 'exchange/inbox').glob('*'))), 1)
        with self.assertRaisesRegex(ValidationError, 'terminal'):
            stage.submit(self.root, request['request_hash'], 'other')

    def test_invalid_first_format_is_terminal_without_generic_truncation_rescue(self):
        raw = json.dumps(offline_answer())[:-1]
        request = self.answer(raw)
        result = stage.resume(self.root)
        self.assertEqual(result['status'], 'terminal_failed')
        self.assertIn('first JSON format rejected', result['error'])
        self.assertEqual(Path(request['outbox_path']).read_text(), raw)
        with patch.object(stage, '_engine', side_effect=AssertionError('terminal must not execute')):
            self.assertTrue(stage.resume(self.root)['restored_without_execution'])
        self.assertEqual(len(list((self.root / 'exchange/inbox').glob('*'))), 1)

    def test_wrong_expected_fails_native_validator_and_retains_raw(self):
        answer = offline_answer()
        answer['tests'][0]['expected'] = 'negative'
        request = self.answer(json.dumps(answer))
        result = stage.resume(self.root)
        self.assertEqual(result['status'], 'terminal_failed')
        self.assertIn('received positive', result['error'])
        self.assertTrue(Path(request['outbox_path']).exists())
        self.assertFalse((self.root / 'completion.json').exists())

    def test_missing_schema_fails_private_module_control_after_native_validation(self):
        answer = offline_answer()
        answer['tests'].pop()
        self.answer(json.dumps(answer))
        result = stage.resume(self.root)
        self.assertEqual(result['status'], 'terminal_failed')
        self.assertIn('two-schema', result['error'])

    def test_bad_cik_cannot_bypass_original_native_consumer(self):
        answer = offline_answer()
        answer['tests'][0]['documents'][0]['metadata']['cik'] = '0000000002'
        self.answer(json.dumps(answer))
        result = stage.resume(self.root)
        self.assertEqual(result['status'], 'terminal_failed')
        self.assertIn('contract validation rejected', result['error'])

    def test_fixed_root_and_coherent_budget_or_input_rewrites_are_rejected(self):
        with self.assertRaisesRegex(ValidationError, 'destination'):
            stage.prepare(self.root.parent / 'new-budget')
        for name, transform in (
            ('contract', lambda value: value['limits'].update(max_case_tokens=262144)),
            ('inputs', lambda value: value['accepted']['spec']['parameters'].update(positive_min=.1)),
        ):
            with self.subTest(name=name):
                path = self.root / f'{name}.json'
                original = path.read_bytes()
                manifest_path = self.root / 'manifest.json'
                original_manifest = manifest_path.read_bytes()
                manifest = stage.read(manifest_path)
                manifest.pop('manifest_hash')
                transform(manifest[name])
                stage.atomic_write_json(path, manifest[name])
                manifest['manifest_hash'] = stage.digest(manifest)
                stage.atomic_write_json(manifest_path, manifest)
                with self.assertRaisesRegex(ValidationError, 'changed'):
                    stage.resume(self.root)
                path.write_bytes(original)
                manifest_path.write_bytes(original_manifest)
        self.assertFalse((self.root / 'exchange').exists())

    def test_budget_rejects_correction_stage_output_drift_oversize_and_second_call(self):
        path = self.root / 'budget-request.json'
        base = {'stage': stage.STAGE, 'max_output_tokens': 4000,
                'messages': [{'role': 'user', 'content': 'small'}]}
        for change in ({'stage': stage.STAGE + '_correction'}, {'max_output_tokens': 4001},
                       {'messages': [{'role': 'user', 'content': 'x' * 131072}]}):
            request = {**deepcopy(base), **change}
            stage.atomic_write_json(path, {'request': request})
            with self.assertRaises(ValidationError):
                stage._Budget()({'event_type': 'request_ready', 'request_path': str(path), 'request_hash': 'a' * 64})
        stage.atomic_write_json(path, {'request': base})
        budget = stage._Budget()
        event = {'event_type': 'request_ready', 'request_path': str(path), 'request_hash': 'a' * 64}
        budget(event)
        with self.assertRaises(ValidationError):
            budget(event)

    def test_unbound_submission_and_code_drift_are_rejected(self):
        stage.resume(self.root)
        with self.assertRaisesRegex(ValidationError, 'pending'):
            stage.submit(self.root, 'f' * 64, 'offline')
        manifest = stage.read(self.root / 'manifest.json')
        manifest.pop('manifest_hash')
        manifest['code'][0]['sha256'] = '0' * 64
        manifest['manifest_hash'] = stage.digest(manifest)
        stage.atomic_write_json(self.root / 'manifest.json', manifest)
        with self.assertRaisesRegex(ValidationError, 'code/source'):
            stage.resume(self.root)

    def test_same_ratio_different_facts_cannot_satisfy_frozen_positive(self):
        answer = offline_answer()
        for fixture in answer['tests']:
            raw = fixture['documents'][0]
            body = json.loads(raw['content'])
            facts = body['facts'] if isinstance(body['facts'], list) else body['facts']['us-gaap']['Revenues']['units']['USD']
            for fact in facts:
                key = 'value' if 'value' in fact else 'val'
                fact[key] *= 10
            raw['content'] = json.dumps(body, sort_keys=True, separators=(',', ':'))
        self.answer(json.dumps(answer))
        result = stage.resume(self.root)
        self.assertEqual(result['status'], 'terminal_failed')
        self.assertIn('two-schema', result['error'])

    def test_memory_only_store_and_fixed_registry_constructor_guard(self):
        other = self.root.parent / 'real-store'
        with stage._guard(self.root):
            self.assertIsNone(stage.RawInfoStore().root)
            with self.assertRaises(ValidationError):
                stage.RawInfoStore(other)
            with self.assertRaises(ValidationError):
                stage.SignalRegistry(other)
        self.assertFalse(other.exists())

    def test_boolean_integer_contract_drift_is_not_equal(self):
        manifest = stage.read(self.root / 'manifest.json')
        manifest.pop('manifest_hash')
        manifest['contract']['max_calls'] = True
        stage.atomic_write_json(self.root / 'contract.json', manifest['contract'])
        manifest['manifest_hash'] = stage.digest(manifest)
        stage.atomic_write_json(self.root / 'manifest.json', manifest)
        with self.assertRaisesRegex(ValidationError, 'contract changed'):
            stage.resume(self.root)

    def test_receipt_raw_drift_blocks_terminal_restore(self):
        request = self.answer(json.dumps(offline_answer()))
        result = stage.resume(self.root)
        self.assertEqual(result['status'], 'module_completed_requires_independent_review')
        Path(request['outbox_path']).write_text('{}')
        with self.assertRaisesRegex(ValidationError, 'terminal artifact drift'):
            stage.resume(self.root)

    def test_merged_schema_fixture_cannot_replace_two_independent_positives(self):
        answer = offline_answer()
        answer['tests'][0]['documents'] += answer['tests'][1]['documents']
        answer['tests'].pop()
        self.answer(json.dumps(answer))
        result = stage.resume(self.root)
        self.assertEqual(result['status'], 'terminal_failed')
        self.assertIn('two-schema', result['error'])

    def test_equivalent_valid_cik_representations_remain_accepted(self):
        answer = offline_answer()
        for index, fixture in enumerate(answer['tests']):
            row = fixture['documents'][0]
            body = json.loads(row['content'])
            body['cik'] = 1 if index == 0 else ' 1 '
            row['metadata']['cik'] = ' 0000000001 ' if index == 0 else 1
            row['content'] = json.dumps(body, sort_keys=True, separators=(',', ':'))
        self.answer(json.dumps(answer))
        result = stage.resume(self.root)
        self.assertEqual(result['status'], 'module_completed_requires_independent_review', result)

    def test_time_drift_cannot_replace_frozen_publication(self):
        answer = offline_answer()
        for fixture in answer['tests']:
            fixture['documents'][0]['published_at'] = '2025-02-17T00:00:00+00:00'
            fixture['documents'][0]['available_at'] = '2025-02-17T00:00:00+00:00'
        self.answer(json.dumps(answer))
        result = stage.resume(self.root)
        self.assertEqual(result['status'], 'terminal_failed')
        self.assertIn('two-schema', result['error'])

    def test_dead_literal_carrier_cannot_replace_actual_typed_fact_rows(self):
        answer = offline_answer()
        row = answer['tests'][1]['documents'][0]
        body = json.loads(row['content'])
        body['nonfact_literal_copies'] = deepcopy(body['facts'])
        for fact in body['facts']:
            fact.pop('filed')
            fact.pop('form')
        row['content'] = json.dumps(body, sort_keys=True, separators=(',', ':'))
        self.answer(json.dumps(answer))
        result = stage.resume(self.root)
        self.assertEqual(result['status'], 'terminal_failed')
        self.assertIn('two-schema', result['error'])

    def test_same_ratio_alternative_basis_cannot_hide_beside_supplied_rows(self):
        answer = offline_answer()
        for fixture in answer['tests']:
            row = fixture['documents'][0]
            body = json.loads(row['content'])
            facts = body['facts'] if isinstance(body['facts'], list) else body['facts']['us-gaap']['Revenues']['units']['USD']
            alternatives = deepcopy(facts)
            for fact in alternatives:
                key = 'value' if 'value' in fact else 'val'
                fact[key] *= 10
                fact['filed'] = '2025-02-14'
            facts[:0] = alternatives
            row['content'] = json.dumps(body, sort_keys=True, separators=(',', ':'))
        self.answer(json.dumps(answer))
        result = stage.resume(self.root)
        self.assertEqual(result['status'], 'terminal_failed')
        self.assertIn('two-schema', result['error'])
