"""Collect one frozen exact proof batch; never normalize or admit Raw Info."""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import time
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.data.reviewed_snapshot import _complete_market_body, _daily_market_rows, _market_response
from stock_opportunity_agent.data.sources.catalog import DataCapability
from stock_opportunity_agent.data.sources.core import DataSourceError, FilingMetadata, decode_response_text
from stock_opportunity_agent.data.sources.sec_edgar import SecEdgarClient, _filings_from_arrays
from stock_opportunity_agent.data.sources.state import (
    DEFAULT_SOURCE_QUOTAS, ManagedHttpTransport, RawCacheKey, RawDataCache,
    RequestLedger, SourceBudget, SourceQuota,
)

REPO = Path(__file__).resolve().parents[3]
MISSING = REPO / 'runs/diagnostics/reviewed_frozen_source_snapshot_20261020_v1/stage/missing-proof-requests.json'
MISSING_SHA = '6c963ac258134d89c80e9ab12fce397203924f8a5e859542d7fa92ed43e9b286'
INVENTORY = REPO / 'runs/diagnostics/frozen40_source_completion_20261020_v1/local-cache-chain-inventory.json'
INVENTORY_SHA = '5bf5a7bbe1c86ef8ca58b7270695eb32b846f64ce306fedaf42f3ed88f1eeb9a'
OLD_PROOFS = REPO / 'runs/diagnostics/market_source_qualification_20261020_v1/proofs'
HEADERS_PLAN = REPO / 'runs/diagnostics/frozen40_source_completion_20261020_v1/companyfacts-fetch-v1/request-plan.json'
EXHIBITS_SHA = '9241e0a7922d26a46cc13c14eead68d1b618a65ce7bdf9e05785acedb046d615'
ADDITIONAL_SHA = '3510e405fada7759c50e83f96cfab89843c0140253292e37c8c68b57bd551fa9'
COUNTS = {'all_type_splits': 53, 'historical_issuer': 29, 'exact_static_primary_body': 10}
SPEC = REPO / 'spec/scripts/collect_frozen40_source_proofs.md'


