"""Local proof identity/shape controls, never new market data or model answers."""
import copy
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import sys
from unittest import TestCase
from unittest.mock import patch

from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.data.acquisition import HistoricalPriceAdapter
from stock_opportunity_agent.data.raw_info import RawInfoStore, RawInfoOracle
from stock_opportunity_agent.data.resolution import RawInfoRequest
from stock_opportunity_agent.data.reviewed_snapshot import (
    materialize_reviewed_snapshot, open_raw_info_store, ReviewedRawInfoStore, ReviewedSourceRejected,
)
from stock_opportunity_agent.data.sources.massive import _price_bar_from_result
from stock_opportunity_agent.research.evolution_core import _prediction_baseline_from_market_documents

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / 'reports/local-trusted-source-market-review-20261019.json'


def bound(path):
    return {'path': str(path.resolve()), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False))
    return bound(path)


def save_review(base, review):
    review['manifest_hash'] = canonical_json_hash({k: v for k, v in review.items() if k != 'manifest_hash'})
    path = base / 'review.json'
    write(path, review)
    return path


def rebound_proof(base, review, kind, body_change=lambda _x: None, request_change=lambda _x: None):
    proof = next(p for p in review['records'][-1]['proofs'] if p['kind'] == kind)
    original_path = Path(proof['artifact']['path'])
    body = json.loads(original_path.read_text())
    body_change(body)
    proof['artifact'] = write(base / kind / original_path.name, body)
    if 'request_record' in proof:
        records = json.loads(Path(proof['request_record']['path']).read_text())
        entry = next(r for r in records if r['name'] == proof['entry_name'])
        entry['raw_response'] = original_path.name
        entry['sha256'] = proof['artifact']['sha256']
        request_change(entry)
        proof['request_record'] = write(base / kind / 'results.json', records)


