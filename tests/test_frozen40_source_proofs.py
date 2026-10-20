"""Offline exact proof collector controls; no production GET or source admission."""
from contextlib import ExitStack, contextmanager
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import urlsplit

PATH = Path(__file__).resolve().parents[1] / 'runs/diagnostics/frozen40_source_proofs_20261020_v1/collector.py'
spec = importlib.util.spec_from_file_location('fixed_proof_collector', PATH)
collector = importlib.util.module_from_spec(spec); spec.loader.exec_module(collector)


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True))
    return collector.bound(path)


class Clock:
    def __init__(self):
        self.value = datetime(2026, 10, 19, tzinfo=timezone.utc)
        self.waited = 0
    def __call__(self):
        return self.value
    def sleep(self, seconds):
        self.waited += seconds; self.value += timedelta(seconds=seconds)


class Response:
    def __init__(self, url, raw, status=200, headers=None):
        self.url, self.raw, self.status = url, raw, status
        self.headers = headers or {}
    def read(self):
        return self.raw
    def geturl(self):
        return self.url
    def __enter__(self):
        return self
    def __exit__(self, *_args):
        pass


class Opener:
    def __init__(self, output, *, mode=None):
        self.output, self.mode, self.calls, self.snapshots = output, mode, [], []
    def open(self, request, timeout):
        result = json.loads((self.output / 'results.json').read_bytes())
        assert result['attempt_reservations'] >= len(self.calls) + 1
        assert result['GET_attempts'] == len(self.calls) + 1
        assert result['network_open_calls'] == len(self.calls) + 1
        assert timeout == 30
        self.snapshots.append(result)
        self.calls.append(request.full_url)
        path = urlsplit(request.full_url).path
        if 'api.massive.com' in request.full_url:
            if self.mode == 'http403':
                raise HTTPError(request.full_url, 403, 'forbidden', {}, io.BytesIO(b'blocked'))
            if self.mode == 'transport':
                raise OSError('fake offline transport failure')
            if self.mode == 'transport_secret':
                raise OSError('fake test-runtime-secret transport failure')
            if self.mode == 'read_secret':
                class BrokenResponse(Response):
                    def read(self):
                        raise OSError('fake test-runtime-secret read failure')
                return BrokenResponse(request.full_url, b'')
            if self.mode == 'gzip_secret':
                return Response(request.full_url, gzip.compress(b'{"echo":"test-runtime-secret"}'), headers={'Content-Encoding': 'gzip'})
            if self.mode == 'escaped_secret':
                return Response(request.full_url, b'{"echo":"\\u0074est-runtime-secret"}')
            if self.mode == 'secret':
                return Response(request.full_url, b'{"echo":"test-runtime-secret"}')
            if self.mode == 'page':
                return Response(request.full_url, b'{"status":"OK","results":[],"next_url":"https://no-follow.invalid"}')
            if '/reference/' in path:
                body = {'status': 'OK', 'results': {'ticker': 'ABC', 'cik': '0000000001'}}
            elif '/aggs/' in path:
                body = {'status': 'OK', 'ticker': 'FTI', 'adjusted': True, 'results': [{
                    't': int(datetime(2025, 5, 29, tzinfo=timezone.utc).timestamp() * 1000),
                    'o': 10, 'h': 11, 'l': 9, 'c': 10, 'v': 123}]}
            else:
                body = {'status': 'OK', 'results': [{'execution_date': '2025-02-01'}] if self.mode == 'nonempty' else []}
            return Response(request.full_url, gzip.compress(json.dumps(body).encode()), headers={'Content-Encoding': 'gzip'})
        return Response(request.full_url, gzip.compress(b'<html>Exact retained offline primary.</html>'), headers={'Content-Encoding': 'gzip'})


