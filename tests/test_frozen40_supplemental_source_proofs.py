"""Offline small-list transport controls; origin reconstruction remains native."""
from datetime import datetime, timezone
import importlib.util
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from urllib.error import HTTPError

from stock_opportunity_agent.artifacts import canonical_json_hash

PATH = Path(__file__).resolve().parents[1] / 'scripts/collect_frozen40_supplemental_source_proofs.py'
spec = importlib.util.spec_from_file_location('supplemental_collector_test', PATH)
collector = importlib.util.module_from_spec(spec); spec.loader.exec_module(collector)


class Response:
    def __init__(self, url, raw):
        self.url, self.raw, self.status, self.headers = url, raw, 200, {}
    def read(self):
        return self.raw
    def geturl(self):
        return self.url
    def __enter__(self):
        return self
    def __exit__(self, *_args):
        pass


class SupplementalProofTests(TestCase):
    def fixture(self, root):
        expected = [
            {'purpose': 'historical_issuer', 'endpoint': 'https://api.massive.com/v3/reference/tickers/FTI',
                'query': {'date': '2025-05-29'}},
            {'purpose': 'all_type_splits', 'endpoint': 'https://api.massive.com/stocks/v1/splits',
                'query': {'ticker': 'FTI', 'execution_date.gte': '2025-05-30',
                    'execution_date.lte': '2026-10-20', 'sort': 'execution_date.asc', 'limit': '1000'}}]
        authority = root / 'authority.json'; authority.write_text(json.dumps({'parent_url': collector.HITI}))
        sec = root / 'sec.json'; sec.write_text(json.dumps({'requests': [
            {'endpoint': collector.HITI, 'authority': collector.shared.bound(authority)}]}))
        rows = [{'name': f'supplement-{i:03d}', 'source': 'massive', 'kind': r['purpose'],
            'endpoint': r['endpoint'], 'query': r['query'], 'associations': [r]}
            for i, r in enumerate(expected, 1)]
        rows.append({'name': 'supplement-003', 'source': 'sec_edgar', 'kind': 'supplemental_sec_body',
            'endpoint': collector.HITI, 'query': {}})
        plan = {'origin': {}, 'additional_sec': collector.shared.bound(sec), 'requests': rows,
            'output': str(root / 'collection'), 'max_GET_attempts': 3, 'automatic_retries': 0,
            'redirects_followed': 0, 'pagination_allowed': False, 'timeout_seconds': 30,
            'native_ledger_paths': [], 'prior_market_attempt_epochs': [], 'sec_user_agent': 'offline tests',
            'source_bindings': [collector.shared.bound(sec), collector.shared.bound(authority)],
            'code_bindings': [collector.shared.bound(PATH)]}
        plan['plan_hash'] = canonical_json_hash(plan)
        path = root / 'plan.json'; path.write_text(json.dumps(plan))
        return plan, path, expected

    def test_actual_managed_receipts_cache_and_permanent_reentry(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp).resolve(); plan, path, expected = self.fixture(root); opened = []
            class Opener:
                def open(self, request, timeout):
                    state = json.loads((root / 'collection/results.json').read_text())
                    assert state['attempt_reservations'] == len(opened) + 1
                    assert state['GET_attempts'] == len(opened) + 1
                    opened.append(request.full_url)
                    body = {'status': 'OK', 'results': [] if '/splits?' in request.full_url else {'ticker': 'FTI'}}
                    return Response(request.full_url, json.dumps(body).encode() if 'massive.com' in request.full_url else b'<html>parent body</html>')
            with patch.object(collector, 'origin_requests', return_value=expected):
                value = collector.collect(path, collector.shared.bound(path)['sha256'], opener=Opener(),
                    clock=lambda: datetime(2026, 10, 20, tzinfo=timezone.utc), credential_loader=lambda: 'offline-secret')
                self.assertEqual(value['GET_attempts'], 3)
                self.assertEqual(value['HTTP_responses_retained'], 3)
                self.assertEqual([r['status'] for r in value['dispositions']], ['received'] * 3)
                self.assertEqual(len(list((root / 'collection/cache').rglob('*.json'))), 3)
                with self.assertRaises(FileExistsError):
                    collector.collect(path, collector.shared.bound(path)['sha256'], opener=Opener())
            self.assertEqual(len(opened), 3)

    def test_market_host_failure_does_not_skip_sec_and_no_retry(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp).resolve(); plan, path, expected = self.fixture(root); opened = []
            class Opener:
                def open(self, request, timeout):
                    opened.append(request.full_url)
                    if 'massive.com' in request.full_url:
                        raise HTTPError(request.full_url, 429, 'rate limited', {}, io.BytesIO(b'limited'))
                    return Response(request.full_url, b'<html>real fake parent</html>')
            with patch.object(collector, 'origin_requests', return_value=expected):
                value = collector.collect(path, collector.shared.bound(path)['sha256'], opener=Opener(),
                    clock=lambda: datetime(2026, 10, 20, tzinfo=timezone.utc), credential_loader=lambda: 'offline-secret')
            self.assertEqual(len(opened), 2)
            self.assertEqual([r['status'] for r in value['dispositions']], ['failed_typed', 'blocked_by_host_failure', 'received'])
            self.assertTrue(value['terminal'])

    def test_rehashed_scope_and_typed_bound_changes_reject_before_open(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp).resolve(); plan, path, expected = self.fixture(root)
            for field, value in [('max_GET_attempts', True), ('timeout_seconds', 30.0)]:
                bad = {**plan, field: value}; bad['plan_hash'] = canonical_json_hash({k:v for k,v in bad.items() if k != 'plan_hash'})
                path.write_text(json.dumps(bad))
                with patch.object(collector, 'origin_requests', return_value=expected):
                    with self.assertRaises(ValueError):
                        collector.collect(path, collector.shared.bound(path)['sha256'])
                self.assertFalse((root / 'collection').exists())
            plan['requests'][2]['endpoint'] = collector.HITI.replace('20241031', '20251031')
            plan['plan_hash'] = canonical_json_hash({k:v for k,v in plan.items() if k != 'plan_hash'})
            path.write_text(json.dumps(plan))
            with patch.object(collector, 'origin_requests', return_value=expected):
                with self.assertRaises(ValueError):
                    collector.collect(path, collector.shared.bound(path)['sha256'])