class ReviewedMarketProfileTests(TestCase):
    def setUp(self):
        self.addCleanup(patch.stopall)
        patch('socket.socket', side_effect=AssertionError('network forbidden')).start()

    def test_real_original_baseline_restore_and_optional_corroboration(self):
        for include_overlap in (True, False):
            with self.subTest(include_overlap=include_overlap), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                review = json.loads(REVIEW.read_text())
                if not include_overlap:
                    review['records'][-1]['proofs'] = [p for p in review['records'][-1]['proofs'] if p['kind'] != 'massive_unadjusted_overlap']
                binding = materialize_reviewed_snapshot(save_review(base, review), base / 'view')
                store = open_raw_info_store(binding['root'], reviewed_snapshot=binding)
                self.assertIsInstance(store.snapshot(), ReviewedRawInfoStore)
                self.assertEqual(len(store.documents), 3)
                original = json.loads(Path(review['records'][-1]['original_record']['path']).read_text())
                doc = store.load(original['document_id'])
                self.assertEqual(doc.to_dict(), original)
                cutoff = datetime.fromisoformat(review['scope']['as_of'])
                baseline = _prediction_baseline_from_market_documents((doc,), cutoff)
                self.assertEqual(baseline['status'], 'available')
                bars = json.loads(doc.content)
                self.assertEqual(baseline['trading_dates'], [r['as_of_date'] for r in bars[-5:]])
                self.assertEqual(baseline['mean_adjusted_close'], sum(r['adjusted_close'] for r in bars[-5:]) / 5)
                self.assertFalse(store.append(doc))

    def test_rebound_wrong_proof_and_request_variants_are_rejected(self):
        cases = [
            ('origin_endpoint', 'massive_daily_origin', lambda b: b.update(endpoint='https://example.invalid/aggs'), lambda r: None),
            ('origin_adjusted', 'massive_daily_origin', lambda b: b['body'].update(adjusted=False), lambda r: None),
            ('origin_params', 'massive_daily_origin', lambda b: b['params'].append(['adjusted', 'true']), lambda r: None),
            ('origin_endwindow', 'massive_daily_origin', lambda b: b.update(endpoint=b['endpoint'] + '/extra'), lambda r: None),
            ('origin_pagination', 'massive_daily_origin', lambda b: b['body'].update(next_url='https://api.massive.com/next'), lambda r: None),
            ('issuer_cik', 'massive_historical_issuer', lambda b: b['results'].update(cik='0000000042'), lambda r: None),
            ('issuer_symbol', 'massive_historical_issuer', lambda b: b['results'].update(ticker='OTHER'), lambda r: None),
            ('issuer_request_date', 'massive_historical_issuer', lambda b: None, lambda r: r['query'].update(date='2025-09-28')),
            ('issuer_endpoint', 'massive_historical_issuer', lambda b: None, lambda r: r.update(endpoint='https://example.invalid/identity')),
            ('split_nonempty', 'massive_no_post_cutoff_splits', lambda b: b.update(results=[{'execution_date': '2025-10-01'}]), lambda r: None),
            ('split_pagination', 'massive_no_post_cutoff_splits', lambda b: b.update(next_url='https://api.massive.com/next'), lambda r: None),
            ('split_type_filter', 'massive_no_post_cutoff_splits', lambda b: None, lambda r: r['query'].update(type='forward_split')),
            ('split_short_end', 'massive_no_post_cutoff_splits', lambda b: None, lambda r: r['query'].update({'execution_date.lte': '2026-08-15'})),
            ('split_short_start', 'massive_no_post_cutoff_splits', lambda b: None, lambda r: r['query'].update({'execution_date.gte': '2025-10-01'})),
            ('split_early_get', 'massive_no_post_cutoff_splits', lambda b: None, lambda r: r.update(retrieved_at='2026-08-16T07:28:08+00:00')),
            ('split_naive_get', 'massive_no_post_cutoff_splits', lambda b: None, lambda r: r.update(retrieved_at='2026-10-19T09:24:32')),
            ('overlap_changed_price', 'massive_unadjusted_overlap', lambda b: b['results'][0].update(c=999), lambda r: None),
        ]
        for name, kind, body_change, request_change in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                review = json.loads(REVIEW.read_text())
                rebound_proof(base, review, kind, body_change, request_change)
                with self.assertRaises(ReviewedSourceRejected):
                    materialize_reviewed_snapshot(save_review(base, review), base / 'view')
                self.assertFalse((base / 'view').exists())

    def test_falsey_pagination_shape_regression(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            review = json.loads(REVIEW.read_text())
            rebound_proof(base, review, 'massive_daily_origin', lambda b: b['body'].update(next_url=[]))
            with self.assertRaises(ReviewedSourceRejected):
                materialize_reviewed_snapshot(save_review(base, review), base / 'view')

    def test_pagination_aliases_reject_malformed_shapes_and_accept_null(self):
        for kind in ('massive_daily_origin', 'massive_historical_issuer', 'massive_no_post_cutoff_splits'):
            for key in ('next_url', 'next_page', 'next_page_token'):
                for value in (0, False, [], {}, '', None):
                    with self.subTest(kind=kind, key=key, value=value), tempfile.TemporaryDirectory() as directory:
                        base = Path(directory)
                        review = json.loads(REVIEW.read_text())
                        def mutate(body):
                            (body['body'] if kind == 'massive_daily_origin' else body)[key] = value
                        rebound_proof(base, review, kind, mutate)
                        if value is None:
                            binding = materialize_reviewed_snapshot(save_review(base, review), base / 'view')
                            self.assertEqual(len(open_raw_info_store(binding['root'], reviewed_snapshot=binding).documents), 3)
                        else:
                            with self.assertRaises(ReviewedSourceRejected):
                                materialize_reviewed_snapshot(save_review(base, review), base / 'view')

    def test_malformed_timestamps_are_typed_source_rejections(self):
        for timestamp in (10 ** 100, float('inf'), float('nan'), None, True):
            with self.subTest(timestamp=timestamp), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                review = json.loads(REVIEW.read_text())
                rebound_proof(base, review, 'massive_daily_origin', lambda b: b['body']['results'][0].update(t=timestamp))
                with self.assertRaises(ReviewedSourceRejected):
                    materialize_reviewed_snapshot(save_review(base, review), base / 'view')

    def test_normalization_prices_and_all_bar_clocks_are_bound(self):
        for variant in ('metadata_prices', 'one_bar_clock', 'naive_published', 'missing_price'):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                review = json.loads(REVIEW.read_text())
                old_root = Path(review['oracle_identity']['path']).parent
                oracle = base / 'oracle'
                review['oracle_identity'] = write(oracle / 'oracle.json', json.loads((old_root / 'oracle.json').read_text()))
                for row in review['records']:
                    path = Path(row['original_record']['path'])
                    value = json.loads(path.read_text())
                    if row is review['records'][-1]:
                        if variant == 'metadata_prices': value['metadata']['prices'][0] = 999
                        elif variant == 'naive_published': value['published_at'] = value['published_at'][:19]
                        elif variant == 'missing_price': value['metadata'].pop('prices')
                        else:
                            content = json.loads(value['content'])
                            content[-1]['retrieved_at'] = '2026-08-17T00:00:00+00:00'
                            value['content'] = json.dumps(content, sort_keys=True, separators=(',', ':'))
                            value['content_hash'] = hashlib.sha256(value['content'].encode()).hexdigest()
                            row['content_hash'] = value['content_hash']
                    row['original_record'] = write(oracle / path.relative_to(old_root), value)
                with self.assertRaises(ReviewedSourceRejected):
                    materialize_reviewed_snapshot(save_review(base, review), base / 'view')

    def test_sec_parallel_array_malformed_stays_on_typed_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            review = json.loads(REVIEW.read_text())
            proof = review['records'][0]['proofs'][1]
            cache = json.loads(Path(proof['artifact']['path']).read_text())
            cache['body']['filings']['recent']['acceptanceDateTime'] = []
            proof['artifact'] = write(base / 'bad-submissions.json', cache)
            with self.assertRaises(ReviewedSourceRejected):
                materialize_reviewed_snapshot(save_review(base, review), base / 'view')

    def test_actual_diagnostic_freeze_loader_factory_and_runtime_baseline(self):
        sys.path.insert(0, str(ROOT / 'scripts'))
        from diagnose_reviewed_market_snapshot import diagnose
        with tempfile.TemporaryDirectory() as directory:
            result = diagnose(REVIEW, Path(directory) / 'diagnostic')
            self.assertTrue(result['narrow_source_checks_passed'])
            self.assertTrue(result['old_sec_view_unchanged'])
            self.assertEqual(result['runtime_baseline']['status'], 'available')
            self.assertFalse(result['baseline_day_boundary_family_closed'])
            self.assertFalse(result['full_factory_zero_external_preflight_proven'])
            self.assertEqual(result['new_model_responses'], 0)
            self.assertEqual(result['readonly_data_requests'], 0)
            self.assertEqual(result['fixed_source_denominator'], 5)

    def test_later_review_scope_cannot_leave_earliest_consumer_unproved(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            review = json.loads(REVIEW.read_text())
            review['scope']['as_of'] = '2025-10-15T00:00:00+00:00'
            rebound_proof(base, review, 'massive_no_post_cutoff_splits',
                request_change=lambda r:r['query'].update({'execution_date.gte':'2025-10-15'}))
            with self.assertRaises(ReviewedSourceRejected):
                materialize_reviewed_snapshot(save_review(base,review),base/'view')

    def test_earliest_consumer_coverage_accepts_exact_or_superset_after_later_review(self):
        for start, end in (('2025-09-30','2026-08-16'), ('2025-09-01','2026-08-17')):
            with self.subTest(start=start,end=end), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                review = json.loads(REVIEW.read_text())
                review['scope']['as_of'] = '2025-10-15T00:00:00+00:00'
                rebound_proof(base, review, 'massive_no_post_cutoff_splits',
                    request_change=lambda r:r['query'].update({'execution_date.gte':start,'execution_date.lte':end}))
                binding = materialize_reviewed_snapshot(save_review(base,review),base/'view')
                store = open_raw_info_store(binding['root'],reviewed_snapshot=binding)
                doc = store.load(review['records'][-1]['document_id'])
                self.assertEqual(store.load(doc.document_id,as_of=doc.available_at),doc)
                self.assertIn(doc,store.snapshot().search(doc.company_id,as_of=doc.available_at))

    def test_synthetic_weekend_cutoff_and_equivalent_timezone_clocks(self):
        # Synthetic generic source-shape positive: no actual source admission.
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            symbol, company = 'TEST', 'cik_0000000042'
            normalized = datetime(2025, 7, 2, 0, 0, 0, 1000, tzinfo=timezone.utc)
            raw_rows = [{'t': int(datetime(2025, 6, day, tzinfo=timezone.utc).timestamp() * 1000),
                         'o': 10, 'h': 12, 'l': 9, 'c': 11, 'v': 3} for day in (26, 27)]
            bars = [_price_bar_from_result(symbol, row, normalized, adjusted=True) for row in raw_rows]
            doc = HistoricalPriceAdapter('massive', lambda *_args: bars).acquire(
                RawInfoRequest('fixture', 'Synthetic fixture.', ('market_data',), lookback_days=3),
                company_id=company, identity={'ticker': symbol}, as_of=datetime(2025, 6, 29, tzinfo=timezone.utc)).documents[0]
            RawInfoOracle.load_or_create(base / 'oracle')
            oracle = RawInfoStore(base / 'oracle')
            oracle.append(doc)
            record = base / 'oracle' / 'market_data' / company / (doc.document_id + '.json')
            endpoint = 'https://api.massive.com/v2/aggs/ticker/TEST/range/1/day/2025-06-26/2025-06-28'
            origin = {'kind': 'massive_daily_origin', 'artifact': write(base / 'cache.json', {
                'endpoint': endpoint, 'source_key': 'massive', 'capability': 'price_daily', 'payload_kind': 'json',
                'retrieved_at': '2025-07-02T00:00:00+00:00', 'params': [['method','GET'],['adjusted','true'],['limit','50000'],['sort','asc']],
                'body': {'status':'OK','ticker':symbol,'adjusted':True,'results':raw_rows,'resultsCount':2}}),
                'provider_retrieved_at':'2025-07-02T08:00:00+08:00','normalization_retrieved_at':'2025-07-01T20:00:00.001-04:00'}
            identity = {'ticker':symbol,'cik':'0000000042','market':'stocks','locale':'us','primary_exchange':'XNYS','type':'CS','currency_name':'usd'}
            proofs, records = [origin], []
            for kind, name, ep, query, body in (
                ('massive_historical_issuer','identity','https://api.massive.com/v3/reference/tickers/TEST',{'date':'2025-06-27'},{'status':'OK','results':identity}),
                ('massive_no_post_cutoff_splits','splits','https://api.massive.com/stocks/v1/splits',{'ticker':symbol,'execution_date.gte':'2025-06-28','execution_date.lte':'2025-07-02','sort':'execution_date.asc','limit':'10'},{'status':'OK','results':[]})):
                artifact=write(base/(name+'.json'),body)
                records.append({'name':name,'endpoint':ep,'query':query,'retrieved_at':'2025-07-03T00:00:00+00:00','http_status':200,'provider_status':'OK','next_page_present':False,'raw_response':name+'.json','sha256':artifact['sha256']})
                proof={'kind':kind,'artifact':artifact,'entry_name':name}
                if name=='identity': proof['expected_identity']=identity
                proofs.append(proof)
            requests=write(base/'results.json',records)
            for proof in proofs[1:]: proof['request_record']=requests
            review={'schema_version':'reviewed-raw-info-snapshot-v1','scope':{'company_ids':[company],'as_of':'2025-06-28T20:00:00-04:00','acquisition_allowed':False},
                'oracle_identity':bound(base/'oracle/oracle.json'),'records':[{'document_id':doc.document_id,'company_id':company,'content_hash':doc.content_hash,'original_record':bound(record),'verdict':'admitted','reviewed_available_at':doc.available_at.isoformat(),'proof_profile':'massive_daily_no_post_cutoff_split_v1','proofs':proofs}]}
            binding=materialize_reviewed_snapshot(save_review(base,review),base/'view')
            self.assertLess(doc.available_at,datetime.fromisoformat(review['scope']['as_of']))
            restored=open_raw_info_store(binding['root'],reviewed_snapshot=binding)
            self.assertEqual(restored.documents[0].to_dict(),doc.to_dict())