@contextmanager
def fixture(root, *, history=False, reuse=False, daily=False, exhibits=False):
    cutoff = '2025-01-31T00:00:00+00:00'
    accepted = '2025-01-20T12:00:00+00:00'
    endpoint = 'https://www.sec.gov/Archives/edgar/data/1/000000000125000001/report.htm'
    root_binding = save(root / 'sec-root.json', {'body': {'cik': 1, 'filings': {'recent': {
        'accessionNumber': ['0000000001-25-000001'], 'filingDate': ['2025-01-20'], 'reportDate': ['2024-12-31'],
        'form': ['10-K'], 'primaryDocument': ['report.htm'], 'acceptanceDateTime': [accepted]}}}})
    association = {'case_id': 'cik_0000000001:20250131'}
    rows = [
        {'endpoint': 'https://api.massive.com/v3/reference/tickers/ABC', 'query': {'date': '2025-01-30'},
            'associations': [{**association, 'purpose': 'historical_issuer'}]},
        {'endpoint': 'https://api.massive.com/stocks/v1/splits', 'query': {'ticker': 'ABC',
            'execution_date.gte': '2025-01-31', 'execution_date.lte': '2026-08-01', 'sort': 'execution_date.asc', 'limit': '1000'},
            'associations': [{**association, 'purpose': 'all_type_splits'}]},
        {'endpoint': endpoint, 'query': {}, 'associations': [{**association, 'purpose': 'exact_static_primary_body',
            'accession_number': '0000000001-25-000001', 'form': '10-K', 'accepted_at': accepted, 'root_bindings': [root_binding]}]},
    ]
    missing = root / 'missing.json'; missing_binding = save(missing, rows)
    price_cache = root / 'old-workspace/cache/data/massive/price_daily/existing.json'
    save(price_cache, {'fixture_only': True})
    inv = root / 'inventory.json'; inventory_binding = save(inv, {'cases': [{'requests': [{
        'family': 'market_daily', 'matches': [{'binding': collector.bound(price_cache)}]}]}]})
    headers = root / 'headers-plan.json'; save(headers, {'request_headers': {'User-Agent': 'Offline fixture contact@example.invalid'}})
    old = root / 'old-proofs'; old.mkdir()
    if reuse:
        artifact = old / 'retained.json'; save(artifact, {'status': 'OK', 'results': {'ticker': 'ABC'}})
        save(old / 'results.json', [{'name': 'old-issuer', 'endpoint': rows[0]['endpoint'], 'query': rows[0]['query'],
            'http_status': 200, 'provider_status': 'OK', 'next_page_present': False, 'retrieved_at': '2026-08-02T00:00:00+00:00',
            'raw_response': 'retained.json', 'sha256': collector.bound(artifact)['sha256']}])
    if history:
        ledger = price_cache.parents[4] / 'data_requests.jsonl'
        events = [{'source_key': 'massive', 'capability': 'price_daily', 'endpoint': 'https://api.massive.com/old',
            'cache_key': 'old-' + str(i), 'status': 'fetched', 'requested_at': '2026-10-19T00:00:00+00:00'} for i in range(5)]
        ledger.write_text(''.join(json.dumps(x) + '\n' for x in events))
    extra = None
    if daily:
        extra = root / 'extra.json'
        save(extra, {'request': {'endpoint': 'https://api.massive.com/v2/aggs/ticker/FTI/range/1/day/2024-04-25/2025-05-29',
            'query': {'adjusted': 'true', 'sort': 'asc', 'limit': '50000'}}, 'case': {'company_id': 'cik_0001681459'},
            'inputs': [], 'definitions': []})
    exhibit_path = None
    if exhibits:
        exhibit_path = root / 'exhibits.json'
        urls = ['https://www.sec.gov/Archives/edgar/data/1847409/000162828025002990/hiti-annualinformationform.htm',
            'https://www.sec.gov/Archives/edgar/data/1847409/000162828025002990/hiti-exhibit992mda.htm']
        save(exhibit_path, {'requests': [{'endpoint': url, 'query': {}, 'parent_original': root_binding,
            'parent_root_proofs': [root_binding]} for url in urls], 'inputs': []})
    with ExitStack() as stack:
        for name, value in [('MISSING_SHA', missing_binding['sha256']), ('INVENTORY_SHA', inventory_binding['sha256']),
                ('COUNTS', {'historical_issuer': 1, 'all_type_splits': 1, 'exact_static_primary_body': 1}),
                ('HEADERS_PLAN', headers), ('OLD_PROOFS', old)]:
            stack.enter_context(patch.object(collector, name, value))
        if extra:
            stack.enter_context(patch.object(collector, 'ADDITIONAL_SHA', collector.bound(extra)['sha256']))
        if exhibit_path:
            stack.enter_context(patch.object(collector, 'EXHIBITS_SHA', collector.bound(exhibit_path)['sha256']))
        plan = collector.prepare(root / 'new', missing=missing, inventory=inv, additional_daily_origin=extra, additional_exhibits=exhibit_path)
        yield plan, root / 'new/request-plan.json'


