"""Collect separately frozen FTI proofs and an explicit small SEC body list."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import time
from urllib.parse import urlencode
from urllib.request import build_opener

from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.data.sources.catalog import DataCapability
from stock_opportunity_agent.data.sources.core import DataSourceError
from stock_opportunity_agent.data.sources.state import (
    DEFAULT_SOURCE_QUOTAS, ManagedHttpTransport, RawCacheKey, RawDataCache,
    RequestLedger, SourceBudget, SourceQuota,
)
import diagnose_reviewed_frozen_source_snapshot as origin_driver

REPO = Path(__file__).resolve().parents[1]
BASE = REPO / 'runs/diagnostics/frozen40_source_proofs_20261020_v1'
COLLECTOR = BASE / 'collector.py'
SPEC = REPO / 'spec/scripts/collect_frozen40_supplemental_source_proofs.md'
HITI = 'https://www.sec.gov/Archives/edgar/data/1847409/000162828025002990/hiti-20241031.htm'
module_spec = importlib.util.spec_from_file_location('frozen95_receipt_transport', COLLECTOR)
shared = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(shared)


def origin_requests(origin):
    """Derive the two exact requests only from native complete reconstruction."""
    record = shared.read_bound(origin['original_record'])
    if (record['metadata'].get('symbol') != 'FTI' or record['metadata'].get('start') != '2024-04-25'
            or record['metadata'].get('end') != '2025-05-29'):
        raise ValueError('supplement requires the exact approved FTI daily window')
    cache = shared.read_bound(origin['cache'])
    _details, requests = origin_driver._market_origin(origin['case'], {'endpoint': cache['endpoint']},
        {'binding': origin['cache']}, {'original_record': origin['original_record']})
    return requests


def sec_requests(path):
    """Read an explicit bounded static-SEC list with individual authority bindings."""
    value = shared.read_bound(shared.bound(path))
    rows = value["requests"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= 8:
        raise ValueError("supplement requires one to eight explicit SEC URLs")
    endpoints = []
    for row in rows:
        authority = shared.read_bound(row["authority"])
        def contains_endpoint(value):
            if isinstance(value, dict):
                return any(contains_endpoint(child) for child in value.values())
            if isinstance(value, list):
                return any(contains_endpoint(child) for child in value)
            return value == row["endpoint"]
        if not contains_endpoint(authority):
            raise ValueError("exact SEC URL absent from bound literal authority")
        shared.validate_request({"endpoint": row["endpoint"], "query": {},
            "associations": [{"purpose": "exact_static_primary_body"}]})
        endpoints.append(row["endpoint"])
    if len(set(endpoints)) != len(endpoints):
        raise ValueError("duplicate supplemental SEC URL")
    return rows


def prepare(output, *, origin_path, completed_plan_path, completed_result_path, additional_sec_path):
    """Freeze derived FTI proofs and an explicit reviewed small SEC request list."""
    plan95 = shared.read_bound(shared.bound(completed_plan_path))
    result95 = shared.read_bound(shared.bound(completed_result_path))
    if result95.get('terminal') is not True or result95.get('plan_hash') != plan95.get('plan_hash'):
        raise ValueError('actual95 collection must be terminal and bound to its plan')
    origin = shared.read_bound(shared.bound(origin_path))
    daily = [row for row in plan95['requests'] if row['kind'] == 'additional_daily_origin']
    dispositions = [row for row in result95['dispositions'] if daily and row['name'] == daily[0]['name']]
    if (len(daily) != 1 or len(dispositions) != 1 or dispositions[0]['status'] != 'received'
            or canonical_json_hash(dispositions[0]['native_cache']) != canonical_json_hash(origin['cache'])):
        raise ValueError('FTI origin is not the actual completed95 daily cache')
    sec_rows = sec_requests(additional_sec_path)
    rows = []
    for index, request in enumerate(origin_requests(origin), 1):
        rows.append({'name': f'supplement-{index:03d}', 'endpoint': request['endpoint'], 'query': request['query'],
            'kind': request['purpose'], 'source': 'massive', 'associations': [request]})
    for index, row in enumerate(sec_rows, 3):
        rows.append({'name': f'supplement-{index:03d}', 'endpoint': row['endpoint'], 'query': {},
            'kind': 'supplemental_sec_body', 'source': 'sec_edgar'})
    historical = [*plan95['native_ledger_paths'], result95['native_ledger']['path']]
    prior = [*plan95['prior_market_attempt_epochs'], *[datetime.fromisoformat(row['started_at_utc']).timestamp()
        for row in result95['requests'] if row['url'].startswith('https://api.massive.com/')]]
    sources = [shared.bound(origin_path), shared.bound(completed_plan_path), shared.bound(completed_result_path),
        shared.bound(additional_sec_path), *[row['authority'] for row in sec_rows], *shared.nested_bindings(origin), *plan95['source_bindings'],
        result95['native_ledger'], *shared.nested_bindings(result95)]
    for row in sec_rows:
        sources.extend(shared.nested_bindings(shared.read_bound(row['authority'])))
    for entry in result95['requests']:
        raw_binding = shared.bound(entry['raw_response'])
        if raw_binding['sha256'] != entry['raw_sha256']:
            raise ValueError('actual95 raw response changed')
        sources.append(raw_binding)
    codes = [shared.bound(__file__), shared.bound(SPEC), shared.bound(COLLECTOR),
        shared.bound(origin_driver.__file__), *plan95['code_bindings']]
    shared.check([*sources, *codes])
    plan = {'requests': rows, 'origin': origin, 'source_bindings': sources, 'code_bindings': codes,
        'additional_sec': shared.bound(additional_sec_path),
        'output': str((Path(output).resolve() / 'collection')), 'max_GET_attempts': len(rows),
        'automatic_retries': 0, 'redirects_followed': 0, 'pagination_allowed': False, 'timeout_seconds': 30,
        'sec_user_agent': plan95['sec_user_agent'], 'native_ledger_paths': historical,
        'prior_market_attempt_epochs': prior}
    plan['plan_hash'] = canonical_json_hash(plan)
    destination = Path(output).resolve()
    destination.mkdir(parents=True, exist_ok=False)
    shared.write(destination / 'request-plan.json', plan, initial=True)
    return plan


def verify_plan(path, expected_sha):
    """Verify this exact small-list contract without invoking the old95 verifier."""
    if shared.bound(path)['sha256'] != expected_sha:
        raise ValueError('supplement plan file differs')
    plan = shared.read_bound(shared.bound(path))
    if canonical_json_hash({k: v for k, v in plan.items() if k != 'plan_hash'}) != plan['plan_hash']:
        raise ValueError('supplement canonical plan differs')
    if (any(type(plan[k]) is not int or plan[k] != value for k, value in
            [('automatic_retries', 0), ('redirects_followed', 0), ('timeout_seconds', 30)])
            or type(plan['max_GET_attempts']) is not int or plan['max_GET_attempts'] != len(plan['requests'])
            or not 3 <= len(plan['requests']) <= 10 or plan['pagination_allowed'] is not False):
        raise ValueError('supplement transport bounds differ')
    expected = origin_requests(plan['origin'])
    for index, (row, request) in enumerate(zip(plan['requests'][:2], expected, strict=True), 1):
        if (row['name'] != f'supplement-{index:03d}' or row['source'] != 'massive'
                or row['kind'] != request['purpose'] or row['endpoint'] != request['endpoint']
                or canonical_json_hash(row['query']) != canonical_json_hash(request['query'])):
            raise ValueError('derived FTI proof request differs')
        shared.validate_request(row)
    sec_rows = sec_requests(plan['additional_sec']['path'])
    if len(sec_rows) != len(plan['requests']) - 2:
        raise ValueError('explicit SEC request count differs')
    for index, (row, authority) in enumerate(zip(plan['requests'][2:], sec_rows, strict=True), 3):
        if row != {'name': f'supplement-{index:03d}', 'endpoint': authority['endpoint'], 'query': {},
                'kind': 'supplemental_sec_body', 'source': 'sec_edgar'}:
            raise ValueError('explicit SEC request differs')
    shared.check([*plan['source_bindings'], *plan['code_bindings']])
    return plan


def collect(plan_path, expected_sha, *, opener=None, clock=None, sleep=time.sleep, credential_loader=shared.runtime_key):
    """Make only frozen first attempts; any execution start forbids reentry."""
    plan = verify_plan(Path(plan_path), expected_sha)
    output = Path(plan['output'])
    output.mkdir(parents=True, exist_ok=False)
    shared.write(output / 'execution-start.json', {'plan_hash': plan['plan_hash'],
        'started_at_utc': datetime.now(timezone.utc).isoformat()}, initial=True)
    result = {'plan_hash': plan['plan_hash'], 'terminal': False, 'status': 'started', 'max_GET_attempts': plan['max_GET_attempts'],
        'GET_attempts': 0, 'network_open_calls': 0, 'HTTP_responses_retained': 0, 'attempt_reservations': 0,
        'automatic_retries': 0, 'redirects_followed': 0, 'requests': [], 'dispositions': [],
        'global_appends': 0, 'models': 0, 'labels_loaded': False, 'source_admission': False}
    shared.write(output / 'results.json', result, initial=True)
    clock = clock or (lambda: datetime.now(timezone.utc))
    opener = opener or build_opener(shared.NoRedirect())
    local = RequestLedger(output / 'native-ledger.jsonl')
    ledger = shared.UsageLedger(local, plan['native_ledger_paths'])
    budget = SourceBudget(ledger, {**DEFAULT_SOURCE_QUOTAS, 'massive': SourceQuota('massive', per_minute_limit=5)})
    cache, blocked, records, secret = RawDataCache(output / 'cache/data'), {}, [], None
    try:
        for frozen_row in plan['requests']:
            row = dict(frozen_row); source = row['source']
            disposition = {'name': row['name'], 'source': source, 'kind': row['kind'], 'status': 'planned_GET'}
            result['dispositions'].append(disposition)
            if source in blocked:
                disposition.update(status='blocked_by_host_failure', failure=blocked[source]); continue
            try:
                if source == 'massive' and secret is None:
                    row['failure_stage'] = 'credential_unavailable'; secret = credential_loader()
                shared._pace(source, ledger, plan, clock, sleep)
                result['attempt_reservations'] += 1
                disposition.update(status='native_attempt_reserved', reserved_at_utc=clock().isoformat())
                shared.write(output / 'results.json', result)
                inner = shared.ReceiptTransport(row, output, result, opener, clock, secret if source == 'massive' else None)
                capability = shared.capability(row) if source == 'massive' else DataCapability.FILING_DOCUMENTS
                managed = ManagedHttpTransport(source, capability, inner, cache, ledger, budget, clock=clock)
                url = row['endpoint'] + ('?' + urlencode(row['query']) if row['query'] else '')
                if source == 'sec_edgar':
                    body = managed.get_text(url, {'User-Agent': plan['sec_user_agent'], 'Accept-Encoding': 'gzip, deflate'})
                else:
                    body = managed.get_json(url, {'Authorization': 'Bearer ' + secret, 'Accept-Encoding': 'identity'})
                    entry, artifact = inner.entry, inner.entry['decoded_response']
                    records.append({'name': row['name'], 'endpoint': row['endpoint'], 'query': row['query'],
                        'http_status': entry['http_status'], 'provider_status': body['status'], 'next_page_present': False,
                        'retrieved_at': entry['retrieved_at_utc'], 'raw_response': str(Path(artifact['path']).relative_to(output)),
                        'sha256': artifact['sha256'], 'raw_HTTP_response': {'path': entry['raw_response'], 'sha256': entry['raw_sha256']}})
                    shared.write(output / 'market-request-records.json', records)
                key = RawCacheKey.from_request(source, capability, 'GET', url)
                cached = cache.get(key)
                if canonical_json_hash(cached.body) != canonical_json_hash(body):
                    raise DataSourceError('native cache body differs')
                disposition.update(status='received_unsupported_nonempty_split_ledger'
                    if row['kind'] == 'all_type_splits' and body['results'] else 'received',
                    native_cache=shared.bound(output / 'cache/data' / source / capability.value / (key.digest + '.json')),
                    cache_retrieved_at=cached.retrieved_at.isoformat())
            except Exception as error:
                disposition.update(status='failed_typed', error_type=type(error).__name__,
                    failure_stage=row.get('failure_stage', 'native_quota_or_cache'))
                blocked[source] = {'request': row['name'], 'error_type': type(error).__name__}
            shared.write(output / 'results.json', result)
        shared.check([*plan['source_bindings'], *plan['code_bindings']])
        result.update(terminal=True, status='completed_with_host_failures' if blocked else 'completed',
            finished_at_utc=clock().isoformat(), native_ledger=shared.bound(local.path) if local.path.exists() else None,
            market_request_record=shared.bound(output / 'market-request-records.json') if records else None,
            all_frozen_bindings_unchanged=True)
        shared.write(output / 'results.json', result)
        return result
    except Exception as error:
        result.update(terminal=True, status='failed_terminal', failure_type=type(error).__name__)
        shared.write(output / 'results.json', result)
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', action='store_true'); parser.add_argument('--execute', action='store_true')
    parser.add_argument('--output', type=Path); parser.add_argument('--origin', type=Path)
    parser.add_argument('--completed-plan', type=Path); parser.add_argument('--completed-result', type=Path)
    parser.add_argument('--additional-sec', type=Path); parser.add_argument('--plan', type=Path)
    parser.add_argument('--expected-plan-sha')
    args = parser.parse_args()
    if args.prepare == args.execute:
        parser.error('choose exactly one prepare or execute')
    if args.prepare:
        prepare(args.output, origin_path=args.origin, completed_plan_path=args.completed_plan,
            completed_result_path=args.completed_result, additional_sec_path=args.additional_sec)
    else:
        collect(args.plan, args.expected_plan_sha)
