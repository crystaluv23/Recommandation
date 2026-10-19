"""Temp-only prepare boundaries; no real cohort source preparation or acquisition."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import diagnose_reviewed_frozen_source_snapshot as diagnostic
from test_reviewed_companyfacts_profile import CompanyFactsProfileFixture, write_bound
from test_reviewed_frozen_case_inputs import fixture_projection
from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.data.acquisition import HistoricalPriceAdapter
from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.data.resolution import RawInfoRequest
from stock_opportunity_agent.data.sources.massive import _price_bar_from_result


def cf_case(fixture):
    return {'case_id': 'temp-case', 'company_id': fixture.item['company_id'], 'ticker': 'FIXTURE',
        'split': 'discovery', 'prediction_time': '2025-07-31T00:00:00+00:00', 'requests': [{
            'family': 'companyfacts', 'matches': [{'binding': fixture.cache_binding,
                'whole_raw_comparisons': [{'original_record': fixture.raw_binding}]}]}]}


class FrozenSourcePreparationTests(TestCase):
    def test_actual_cf_materializer_profile_all_products_and_cross_namespace_collision(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            fixture = CompanyFactsProfileFixture(root / 'fixture')
            oracle = root / 'unrelated-oracle'; oracle.mkdir()
            case = cf_case(fixture)
            with diagnostic._prepare_only():
                first = diagnostic._financial(case, [], root / 'first', oracle)
            self.assertEqual(first['status'], 'preappend_eligible')
            self.assertEqual(len(first['products']), 2)
            self.assertTrue(all(row['profile_preverified'] for row in first['products']))
            normalization = json.loads(Path(first['normalization']['path']).read_bytes())
            self.assertEqual(normalization['selection']['period_end_from'], '0001-01-01')
            self.assertEqual(len(normalization['expected_products']), 2)
            product = RawInfoDocument.from_dict(json.loads(Path(first['products'][0]['product']['path']).read_bytes()))
            original = replace(product, source_type='financials')
            write_bound(oracle / 'financials' / product.company_id / (product.document_id + '.json'), original.to_dict())
            with diagnostic._prepare_only():
                collision = diagnostic._collision(product, oracle)
            self.assertTrue(collision['collision'])
            self.assertEqual(len(collision['matches']), 1)
            self.assertEqual(json.loads(Path(collision['matches'][0]['original_record']['path']).read_bytes())['source_type'], 'financials')

    def test_pair_variants_keep_clock_exclusions_body_ambiguity_and_raw_identity_conflicts(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve(); fixture = CompanyFactsProfileFixture(root / 'fixture')
            case = cf_case(fixture)
            cached = deepcopy(fixture.cache); cached['retrieved_at'] = '2026-08-01T00:00:00.500000+00:00'
            newer = write_bound(root / 'newer.json', cached)
            case['requests'][0]['matches'].append({'binding': newer,
                'whole_raw_comparisons': [{'original_record': fixture.raw_binding}]})
            selected, audit, status = diagnostic._choose_companyfacts(case, [])
            self.assertEqual(status, 'selected'); self.assertEqual(selected['cache'], newer)
            self.assertEqual(len(audit), 2)
            too_new = deepcopy(cached); too_new['retrieved_at'] = '2026-08-02T00:00:00+00:00'
            case['requests'][0]['matches'].append({'binding': write_bound(root / 'late.json', too_new),
                'whole_raw_comparisons': [{'original_record': fixture.raw_binding}]})
            self.assertEqual(diagnostic._choose_companyfacts(case, [])[1][-1]['status'], 'rejected_pair')
            changed = replace(fixture.raw, metadata={**fixture.raw.metadata, 'extra': True})
            case['requests'][0]['matches'].append({'binding': fixture.cache_binding,
                'whole_raw_comparisons': [{'original_record': write_bound(root / 'conflict.json', changed.to_dict())}]})
            self.assertEqual(diagnostic._choose_companyfacts(case, [])[2], 'ambiguous_source_variants')
            distinct = CompanyFactsProfileFixture(root / 'distinct')
            body = deepcopy(distinct.cache); body['body']['entityName'] = 'Another retained body'
            raw_body = json.dumps(body['body'], sort_keys=True, separators=(',', ':'), ensure_ascii=False)
            raw = RawInfoDocument.create(document_id='sec_edgar:' + case['company_id'] + ':sec_company_facts_raw_response:' +
                diagnostic.hashlib.sha256(raw_body.encode()).hexdigest()[:24], company_id=case['company_id'],
                source_type='sec_company_facts_raw_response', published_at=fixture.raw.published_at,
                available_at=fixture.raw.available_at, content=raw_body, metadata=fixture.raw.metadata)
            changed_case = cf_case(fixture)
            changed_case['requests'][0]['matches'].append({'binding': write_bound(root / 'body2.json', body),
                'whole_raw_comparisons': [{'original_record': write_bound(root / 'raw2.json', raw.to_dict())}]})
            self.assertEqual(diagnostic._choose_companyfacts(changed_case, [])[2], 'ambiguous_source_variants')

    def test_canonical_collision_rejects_boolean_numeric_and_clock_replays(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            clock = datetime(2025, 1, 1, tzinfo=timezone.utc)
            product = RawInfoDocument.create(document_id='sec:issuer:accession', company_id='cik_0000000001',
                source_type='filing', published_at=clock, available_at=clock, content='whole literal body', metadata={'flag': 1})
            path = root / 'sec_filing' / product.company_id / (product.document_id + '.json')
            for original in (replace(product, metadata={'flag': True}), replace(product, available_at=clock + timedelta(hours=1))):
                write_bound(path, original.to_dict())
                self.assertTrue(diagnostic._collision(product, root)['collision'])
            write_bound(path, product.to_dict())
            self.assertFalse(diagnostic._collision(product, root)['collision'])

    def test_additional_receipt_binds_cache_raw_and_actual_response_without_new_proof_kind(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve(); fixture = CompanyFactsProfileFixture(root / 'fixture')
            raw = (root / 'response.raw'); raw.write_text(json.dumps(fixture.body))
            receipt = {'status': 'successful', 'terminal': True, 'GET_attempts': 1, 'automatic_retries': 0,
                'network_open_calls': 1, 'HTTP_responses_retained': 1, 'attempt_reservations': 1,
                'redirects_followed': 0, 'native_cache': fixture.cache_binding, 'raw_response_proof': fixture.raw_binding,
                'requests': [{'method': 'GET', 'status': 'http_response_retained',
                    'url': fixture.item['source_url'], 'response_url': fixture.item['source_url'], 'http_status': 200,
                    'raw_response': str(raw), 'raw_sha256': diagnostic.frozen._stream_binding(raw)['sha256'],
                    'response_headers': {}, 'bytes': len(raw.read_bytes())}]}
            receipt_binding = write_bound(root / 'receipt.json', receipt)
            row = {'company_id': fixture.item['company_id'], 'cache': fixture.cache_binding,
                'rawproof': fixture.raw_binding, 'receipt': receipt_binding}
            table = root / 'additional.json'; write_bound(table, [row])
            rows, bindings = diagnostic._additional(table, {fixture.item['company_id']})
            self.assertEqual(rows, [row]); self.assertIn(diagnostic.frozen._stream_binding(raw), bindings)
            for field, value in (('automatic_retries', False), ('redirects_followed', False),
                    ('http_status', 200.0), ('bytes', float(len(raw.read_bytes())))):
                changed = deepcopy(receipt)
                if field in ('http_status', 'bytes'):
                    changed['requests'][0][field] = value
                else:
                    changed[field] = value
                changed_row = {**row, 'receipt': write_bound(root / (field + '-rehashed.json'), changed)}
                write_bound(table, [changed_row])
                with self.subTest(field=field), self.assertRaises(diagnostic.ReviewedSourceRejected):
                    diagnostic._additional(table, {fixture.item['company_id']})
            variants = [('method', 'POST'), ('status', 'failed')]
            variants.extend((field, value) for field in ('network_open_calls', 'HTTP_responses_retained', 'attempt_reservations')
                for value in (True, 0, False))
            for index, (field, value) in enumerate(variants):
                changed = deepcopy(receipt)
                if field in ('method', 'status'):
                    changed['requests'][0][field] = value
                else:
                    changed[field] = value
                changed_row = {**row, 'receipt': write_bound(root / ('singleton-rehashed-' + str(index) + '.json'), changed)}
                write_bound(table, [changed_row])
                with self.subTest(field=field, value=value), self.assertRaises(diagnostic.ReviewedSourceRejected):
                    diagnostic._additional(table, {fixture.item['company_id']})
            receipt['requests'][0]['response_url'] += '?wrong=1'
            row['receipt'] = write_bound(root / 'receipt-bad.json', receipt); write_bound(table, [row])
            with self.assertRaisesRegex(diagnostic.ReviewedSourceRejected, 'receipt'):
                diagnostic._additional(table, {fixture.item['company_id']})
            with self.assertRaises(diagnostic.ReviewedSourceRejected):
                diagnostic._additional(table, {'cik_9999999999'})
            self.assertEqual(diagnostic._additional(None, set()), ([], []))

    def test_market_actual_origin_and_missing_proofs_keep_distinct_associations(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            normalized = datetime(2026, 8, 2, tzinfo=timezone.utc)
            row = {'t': int(datetime(2025, 1, 2, tzinfo=timezone.utc).timestamp() * 1000),
                'o': 9, 'h': 11, 'l': 8, 'c': 10, 'v': 100}
            bars = [_price_bar_from_result('TEMP', row, normalized, adjusted=True)]
            as_of = datetime(2025, 1, 3, tzinfo=timezone.utc)
            document = HistoricalPriceAdapter('massive', lambda *_: bars).acquire(
                RawInfoRequest('temp', 'offline', ('market_data',), lookback_days=2, max_documents=1),
                company_id='cik_0000000001', identity={'ticker': 'TEMP'}, as_of=as_of).documents[0]
            endpoint = 'https://api.massive.com/v2/aggs/ticker/TEMP/range/1/day/2025-01-01/2025-01-02'
            cache = {'endpoint': endpoint, 'source_key': 'massive', 'capability': 'price_daily', 'payload_kind': 'json',
                'params': [['method', 'GET'], ['adjusted', 'true'], ['limit', '50000'], ['sort', 'asc']],
                'retrieved_at': '2026-08-01T00:00:00+00:00', 'body': {'ticker': 'TEMP', 'adjusted': True,
                    'status': 'OK', 'results': [row], 'resultsCount': 1}}
            request = {'family': 'market_daily', 'endpoint': endpoint,
                'matches': [{'binding': write_bound(root / 'cache.json', cache)}],
                'original_candidates': [{'original_record': write_bound(root / 'original.json', document.to_dict())}]}
            case = {'case_id': 'temp', 'company_id': document.company_id, 'prediction_time': as_of.isoformat(), 'requests': [request]}
            missing = []
            with diagnostic._prepare_only():
                outcome = diagnostic._market(case, missing)
            self.assertEqual(outcome['status'], 'unknown_missing_proofs')
            self.assertTrue(outcome['variants'][0]['complete_canonical_reconstruction'])
            self.assertEqual([x['purpose'] for x in missing], ['historical_issuer', 'all_type_splits'])
            self.assertEqual(missing[1]['query']['execution_date.lte'], '2026-08-02')
            grouped = diagnostic._missing_requests(missing + deepcopy(missing))
            self.assertEqual(len(grouped), 2); self.assertTrue(all(len(x['associations']) == 2 for x in grouped))

    def test_profile_failure_preserves_all_derived_files_expected_set_and_product_dispositions(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve(); fixture = CompanyFactsProfileFixture(root / 'fixture')
            oracle = root / 'oracle'; oracle.mkdir()
            native = diagnostic._verify_companyfacts_document
            calls = []
            def fail_second(*args):
                calls.append(args[0].document_id)
                if len(calls) == 2:
                    raise diagnostic.ReviewedSourceRejected('explicit offline second-product failure')
                return native(*args)
            with diagnostic._prepare_only(), patch.object(diagnostic, '_verify_companyfacts_document', fail_second):
                result = diagnostic._financial(cf_case(fixture), [], root / 'output', oracle)
            self.assertEqual(result['status'], 'unknown_native_profile_failed')
            self.assertEqual(len(result['products']), 2)
            self.assertEqual([x['profile_preverified'] for x in result['products']], [True, False])
            self.assertEqual(len(json.loads(Path(result['normalization']['path']).read_bytes())['expected_products']), 2)
            self.assertEqual(len(list((root / 'output/products').glob('*.json'))), 2)

    def test_operating_bound_primary_mechanical_profile_is_not_wholebody_scope_or_alias_rewrite(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve(); oracle = root / 'oracle'; oracle.mkdir()
            cik, accession = '0000000001', '0000000001-25-000001'
            url = 'https://www.sec.gov/Archives/edgar/data/1/000000000125000001/report.htm'
            accepted = '2025-01-20T12:00:00+00:00'
            root_binding = write_bound(root / 'root.json', {'endpoint': 'https://data.sec.gov/submissions/CIK' + cik + '.json',
                'body': {'cik': 1, 'filings': {'recent': {'accessionNumber': [accession], 'form': ['10-K'],
                    'primaryDocument': ['report.htm'], 'acceptanceDateTime': [accepted]}}}})
            body = write_bound(root / 'body.json', {'endpoint': url, 'body': '<html>Actual whole source fixture.</html>'})
            target = {'accession': accession, 'form': '10-K', 'primary_document': 'report.htm', 'accepted_at': accepted,
                'primary_url': url, 'root_bindings': [root_binding], 'body_cache_matches': [{'binding': body}],
                'candidate_original_document_id': 'sec:cik_' + cik + ':000000000125000001'}
            case = {'case_id': 'temp', 'company_id': 'cik_' + cik, 'prediction_time': '2025-02-01T00:00:00+00:00'}
            with diagnostic._prepare_only():
                result = diagnostic._operating(case, {'selected_annual_interim': [target]}, oracle, [])
            self.assertEqual(result['status'], 'pending_wholebody_semantic_review')
            actual = result['targets'][0]['body_variants'][0]
            self.assertEqual(actual['status'], 'mechanical_profile_preverified_semantic_scope_pending')
            self.assertFalse(result['source_admitted'])
            original = RawInfoDocument.create(document_id=target['candidate_original_document_id'], company_id=case['company_id'],
                source_type='10-k', published_at=datetime.fromisoformat(accepted), available_at=datetime.fromisoformat(accepted),
                content='<html>Actual whole source fixture.</html>', metadata={'provider': 'sec_edgar', 'cik': cik,
                    'form': '10-K', 'accession_number': accession, 'source_url': url})
            original_binding = write_bound(oracle / '10-k' / original.company_id / (original.document_id + '.json'), original.to_dict())
            target['existing_same_id_originals'] = [{'binding': original_binding}]
            with diagnostic._prepare_only(), patch.object(diagnostic.RawInfoDocument, 'create', side_effect=AssertionError('must retain complete original')):
                retained = diagnostic._operating(case, {'selected_annual_interim': [target]}, oracle, [])
            retained_row = retained['targets'][0]['body_variants'][0]
            self.assertEqual(retained_row['candidate_origin'], 'bound_existing_original')
            self.assertEqual(retained_row['status'], 'mechanical_profile_preverified_semantic_scope_pending')
            self.assertFalse(retained_row['collision'])
            self.assertEqual(retained_row['candidate_canonical_record_hash'], canonical_json_hash(original.to_dict()))
            conflicting = replace(original, metadata={**original.metadata, 'flag': True})
            different_binding = write_bound(root / 'different.json', conflicting.to_dict())
            target['existing_same_id_originals'].append({'binding': different_binding})
            changed = diagnostic._operating(case, {'selected_annual_interim': [target]}, oracle, [])
            self.assertEqual(changed['targets'][0]['body_variants'][0]['status'], 'unknown_conflicting_existing_canonical_records')
            self.assertTrue(changed['targets'][0]['body_variants'][0]['collision'])
            wrong_content = replace(original, content='Different retained whole body',
                content_hash=diagnostic.hashlib.sha256(b'Different retained whole body').hexdigest())
            wrong_binding = write_bound(root / 'wrong-content.json', wrong_content.to_dict())
            target['existing_same_id_originals'] = [{'binding': wrong_binding}]
            rejected = diagnostic._operating(case, {'selected_annual_interim': [target]}, oracle, [])
            self.assertEqual(rejected['targets'][0]['body_variants'][0]['status'], 'unknown_native_profile_failed')
            self.assertEqual(diagnostic.frozen._stream_binding(original_binding['path']), original_binding)
            target['body_cache_matches'] = []
            missing = []
            diagnostic._operating(case, {'selected_annual_interim': [target]}, oracle, missing)
            self.assertEqual(missing[0]['endpoint'], url)
            self.assertEqual(missing[0]['root_bindings'], [root_binding])

    def test_prepare_full25_and24_missing_families_stay_in_fixed40_and_cannot_rerun(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            _envelope, _scope, _approved, projection = fixture_projection(root / 'never-reopen-mixed.json')
            old = root / 'old'; old.mkdir()
            projection_path = old / 'case-identities.json'; projection_binding = write_bound(projection_path, projection)
            cohort_binding = write_bound(old / 'plan.json', {'projection': projection_binding, 'groups': []})
            cases = [{**row, 'ticker': projection['identities'][row['company_id']]['ticker'], 'requests': []}
                for row in projection['cases'] if row['split'] != 'anchor'] + [{**projection['cases'][16],
                    'ticker': projection['identities'][projection['cases'][16]['company_id']]['ticker'], 'requests': []}]
            inventory_path = root / 'candidates/inventory.json'
            prior = write_bound(root / 'prior.json', {'source_only': True})
            inventory_binding = write_bound(inventory_path, {'cases': cases, 'prior_inventory': prior, 'read_file_bindings': []})
            operating_path = root / 'operating.json'
            operating_binding = write_bound(operating_path, {'input': inventory_binding, 'read_file_bindings': [],
                'cases': [{**row, 'selected_annual_interim': []} for row in cases]})
            oracle = root / 'oracle'; oracle.mkdir()
            oracle_binding = write_bound(oracle / 'oracle.json', {'fixture': True})
            review_binding = write_bound(root / 'review.json', {'oracle_identity': oracle_binding,
                'records': [{'verdict': 'admitted'} for _ in range(653)] + [{'verdict': 'unknown'} for _ in range(5)]})
            view = root / 'view'; view.mkdir()
            base_path = root / 'base.json'
            base_binding = write_bound(base_path, {'source_review': review_binding, 'reviewed_source_snapshot': {'root': str(view)}})
            fixed = {'projection': projection_binding['sha256'], 'base': base_binding['sha256'],
                'inventory': inventory_binding['sha256'], 'operating': operating_binding['sha256']}
            real_read = diagnostic._bound_json
            def no_mixed(path):
                self.assertNotEqual(Path(path).resolve(), (root / 'never-reopen-mixed.json').resolve())
                return real_read(path)
            with patch.object(diagnostic, 'FIXED_SHA', fixed), patch.object(diagnostic, 'COHORT_PLAN_SHA', cohort_binding['sha256']), \
                    patch.object(diagnostic.frozen, '_code_bindings', return_value=[]), patch.object(diagnostic, '_bound_json', no_mixed):
                result = diagnostic.prepare(projection_path, base_path, inventory_path, None, root / 'output', operating_path)
                self.assertEqual([len(result['outcomes'][x]) for x in ('financial', 'market', 'operating')], [25, 24, 24])
                self.assertTrue(all(row['status'] == 'needs_acquisition' for row in result['outcomes']['financial']))
                self.assertEqual(result['fixed_case_denominator'], 40)
                self.assertEqual(result['derived_product_count'], 0)
                self.assertFalse(result['admission_or_readiness_claim'])
                before = {str(p): p.read_bytes() for p in (root / 'output').rglob('*') if p.is_file()}
                with self.assertRaisesRegex(diagnostic.ReviewedSourceRejected, 'cannot rerun'):
                    diagnostic.prepare(projection_path, base_path, inventory_path, None, root / 'output', operating_path)
                self.assertEqual(before, {str(p): p.read_bytes() for p in (root / 'output').rglob('*') if p.is_file()})
            with diagnostic._prepare_only():
                with self.assertRaisesRegex(diagnostic.ReviewedSourceRejected, 'global store'):
                    RawInfoStore(oracle)
                with self.assertRaisesRegex(diagnostic.ReviewedSourceRejected, 'prepare_inputs'):
                    diagnostic.SignalExecutor.prepare_inputs(None)