def bound(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def read_bound(binding):
    raw = Path(binding['path']).read_bytes()
    if hashlib.sha256(raw).hexdigest() != binding['sha256']:
        raise ValueError('bound proof input changed')
    return json.loads(raw)


def write(path, value, *, initial=False):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    target = path if initial else path.with_name(path.name + '.pending')
    with target.open('x') as handle:
        json.dump(value, handle, sort_keys=True, indent=2); handle.write('\n')
        handle.flush(); os.fsync(handle.fileno())
    if not initial:
        os.replace(target, path)
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def nested_bindings(value):
    if isinstance(value, dict):
        if set(value) >= {'path', 'sha256'}:
            yield {'path': value['path'], 'sha256': value['sha256']}
        else:
            for child in value.values():
                yield from nested_bindings(child)
    elif isinstance(value, list):
        for child in value:
            yield from nested_bindings(child)


def check(bindings):
    for item in bindings:
        if bound(item['path']) != item:
            raise ValueError('frozen source/code changed')


def request_kind(row):
    kinds = {item['purpose'] for item in row['associations']}
    if len(kinds) != 1:
        raise ValueError('one request must have one consistent proof kind')
    return next(iter(kinds))


def validate_request(row):
    endpoint, query, kind = row['endpoint'], row['query'], request_kind(row)
    if not isinstance(query, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in query.items()):
        raise ValueError('request query requires exact strings')
    if kind == 'historical_issuer':
        if not re.fullmatch(r'https://api\.massive\.com/v3/reference/tickers/[A-Z0-9.-]+', endpoint) or set(query) != {'date'}:
            raise ValueError('issuer request outside exact whitelist')
        date.fromisoformat(query['date'])
    elif kind == 'all_type_splits':
        if (endpoint != 'https://api.massive.com/stocks/v1/splits'
                or set(query) != {'ticker', 'execution_date.gte', 'execution_date.lte', 'sort', 'limit'}
                or not re.fullmatch(r'[A-Z0-9.-]+', query['ticker'])
                or query['sort'] != 'execution_date.asc' or query['limit'] != '1000'
                or date.fromisoformat(query['execution_date.gte']) > date.fromisoformat(query['execution_date.lte'])):
            raise ValueError('split request outside exact whitelist')
    elif kind == 'exact_static_primary_body':
        if query or not re.fullmatch(r'https://www\.sec\.gov/Archives/edgar/data/[0-9]+/[0-9]{18}/[A-Za-z0-9][A-Za-z0-9._-]*', endpoint):
            raise ValueError('SEC primary URL outside exact whitelist')
    elif kind == 'additional_exhibit':
        if query or endpoint not in {
                'https://www.sec.gov/Archives/edgar/data/1847409/000162828025002990/hiti-annualinformationform.htm',
                'https://www.sec.gov/Archives/edgar/data/1847409/000162828025002990/hiti-exhibit992mda.htm'}:
            raise ValueError('additional exhibit differs from exact HITI links')
    elif kind == 'additional_daily_origin':
        if (not re.fullmatch(r'https://api\.massive\.com/v2/aggs/ticker/FTI/range/1/day/2024-04-25/2025-05-29', endpoint)
                or query != {'adjusted': 'true', 'limit': '50000', 'sort': 'asc'}):
            raise ValueError('additional daily request differs from exact FTI window')
    else:
        raise ValueError('unsupported proof request kind')
    return kind


def capability(row):
    return {'historical_issuer': DataCapability.COMPANY_PROFILE, 'all_type_splits': DataCapability.CORPORATE_ACTIONS,
        'additional_daily_origin': DataCapability.PRICE_DAILY, 'additional_exhibit': DataCapability.FILING_DOCUMENTS, 'exact_static_primary_body': DataCapability.FILING_DOCUMENTS}[request_kind(row)]


def _reuse(row, old_receipts):
    for item in old_receipts:
        if item['record']['endpoint'] == row['endpoint'] and item['record']['query'] == row['query']:
            proof = {'artifact': item['artifact'], 'request_record': item['request_record'], 'entry_name': item['record']['name']}
            _market_response(proof, row['endpoint'], row['query'])
            return item
    return None


def _filing(row):
    association = row['associations'][0]
    cik = association['case_id'].split(':')[0].removeprefix('cik_')
    for binding in association['root_bindings']:
        source = read_bound(binding)['body']
        matches = [item for item in _filings_from_arrays(cik, source['filings']['recent'], date.max)
            if item.source_url == row['endpoint'] and item.accession_number == association['accession_number']]
        if len(matches) == 1:
            item = matches[0]
            if item.form != association['form'] or item.accepted_at.isoformat() != association['accepted_at']:
                raise ValueError('literal SEC target metadata differs')
            return {key: getattr(item, key).isoformat() if isinstance(getattr(item, key), (date, datetime))
                else getattr(item, key) for key in ('cik', 'accession_number', 'filing_date', 'report_date', 'form',
                    'primary_document', 'source_url', 'retrieved_at', 'accepted_at')}
    raise ValueError('SEC primary lacks exact retained native root metadata')


class UsageLedger:
    """Read existing usage and append only to the new task-local native ledger."""
    def __init__(self, local, historical):
        self.local, self.historical = local, historical

    def entries(self, *, source_key=None):
        entries = [entry for path in self.historical for entry in RequestLedger(path).entries(source_key=source_key)]
        return entries + self.local.entries(source_key=source_key)

    def append(self, entry):
        self.local.append(entry)


def prepare(output, *, missing=MISSING, inventory=INVENTORY, additional_daily_origin=None, additional_exhibits=None):
    """Freeze exact requests, bounded cache findings and prior quota evidence only."""
    output = Path(output).resolve()
    if (output / 'request-plan.json').exists():
        raise ValueError('proof plan already exists')
    missing_binding, inventory_binding = bound(missing), bound(inventory)
    if missing_binding['sha256'] != MISSING_SHA or inventory_binding['sha256'] != INVENTORY_SHA:
        raise ValueError('fixed92 source authority differs')
    rows, inv = read_bound(missing_binding), read_bound(inventory_binding)
    counts = {kind: sum(request_kind(row) == kind for row in rows) for kind in COUNTS}
    if counts != COUNTS or len(rows) != sum(COUNTS.values()) or len({canonical_json_hash([r['endpoint'], r['query']]) for r in rows}) != len(rows):
        raise ValueError('fixed92 unique request denominator differs')
    for row in rows:
        validate_request(row)
    original_rows = json.loads(json.dumps(rows))
    sources = [missing_binding, inventory_binding, *nested_bindings(rows)]
    if additional_daily_origin is not None:
        extra_binding = bound(additional_daily_origin)
        if extra_binding['sha256'] != ADDITIONAL_SHA:
            raise ValueError('additional daily authority differs')
        extra = read_bound(extra_binding)
        row = {key: extra['request'][key] for key in ('endpoint', 'query')}
        row['associations'] = [{'purpose': 'additional_daily_origin', 'case': extra['case'], 'authority': extra_binding}]
        validate_request(row); rows.append(row); sources.extend([extra_binding, *nested_bindings(extra['inputs']), *nested_bindings(extra['definitions'])])
    if additional_exhibits is not None:
        exhibits_binding = bound(additional_exhibits)
        if exhibits_binding['sha256'] != EXHIBITS_SHA:
            raise ValueError('additional exhibits authority differs')
        exhibits = read_bound(exhibits_binding)
        if len(exhibits['requests']) != 2:
            raise ValueError('exactly two bound HITI exhibits required')
        for extra in exhibits['requests']:
            row = {key: extra[key] for key in ('endpoint', 'query')}
            row['associations'] = [{'purpose': 'additional_exhibit', 'authority': exhibits_binding, 'literal_parent': extra}]
            validate_request(row); rows.append(row)
            sources.extend(nested_bindings({key: extra[key] for key in ('parent_original', 'parent_root_proofs')}))
        sources.extend([exhibits_binding, *nested_bindings(exhibits['inputs'])])
    roots = sorted({str(Path(m['binding']['path']).parent.parent) for c in inv['cases'] for r in c['requests']
        if r['family'] == 'market_daily' for m in r['matches']})
    historical_paths = sorted({str(Path(root).parents[2] / name) for root in roots
        for name in ('data_requests.jsonl', 'request_ledger.jsonl') if (Path(root).parents[2] / name).is_file()})
    # The earlier proof collector recorded actual attempts outside the native ledger.
    old_attempts = OLD_PROOFS / 'attempts.json'
    previous_attempts = read_bound(bound(old_attempts)) if old_attempts.is_file() else []
    old_receipts_path = OLD_PROOFS / 'results.json'
    old_receipts = []
    if old_receipts_path.is_file():
        receipt_binding = bound(old_receipts_path); sources.append(receipt_binding)
        for item in read_bound(receipt_binding):
            artifact = bound(OLD_PROOFS / item['raw_response'])
            old_receipts.append({'record': item, 'artifact': artifact, 'request_record': receipt_binding})
    lookup, requests = [], []
    for index, row in enumerate(rows):
        kind = validate_request(row); source = 'sec_edgar' if kind in ('exact_static_primary_body', 'additional_exhibit') else 'massive'
        item = {'name': 'proof-' + str(index).zfill(3), 'source': source, 'kind': kind, **row, 'disposition': 'planned_GET'}
        if source == 'massive' and kind != 'additional_daily_origin':
            matches, keys = [], {}
            for cap in (DataCapability.COMPANY_PROFILE, DataCapability.CORPORATE_ACTIONS, DataCapability.PRICE_DAILY):
                key = RawCacheKey.from_request('massive', cap, 'GET', row['endpoint'] + '?' + urlencode(row['query']))
                keys[cap.value] = key.digest
                for root in roots:
                    path = Path(root) / cap.value / (key.digest + '.json')
                    if path.is_file():
                        matches.append(bound(path))
            reused = _reuse(row, old_receipts)
            if reused:
                item.update(disposition='reused_no_GET', reused=reused); sources.extend(nested_bindings(reused))
            elif matches:
                item.update(disposition='blocked_cache_without_http_receipt', cache_candidates=matches)
            sources.extend(matches)
            lookup.append({'name': item['name'], 'exact_keys': keys, 'matches': matches,
                'direct_paths_checked': len(roots) * len(keys), 'reused_HTTP_proof': reused is not None})
        if kind == 'exact_static_primary_body':
            item['filing'] = _filing(row)
        requests.append(item)
    headers_binding = bound(HEADERS_PLAN); sources.append(headers_binding)
    user_agent = read_bound(headers_binding)['request_headers']['User-Agent']
    sources.extend(bound(path) for path in historical_paths)
    if old_attempts.is_file():
        sources.append(bound(old_attempts))
    code_paths = [Path(__file__).resolve(), SPEC, *sorted((REPO / 'src').rglob('*.py')),
        REPO / 'scripts/run_minimal_rounds.py', REPO / 'spec/src/stock_opportunity_agent/data/sources.md',
        REPO / 'spec/src/stock_opportunity_agent/data/reviewed_snapshot.md',
        REPO / 'spec/src/stock_opportunity_agent/data/reviewed_market_profile.md',
        REPO / 'spec/src/stock_opportunity_agent/data/reviewed_sec_response_profile.md']
    unique_sources = {}
    for item in sources:
        if item['path'] in unique_sources and canonical_json_hash(item) != canonical_json_hash(unique_sources[item['path']]):
            raise ValueError('conflicting nested source binding')
        unique_sources[item['path']] = item
    check(list(unique_sources.values()))
    output.mkdir(parents=True, exist_ok=True)
    lookup_record = {'root_scope': roots, 'roots': len(roots), 'market_proof_requests': len(lookup),
        'direct_path_checks': sum(x['direct_paths_checked'] for x in lookup), 'requests': lookup,
        'no_filename_census': True, 'absence_is_limited_to_checked_exact_paths': True}
    write(output / 'exact-cache-lookup.json', lookup_record, initial=True)
    historical = UsageLedger(RequestLedger(output / 'collection/unused-ledger.jsonl'), historical_paths)
    now = datetime.now(timezone.utc)
    quotas = {**DEFAULT_SOURCE_QUOTAS, 'massive': SourceQuota('massive', per_minute_limit=5)}
    budget = SourceBudget(historical, quotas)
    quota_state = {source: {'native_currently_allowed': budget.check(source, now).allowed,
        'retained_native_network_entries': sum(e.status.value in {'fetched', 'error'} for e in historical.entries(source_key=source)),
        'latest_native_event': max((e.requested_at.isoformat() for e in historical.entries(source_key=source)), default=None)}
        for source in ('massive', 'sec_edgar')}
    write(output / 'quota-state.json', quota_state, initial=True)
    plan = {'request_source': missing_binding, 'original_requests': original_rows,
        'original_unique_requests': len(original_rows), 'original_association_count': sum(len(x['associations']) for x in original_rows),
        'additional_unique_requests': len(rows) - len(original_rows), 'requests': requests,
        'max_GET_attempts': len(rows), 'timeout_seconds': 30, 'automatic_retries': 0, 'redirects_followed': 0,
        'pagination_allowed': False, 'native_ledger_paths': historical_paths,
        'prior_market_attempt_epochs': [x['started_epoch'] for x in previous_attempts],
        'sec_user_agent_source': headers_binding, 'sec_user_agent': user_agent,
        'source_bindings': list(unique_sources.values()), 'code_bindings': [bound(path) for path in code_paths],
        'cache_lookup': bound(output / 'exact-cache-lookup.json'), 'quota_state': bound(output / 'quota-state.json'),
        'output': str(output / 'collection')}
    plan['plan_hash'] = canonical_json_hash(plan)
    write(output / 'request-plan.json', plan, initial=True)
    return plan


class NoRedirect(HTTPRedirectHandler):
    """Preserve redirect responses without opening a replacement URL."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def runtime_key():
    """Use the normal source launcher/environment without returning it to logs."""
    from run_minimal_rounds import _load_env
    _load_env()
    value = os.environ.get('MASSIVE_API_KEY', '').strip()
    if not value:
        raise DataSourceError('Massive credential unavailable')
    return value


def _pace(source, ledger, plan, clock, sleep):
    limit, seconds = (5, 60) if source == 'massive' else (10, 1)
    while True:
        now = clock()
        times = [e.requested_at.timestamp() for e in ledger.entries(source_key=source) if e.status.value in {'fetched', 'error'}]
        if source == 'massive':
            times += plan['prior_market_attempt_epochs']
        recent = sorted(t for t in times if now.timestamp() - seconds <= t <= now.timestamp())
        if len(recent) < limit:
            return
        wait = recent[-limit] + seconds + 0.02 - now.timestamp()
        sleep(min(5, max(0.01, wait)))


class ReceiptTransport:
    """Retain one actual response before native parsing/cache admission."""
    def __init__(self, row, output, result, opener, clock, secret):
        self.row, self.output, self.result = row, output, result
        self.opener, self.clock, self.secret = opener, clock, secret
        self.entry = None

    def _get(self, url, headers):
        row, result, output = self.row, self.result, self.output
        expected = row['endpoint'] + ('?' + urlencode(row['query']) if row['query'] else '')
        if url != expected:
            raise DataSourceError('native request differs from exact frozen URL')
        entry = {'name': row['name'], 'method': 'GET', 'url': expected, 'status': 'attempt_recorded_before_network',
            'started_at_utc': self.clock().isoformat(), 'headers_omitted': ['Authorization'] if self.secret else []}
        self.entry = entry
        result['requests'].append(entry)
        result['GET_attempts'] += 1
        if result['GET_attempts'] > result['max_GET_attempts']:
            raise DataSourceError('frozen GET ceiling reached')
        write(output / 'results.json', result)
        result['network_open_calls'] += 1
        entry['status'] = 'network_open_started'
        write(output / 'results.json', result)
        self.row['failure_stage'] = 'transport'
        try:
            try:
                response = self.opener.open(Request(url, headers=dict(headers), method='GET'), timeout=30)
            except HTTPError as error:
                response = error
            with response:
                raw, status, response_url = response.read(), response.status, response.geturl()
                response_headers = {key: value for key, value in response.headers.items()
                    if not any(term in key.lower() for term in ('auth', 'cookie', 'key', 'token', 'secret', 'password'))
                    and not (self.secret and self.secret in value)}
        except Exception as error:
            row['transport_error_type'] = type(error).__name__
            raise DataSourceError('transport failure: ' + type(error).__name__) from None
        encodings = [value for key, value in response_headers.items() if key.lower() == 'content-encoding']
        if len(encodings) > 1:
            row['failure_stage'] = 'decode'
            raise DataSourceError('ambiguous response encoding')
        # Decode before retaining raw bytes: compressed or escaped echoes must
        # never reach either decoded proof files or the native managed cache.
        row['failure_stage'] = 'decode'
        decoded = decode_response_text(raw, encodings[0] if encodings else None) if self.secret else None
        security_text = decoded or ''
        if self.secret:
            try:
                security_text += json.dumps(json.loads(decoded), ensure_ascii=False)
            except (ValueError, TypeError):
                pass
        if self.secret and (self.secret.encode() in raw or self.secret in security_text or self.secret in response_url):
            entry.update(status='credential_echo_not_retained', http_status=status, bytes_observed=len(raw))
            self.row['failure_stage'] = 'credential_echo'
            write(output / 'results.json', result)
            raise DataSourceError('credential echo rejected before response persistence')
        row['failure_stage'] = 'response_persistence'
        path = output / 'responses' / (row['name'] + '.response.raw')
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as handle:
            handle.write(raw); handle.flush(); os.fsync(handle.fileno())
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        retrieved = self.clock()
        entry.update(status='http_response_retained', http_status=status, response_url=response_url,
            retrieved_at_utc=retrieved.isoformat(), raw_response=str(path), raw_sha256=bound(path)['sha256'],
            bytes=len(raw), response_headers=response_headers)
        result['HTTP_responses_retained'] += 1
        write(output / 'results.json', result)
        if type(status) is not int or status != 200 or response_url != expected or retrieved < datetime.fromisoformat(entry['started_at_utc']):
            row['failure_stage'] = 'http_or_response_identity'
            raise DataSourceError('HTTP status/URL/clock rejected')
        return decoded if decoded is not None else decode_response_text(raw, encodings[0] if encodings else None)

    def get_json(self, url, headers):
        text = self._get(url, headers)
        self.row['failure_stage'] = 'json_parse'
        body = json.loads(text)
        self.row['failure_stage'] = 'provider_or_page_shape'
        _complete_market_body(body)
        if self.row['kind'] == 'historical_issuer' and not isinstance(body.get('results'), dict):
            raise DataSourceError('issuer response lacks object result')
        if self.row['kind'] == 'all_type_splits' and not isinstance(body.get('results'), list):
            raise DataSourceError('split response lacks list result')
        if self.row['kind'] == 'additional_daily_origin':
            _daily_market_rows(body, 'FTI', True, date(2024, 4, 25), date(2025, 5, 29))
        decoded = self.output / 'responses' / (self.row['name'] + '.response.json')
        with decoded.open('x') as handle:
            handle.write(text); handle.flush(); os.fsync(handle.fileno())
        self.entry['decoded_response'] = bound(decoded)
        return body

    def get_text(self, url, headers):
        return self._get(url, headers)


def _verify_plan(path, expected_sha):
    if bound(path)['sha256'] != expected_sha:
        raise ValueError('reviewed plan file hash differs')
    plan = read_bound(bound(path))
    if canonical_json_hash({k: v for k, v in plan.items() if k != 'plan_hash'}) != plan['plan_hash']:
        raise ValueError('plan canonical hash differs')
    if (plan['request_source']['sha256'] != MISSING_SHA or plan['original_unique_requests'] != sum(COUNTS.values())
            or type(plan['max_GET_attempts']) is not int or plan['max_GET_attempts'] != len(plan['requests'])
            or len(plan['requests']) != sum(COUNTS.values()) + plan['additional_unique_requests']
            or type(plan['additional_unique_requests']) is not int or plan['additional_unique_requests'] not in (0, 1, 2, 3)
            or type(plan['automatic_retries']) is not int or plan['automatic_retries'] != 0
            or type(plan['redirects_followed']) is not int or plan['redirects_followed'] != 0
            or plan['pagination_allowed'] is not False or type(plan['timeout_seconds']) is not int or plan['timeout_seconds'] != 30):
        raise ValueError('frozen proof count or transport bounds differ')
    original = read_bound(plan['request_source'])
    if canonical_json_hash(original) != canonical_json_hash(plan['original_requests']):
        raise ValueError('original request associations differ')
    expected = plan['original_requests']
    for index, row in enumerate(plan['requests']):
        validate_request(row)
        if index < len(expected) and canonical_json_hash({key: row[key] for key in ('endpoint', 'query', 'associations')}) != canonical_json_hash(expected[index]):
            raise ValueError('original request row changed')
    check([*plan['source_bindings'], *plan['code_bindings'], plan['cache_lookup'], plan['quota_state']])
    return plan


def collect(plan_path, expected_plan_sha, *, opener=None, clock=None, sleep=time.sleep, credential_loader=runtime_key):
    """Execute one frozen batch; any start or partial completion forbids reentry."""
    plan = _verify_plan(Path(plan_path), expected_plan_sha)
    output = Path(plan['output'])
    if output.exists():
        raise ValueError('partial/completed proof collection cannot reenter')
    output.mkdir(parents=True)
    write(output / 'execution-start.json', {'plan_hash': plan['plan_hash'], 'started_at_utc': datetime.now(timezone.utc).isoformat()}, initial=True)
    result = {'plan_hash': plan['plan_hash'], 'terminal': False, 'status': 'started',
        'max_GET_attempts': plan['max_GET_attempts'], 'GET_attempts': 0, 'network_open_calls': 0,
        'HTTP_responses_retained': 0, 'attempt_reservations': 0, 'automatic_retries': 0,
        'redirects_followed': 0, 'requests': [], 'dispositions': [], 'market_request_record': None,
        'global_appends': 0, 'models': 0, 'labels_loaded': False, 'source_admission': False}
    write(output / 'results.json', result, initial=True)
    clock = clock or (lambda: datetime.now(timezone.utc))
    opener = opener or build_opener(NoRedirect())
    local = RequestLedger(output / 'native-ledger.jsonl')
    ledger = UsageLedger(local, plan['native_ledger_paths'])
    budget = SourceBudget(ledger, {**DEFAULT_SOURCE_QUOTAS, 'massive': SourceQuota('massive', per_minute_limit=5)})
    cache, blocked, records = RawDataCache(output / 'cache/data'), {}, []
    secret = None
    try:
        for frozen_row in plan['requests']:
            row = dict(frozen_row)
            source = row['source']
            disposition = {'name': row['name'], 'source': source, 'kind': row['kind'], 'status': row['disposition']}
            result['dispositions'].append(disposition)
            if source in blocked:
                disposition.update(status='blocked_by_host_failure', failure=blocked[source]); continue
            if row['disposition'] == 'reused_no_GET':
                disposition['reused'] = row['reused']; continue
            if row['disposition'] != 'planned_GET':
                continue
            try:
                if source == 'massive' and secret is None:
                    row['failure_stage'] = 'credential_unavailable'; secret = credential_loader()
                _pace(source, ledger, plan, clock, sleep)
                result['attempt_reservations'] += 1
                disposition.update(status='native_attempt_reserved', reserved_at_utc=clock().isoformat())
                write(output / 'results.json', result)
                inner = ReceiptTransport(row, output, result, opener, clock, secret if source == 'massive' else None)
                managed = ManagedHttpTransport(source, capability(row), inner, cache, ledger, budget, clock=clock)
                url = row['endpoint'] + ('?' + urlencode(row['query']) if row['query'] else '')
                if row['kind'] == 'additional_exhibit':
                    body = managed.get_text(url, {'User-Agent': plan['sec_user_agent'], 'Accept-Encoding': 'gzip, deflate'})
                elif source == 'sec_edgar':
                    data = dict(row['filing'])
                    for key in ('filing_date', 'report_date'):
                        data[key] = date.fromisoformat(data[key]) if data[key] else None
                    for key in ('accepted_at', 'retrieved_at'):
                        data[key] = datetime.fromisoformat(data[key]) if data[key] else None
                    body = SecEdgarClient(plan['sec_user_agent'], transport=managed).filing_document_text(FilingMetadata(**data))
                else:
                    body = managed.get_json(url, {'Authorization': 'Bearer ' + secret, 'Accept-Encoding': 'identity'})
                    entry = inner.entry
                    artifact = entry['decoded_response']
                    record = {'name': row['name'], 'endpoint': row['endpoint'], 'query': row['query'],
                        'http_status': entry['http_status'], 'provider_status': body['status'], 'next_page_present': False,
                        'retrieved_at': entry['retrieved_at_utc'],
                        'raw_response': str(Path(artifact['path']).relative_to(output)), 'sha256': artifact['sha256'],
                        'raw_HTTP_response': {'path': entry['raw_response'], 'sha256': entry['raw_sha256']}}
                    records.append(record)
                    write(output / 'market-request-records.json', records)
                key = RawCacheKey.from_request(source, capability(row), 'GET', url)
                native_binding = bound(output / 'cache/data' / source / capability(row).value / (key.digest + '.json'))
                cached = cache.get(key)
                if canonical_json_hash(cached.body) != canonical_json_hash(body):
                    raise DataSourceError('native cache body differs from actual response')
                disposition.update(status='received_unsupported_nonempty_split_ledger' if row['kind'] == 'all_type_splits' and body['results'] else 'received',
                    native_cache=native_binding, cache_retrieved_at=cached.retrieved_at.isoformat())
                print(json.dumps({'name': row['name'], 'source': source, 'status': disposition['status'],
                    'actual_GET_attempts': result['GET_attempts']}), flush=True)
            except Exception as error:
                stage = row.get('failure_stage', 'native_quota_or_cache')
                disposition.update(status='failed_typed', error_type=type(error).__name__, failure_stage=stage)
                if 'transport_error_type' in row:
                    disposition['transport_error_type'] = row['transport_error_type']
                blocked[source] = {'error_type': type(error).__name__, 'failure_stage': stage, 'request': row['name']}
                print(json.dumps({'name': row['name'], 'source': source, 'status': 'failed_typed',
                    'error_type': type(error).__name__, 'failure_stage': stage}), flush=True)
            write(output / 'results.json', result)
        check([*plan['source_bindings'], *plan['code_bindings']])
        result.update(terminal=True, status='completed_with_host_failures' if blocked else 'completed',
            finished_at_utc=clock().isoformat(), native_ledger=bound(local.path) if local.path.exists() else None,
            market_request_record=bound(output / 'market-request-records.json') if records else None,
            all_frozen_bindings_unchanged=True)
        write(output / 'results.json', result)
        return result
    except Exception as error:
        result.update(terminal=True, status='failed_terminal', failure_type=type(error).__name__)
        write(output / 'results.json', result)
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--expected-plan-sha')
    parser.add_argument('--additional-daily-origin', type=Path)
    parser.add_argument('--additional-exhibits', type=Path)
    args = parser.parse_args()
    if args.prepare == args.execute:
        parser.error('choose exactly one prepare or execute')
    if args.prepare:
        value = prepare(args.output, additional_daily_origin=args.additional_daily_origin, additional_exhibits=args.additional_exhibits)
        print(json.dumps({'plan_hash': value['plan_hash'], 'requests': len(value['requests']), 'max_GET_attempts': value['max_GET_attempts']}))
    else:
        if args.plan is None or args.expected_plan_sha is None:
            parser.error('execute requires exact plan and expected plan SHA')
        value = collect(args.plan, args.expected_plan_sha)
        print(json.dumps({'status': value['status'], 'GET_attempts': value['GET_attempts']}))