class Frozen40ProofCollectorTests(TestCase):
    def run_collection(self, plan, path, *, mode=None, clock=None):
        clock = clock or Clock(); opener = Opener(Path(plan['output']), mode=mode)
        value = collector.collect(path, collector.bound(path)['sha256'], opener=opener, clock=clock,
            sleep=clock.sleep, credential_loader=lambda: 'test-runtime-secret')
        return value, opener, clock

    def test_native_success_gzip_exact_source_records_and_terminal_no_reentry(self):
        with TemporaryDirectory() as directory, fixture(Path(directory).resolve()) as (plan, path):
            result, opener, _clock = self.run_collection(plan, path)
            self.assertEqual(result['status'], 'completed'); self.assertEqual(len(opener.calls), 3)
            self.assertEqual((result['attempt_reservations'], result['GET_attempts'], result['network_open_calls']), (3, 3, 3))
            self.assertEqual(len(result['dispositions']), 3)
            records = collector.read_bound(result['market_request_record'])
            for row in records:
                proof = {'artifact': collector.bound(Path(plan['output']) / row['raw_response']),
                    'request_record': result['market_request_record'], 'entry_name': row['name']}
                collector._market_response(proof, row['endpoint'], row['query'])
            for disposition in result['dispositions']:
                cached = collector.read_bound(disposition['native_cache'])
                self.assertNotIn('apiKey', json.dumps(cached))
            before = {str(p): p.read_bytes() for p in Path(plan['output']).rglob('*') if p.is_file()}
            with self.assertRaisesRegex(ValueError, 'cannot reenter'):
                self.run_collection(plan, path)
            self.assertEqual(before, {str(p): p.read_bytes() for p in Path(plan['output']).rglob('*') if p.is_file()})

    def test_known_native_usage_paces_before_first_attempt_without_reset(self):
        with TemporaryDirectory() as directory, fixture(Path(directory).resolve(), history=True) as (plan, path):
            history = [(Path(p), Path(p).read_bytes()) for p in plan['native_ledger_paths']]
            result, _opener, clock = self.run_collection(plan, path)
            self.assertEqual(result['status'], 'completed'); self.assertGreaterEqual(clock.waited, 60)
            for p, raw in history:
                self.assertEqual(p.read_bytes(), raw)

    def test_provider_page_http_and_transport_failure_stop_only_their_host(self):
        for mode in ('page', 'http403', 'transport'):
            with self.subTest(mode=mode), TemporaryDirectory() as directory, fixture(Path(directory).resolve()) as (plan, path):
                result, opener, _clock = self.run_collection(plan, path, mode=mode)
                self.assertEqual(result['status'], 'completed_with_host_failures')
                self.assertEqual([x['status'] for x in result['dispositions']], ['failed_typed', 'blocked_by_host_failure', 'received'])
                self.assertEqual(len(opener.calls), 2)

    def test_nonempty_splits_are_retained_unsupported_and_do_not_stop_other_requests(self):
        with TemporaryDirectory() as directory, fixture(Path(directory).resolve()) as (plan, path):
            result, opener, _clock = self.run_collection(plan, path, mode='nonempty')
            self.assertEqual(len(opener.calls), 3)
            self.assertEqual(result['dispositions'][1]['status'], 'received_unsupported_nonempty_split_ledger')
            self.assertEqual(result['dispositions'][2]['status'], 'received')

    def test_secret_echo_is_never_persisted_and_host_stops(self):
        for mode in ('secret', 'gzip_secret', 'escaped_secret', 'transport_secret', 'read_secret'):
            with self.subTest(mode=mode), TemporaryDirectory() as directory, fixture(Path(directory).resolve()) as (plan, path):
                result, opener, _clock = self.run_collection(plan, path, mode=mode)
                expected = 'transport' if mode in ('transport_secret', 'read_secret') else 'credential_echo'
                self.assertEqual(result['dispositions'][0]['failure_stage'], expected)
                self.assertEqual((opener.snapshots[0]['GET_attempts'], opener.snapshots[0]['network_open_calls']), (1, 1))
                self.assertEqual(opener.snapshots[1]['HTTP_responses_retained'], 0)
                self.assertEqual(result['HTTP_responses_retained'], 1)
                self.assertEqual([x['status'] for x in result['dispositions']], ['failed_typed', 'blocked_by_host_failure', 'received'])
                self.assertNotIn('raw_response', result['requests'][0])
                self.assertFalse(any((Path(plan['output']) / 'cache/data/massive').rglob('*.json')))
                self.assertTrue(all(b'test-runtime-secret' not in p.read_bytes() for p in Path(plan['output']).rglob('*') if p.is_file()))

    def test_exact_retained_http_proof_reuses_no_GET_without_dropping_request(self):
        with TemporaryDirectory() as directory, fixture(Path(directory).resolve(), reuse=True) as (plan, path):
            self.assertEqual(plan['requests'][0]['disposition'], 'reused_no_GET')
            result, opener, _clock = self.run_collection(plan, path)
            self.assertEqual(len(result['dispositions']), 3); self.assertEqual(result['GET_attempts'], 2)
            self.assertEqual(len(opener.calls), 2)
            self.assertEqual(result['dispositions'][0]['status'], 'reused_no_GET')

    def test_additional_daily_is_separate_and_never_invents_issuer_or_split_requests(self):
        with TemporaryDirectory() as directory, fixture(Path(directory).resolve(), daily=True, exhibits=True) as (plan, path):
            self.assertEqual(plan['original_unique_requests'], 3); self.assertEqual(plan['additional_unique_requests'], 3)
            self.assertEqual(len(plan['requests']), 6)
            result, opener, _clock = self.run_collection(plan, path)
            self.assertEqual(result['status'], 'completed'); self.assertEqual(len(opener.calls), 6)
            self.assertEqual([x['kind'] for x in result['dispositions'][-2:]], ['additional_exhibit', 'additional_exhibit'])
            last = result['dispositions'][3]
            self.assertEqual(collector.read_bound(last['native_cache'])['capability'], 'price_daily')
            self.assertEqual(last['kind'], 'additional_daily_origin')

    def test_plan_tamper_and_request_whitelist_reject_before_any_collection(self):
        with TemporaryDirectory() as directory, fixture(Path(directory).resolve()) as (plan, path):
            tampered = dict(plan); tampered['requests'] = [dict(row) for row in plan['requests']]
            tampered['requests'][0]['endpoint'] = 'https://external.invalid/model'
            tampered['plan_hash'] = collector.canonical_json_hash({k: v for k, v in tampered.items() if k != 'plan_hash'})
            save(path, tampered)
            with self.assertRaisesRegex(ValueError, 'whitelist'):
                self.run_collection(tampered, path)
            self.assertFalse(Path(plan['output']).exists())
