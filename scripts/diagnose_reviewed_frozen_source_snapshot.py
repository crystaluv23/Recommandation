"""Prepare fixed40 source candidates without acquisition, append or research execution."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote

import diagnose_reviewed_anchor_financial_snapshot as financial
import diagnose_reviewed_frozen_case_inputs as frozen
from stock_opportunity_agent.artifacts import atomic_write_json, canonical_json_hash
from stock_opportunity_agent.data.acquisition import HistoricalPriceAdapter
from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.data.resolution import RawInfoRequest
from stock_opportunity_agent.data.reviewed_snapshot import (
    ReviewedSourceRejected, _daily_market_rows, _read_bound,
    _verify_companyfacts_document, _verify_sec_document,
)
from stock_opportunity_agent.data.sources.massive import _price_bar_from_result
from stock_opportunity_agent.data.sources.core import decode_response_text
from stock_opportunity_agent.signal_library import SignalExecutor

REPO = Path(__file__).resolve().parents[1]
DEFAULT_PROJECTION = REPO / 'runs/diagnostics/reviewed_frozen_case_inputs_20261020_v1/stage/case-identities.json'
DEFAULT_BASE = REPO / 'runs/diagnostics/reviewed_periodic_operating_snapshot_20261020_v1/stage/input_manifest.json'
DEFAULT_INVENTORY = REPO / 'runs/diagnostics/frozen40_source_completion_20261020_v1/local-cache-chain-inventory.json'
DEFAULT_OPERATING = REPO / 'runs/diagnostics/frozen40_source_completion_20261020_v1/operating-target-candidates.json'
COHORT_PLAN_SHA = '20ee4d2f386a237fbeacfedfbe32dbd0406310166cb5f7b4f48014e391645696'
DEFAULT_OUTPUT = REPO / 'runs/diagnostics/reviewed_frozen_source_snapshot_20261020_v1/stage'
FIXED_SHA = {
    'projection': '3ecbd01349c00bbbba554b06bee2824ef08db162affbac0122c62558e90d02e9',
    'base': '535ba9007c6b31a1b257126ce50d377536393e6df04d71ee0d751320db424f25',
    'operating': '53be103294e060b90fa5b80fa7d47ab9b4e997432ca9f4c1e8661d7feb0134b0',
    'inventory': '5bf5a7bbe1c86ef8ca58b7270695eb32b846f64ce306fedaf42f3ed88f1eeb9a',
}


@contextmanager
def _prepare_only():
    def forbidden(*_args, **_kwargs):
        raise ReviewedSourceRejected('global store/append/prepare_inputs forbidden during source preparation')
    with frozen._source_only(), patch.object(RawInfoStore, '__init__', forbidden), \
            patch.object(RawInfoStore, 'append', forbidden), \
            patch.object(SignalExecutor, 'prepare_inputs', forbidden):
        yield


def _bindings(values):
    result = {}
    for value in values:
        path = str(Path(value['path']).resolve())
        if path in result and result[path]['sha256'] != value['sha256']:
            raise ReviewedSourceRejected('conflicting source binding: ' + path)
        result[path] = {'path': path, 'sha256': value['sha256']}
    return [result[path] for path in sorted(result)]


def _check(values):
    for value in values:
        if frozen._stream_binding(value['path']) != value:
            raise ReviewedSourceRejected('bound source changed: ' + value['path'])


def _bound_json(path):
    binding = frozen._stream_binding(path)
    return binding, _read_bound(binding)[1]


def _collision(document, oracle_root):
    matches = []
    for namespace in sorted(Path(oracle_root).iterdir()):
        if not namespace.is_dir():
            continue
        path = namespace / document.company_id / (document.document_id + '.json')
        if path.is_file():
            binding, record = _bound_json(path)
            matches.append({'original_record': binding,
                'canonical_equal': canonical_json_hash(record) == canonical_json_hash(document.to_dict())})
    return {'document_id': document.document_id, 'matches': matches,
        'collision': any(not match['canonical_equal'] for match in matches)}


def _additional(path, companies):
    if path is None:
        return [], []
    binding, rows = _bound_json(path)
    if not isinstance(rows, list):
        raise ReviewedSourceRejected('additional Company Facts must be an explicit table')
    seen, sources = set(), [binding]
    for row in rows:
        if (not isinstance(row, dict) or set(row) != {'company_id', 'cache', 'rawproof', 'receipt'}
                or row['company_id'] not in companies or row['company_id'] in seen):
            raise ReviewedSourceRejected('additional Company Facts identity or fields differ')
        seen.add(row['company_id'])
        values = {}
        for key in ('cache', 'rawproof', 'receipt'):
            if (not isinstance(row[key], dict) or set(row[key]) != {'path', 'sha256'}
                    or any(not isinstance(row[key][field], str) for field in ('path', 'sha256'))):
                raise ReviewedSourceRejected('additional Company Facts binding requires path/SHA strings')
            values[key] = _read_bound(row[key])[1]
            sources.append(row[key])
        receipt = values['receipt']
        endpoint = 'https://data.sec.gov/api/xbrl/companyfacts/CIK' + row['company_id'].removeprefix('cik_') + '.json'
        requests = receipt.get('requests', [])
        if (receipt.get('status') != 'successful' or receipt.get('terminal') is not True
                or any(type(receipt.get(key)) is not int or receipt[key] != 1
                    for key in ('GET_attempts', 'network_open_calls', 'HTTP_responses_retained', 'attempt_reservations'))
                or any(type(receipt.get(key)) is not int or receipt[key] != 0
                    for key in ('automatic_retries', 'redirects_followed'))
                or canonical_json_hash(receipt.get('native_cache')) != canonical_json_hash(row['cache'])
                or canonical_json_hash(receipt.get('raw_response_proof')) != canonical_json_hash(row['rawproof'])
                or not isinstance(requests, list) or len(requests) != 1 or not isinstance(requests[0], dict)
                or requests[0].get('method') != 'GET' or requests[0].get('status') != 'http_response_retained'
                or type(requests[0].get('http_status')) is not int or requests[0]['http_status'] != 200
                or requests[0].get('url') != endpoint or requests[0].get('response_url') != endpoint):
            raise ReviewedSourceRejected('additional Company Facts receipt does not bind successful exact origin')
        request = requests[0]
        response_binding = {'path': request['raw_response'], 'sha256': request['raw_sha256']}
        _check([response_binding])
        raw_bytes = Path(response_binding['path']).read_bytes()
        encodings = [value for key, value in request['response_headers'].items() if key.lower() == 'content-encoding']
        if len(encodings) > 1 or type(request.get('bytes')) is not int or len(raw_bytes) != request['bytes']:
            raise ReviewedSourceRejected('additional Company Facts response bytes/encoding differ')
        body = json.loads(decode_response_text(raw_bytes, encodings[0] if encodings else None))
        if canonical_json_hash(body) != canonical_json_hash(values['cache']['body']):
            raise ReviewedSourceRejected('additional Company Facts receipt response differs from native cache')
        sources.append(response_binding)
    return rows, sources


def _companyfacts_pairs(case, additions):
    pairs = [(match['binding'], comparison['original_record'])
        for request in case['requests'] if request['family'] == 'companyfacts'
        for match in request['matches'] for comparison in match.get('whole_raw_comparisons', [])]
    pairs.extend((row['cache'], row['rawproof']) for row in additions if row['company_id'] == case['company_id'])
    return pairs


def _choose_companyfacts(case, additions):
    audits, valid, raw_ids = [], [], {}
    for cache_binding, raw_binding in _companyfacts_pairs(case, additions):
        audit = {'cache': cache_binding, 'rawproof': raw_binding}
        audits.append(audit)
        try:
            cache, record = _read_bound(cache_binding)[1], _read_bound(raw_binding)[1]
            raw = RawInfoDocument.from_dict(record)
            previous = raw_ids.setdefault(raw.document_id, canonical_json_hash(record))
            if previous != canonical_json_hash(record):
                raise ReviewedSourceRejected('same raw proof ID has conflicting complete records')
            body = json.dumps(cache['body'], sort_keys=True, separators=(',', ':'), ensure_ascii=False)
            expected_id = 'sec_edgar:' + case['company_id'] + ':sec_company_facts_raw_response:' + hashlib.sha256(body.encode()).hexdigest()[:24]
            endpoint = 'https://data.sec.gov/api/xbrl/companyfacts/CIK' + case['company_id'].removeprefix('cik_') + '.json'
            if (cache['endpoint'] != endpoint or cache['params'] != [['method', 'GET']]
                    or cache['source_key'] != 'sec_edgar' or cache['capability'] != 'financial_statements'
                    or cache['payload_kind'] != 'json' or raw.document_id != expected_id
                    or raw.company_id != case['company_id'] or raw.source_type != 'sec_company_facts_raw_response'
                    or raw.content != body or raw.published_at != raw.available_at
                    or raw.metadata.get('provider') != 'sec_edgar'
                    or raw.metadata.get('cik') != case['company_id'].removeprefix('cik_')
                    or frozen._aware(cache['retrieved_at']) > raw.available_at):
                raise ReviewedSourceRejected('Company Facts request/body/identity/cache-to-raw clock differs')
            audit.update(status='usable_pair', body_hash=canonical_json_hash(cache['body']),
                cache_retrieved_at=cache['retrieved_at'], raw_normalized_at=raw.available_at.isoformat())
            valid.append((frozen._aware(cache['retrieved_at']), cache_binding['path'], raw_binding['path'], audit))
        except Exception as error:
            audit.update(status='rejected_pair', error_type=type(error).__name__, error=str(error))
    bodies = {item[3]['body_hash'] for item in valid}
    conflicting = any('conflicting complete records' in item.get('error', '') for item in audits)
    if conflicting or len(bodies) > 1:
        return None, audits, 'ambiguous_source_variants'
    if not valid:
        return None, audits, 'needs_acquisition' if not audits else 'unknown_no_usable_pair'
    # Retain every association; choose a reproducible proof pair only within one body.
    latest = max(item[0] for item in valid)
    selected = min((item for item in valid if item[0] == latest), key=lambda item: (item[1], item[2]))[3]
    return selected, audits, 'selected'


def _financial(case, additions, output, oracle_root):
    selected, audits, status = _choose_companyfacts(case, additions)
    result = {'case_id': case['case_id'], 'company_id': case['company_id'], 'status': status,
        'all_request_associations': [row for row in case['requests'] if row['family'] == 'companyfacts'],
        'pair_audit': audits, 'products': []}
    atomic_write_json(output / 'companyfacts-selection.json', result)
    if selected is None:
        return result
    products, normalization, stats = financial._derive({**case, 'cutoff': case['prediction_time'],
        'exact_cache': {'binding': selected['cache']}, 'original_raw_proof': {'binding': selected['rawproof']}})
    normalization_path = output / 'normalization.json'
    atomic_write_json(normalization_path, normalization)
    proofs = [{'kind': 'sec_companyfacts_cache', 'artifact': selected['cache']},
        {'kind': 'sec_companyfacts_raw_response', 'artifact': selected['rawproof']},
        {'kind': 'sec_companyfacts_normalization', 'artifact': frozen._stream_binding(normalization_path)}]
    parsed = {proof['kind']: (proof, _read_bound(proof['artifact'])[1]) for proof in proofs}
    memo = {}
    for document in products:
        path = output / 'products' / (document.document_id + '.json')
        atomic_write_json(path, document.to_dict())
        product = {'product': frozen._stream_binding(path), **_collision(document, oracle_root)}
        try:
            _verify_companyfacts_document(document, {'reviewed_available_at': document.available_at.isoformat()},
                parsed, frozen._aware(case['prediction_time']), memo)
            product['profile_preverified'] = True
        except Exception as error:
            product.update(profile_preverified=False, error_type=type(error).__name__, error=str(error))
        result['products'].append(product)
    status = 'preappend_eligible'
    if any(not row['profile_preverified'] for row in result['products']):
        status = 'unknown_native_profile_failed'
    elif any(row['collision'] for row in result['products']):
        status = 'preappend_collision'
    result.update(status=status, statistics=stats, normalization=frozen._stream_binding(normalization_path))
    return result


def _market_origin(case, request, match, original):
    document = RawInfoDocument.from_dict(_read_bound(original['original_record'])[1])
    cache = _read_bound(match['binding'])[1]
    symbol, start, end = document.metadata['symbol'], date.fromisoformat(document.metadata['start']), date.fromisoformat(document.metadata['end'])
    endpoint = 'https://api.massive.com/v2/aggs/ticker/' + quote(symbol, safe='') + '/range/1/day/' + start.isoformat() + '/' + end.isoformat()
    if (document.company_id != case['company_id'] or document.source_type != 'market_data'
            or cache['endpoint'] != endpoint or request['endpoint'] != endpoint
            or cache['source_key'] != 'massive' or cache['capability'] != 'price_daily'
            or cache['payload_kind'] != 'json' or dict(cache['params']) != {
                'method': 'GET', 'adjusted': 'true', 'sort': 'asc', 'limit': '50000'}
            or len(cache['params']) != 4):
        raise ReviewedSourceRejected('daily origin request/company differs')
    clocks = {bar['retrieved_at'] for bar in json.loads(document.content)}
    if len(clocks) != 1:
        raise ReviewedSourceRejected('daily source has ambiguous normalization clocks')
    normalized = frozen._aware(next(iter(clocks)))
    cached = frozen._aware(cache['retrieved_at'])
    if normalized < cached:
        raise ReviewedSourceRejected('daily origin cache is later than normalization')
    rows, days = _daily_market_rows(cache['body'], symbol, True, start, end)
    cutoff = frozen._aware(case['prediction_time'])
    if days[-1] >= cutoff.astimezone(timezone.utc).date() or document.available_at > cutoff:
        raise ReviewedSourceRejected('daily origin exceeds prediction cutoff')
    bars = [_price_bar_from_result(symbol, row, normalized.astimezone(timezone.utc), adjusted=True) for row in rows]
    as_of = datetime.combine(end + timedelta(days=1), datetime.min.time(), timezone.utc)
    actual = HistoricalPriceAdapter('massive', lambda *_args: bars).acquire(
        RawInfoRequest('preappend_origin', 'Reconstruct exact retained daily source.', (document.source_type,),
            lookback_days=(as_of.date() - start).days, max_documents=1),
        company_id=case['company_id'], identity={'ticker': symbol}, as_of=as_of).documents
    if len(actual) != 1:
        raise ReviewedSourceRejected('daily source reconstruction count differs')
    financial._require_same_record(actual[0], document)
    return {'latest_bar': days[-1].isoformat(), 'normalized_at': normalized.isoformat(),
        'provider_retrieved_at': cached.isoformat(), 'complete_canonical_reconstruction': True}, [
        {'purpose': 'historical_issuer', 'endpoint': 'https://api.massive.com/v3/reference/tickers/' + quote(symbol, safe=''),
            'query': {'date': days[-1].isoformat()}},
        {'purpose': 'all_type_splits', 'endpoint': 'https://api.massive.com/stocks/v1/splits', 'query': {
            'ticker': symbol, 'execution_date.gte': document.available_at.astimezone(timezone.utc).date().isoformat(),
            'execution_date.lte': max(cached, normalized).astimezone(timezone.utc).date().isoformat(),
            'sort': 'execution_date.asc', 'limit': '1000'}}]


def _market(case, missing):
    variants = []
    requests = [row for row in case['requests'] if row['family'] == 'market_daily']
    for request in requests:
        for original in request['original_candidates']:
            for match in request['matches']:
                outcome = {'original_record': original['original_record'], 'cache': match['binding']}
                variants.append(outcome)
                try:
                    details, proof_requests = _market_origin(case, request, match, original)
                    outcome.update(status='origin_reconstructed_missing_issuer_split_proofs', **details)
                    for proof in proof_requests:
                        missing.append({**proof, 'case_id': case['case_id'],
                            'original_record': original['original_record'], 'cache': match['binding']})
                except Exception as error:
                    outcome.update(status='unknown_origin_reconstruction_failed', error_type=type(error).__name__, error=str(error))
    return {'case_id': case['case_id'], 'request_associations': requests, 'variants': variants,
        'status': 'unknown_missing_proofs' if any(row.get('complete_canonical_reconstruction') for row in variants)
        else 'unknown_no_reconstructed_origin', 'source_admitted': False}


def _operating(case, selected, oracle_root, missing):
    targets = []
    cutoff, cik = frozen._aware(case['prediction_time']), case['company_id'].removeprefix('cik_')
    for selection in selected['selected_annual_interim']:
        target = {**selection, 'body_variants': [], 'wholebody_semantic_review': 'pending_not_form_inferred'}
        targets.append(target)
        if not selection['body_cache_matches']:
            missing.append({'purpose': 'exact_static_primary_body', 'case_id': case['case_id'],
                'endpoint': selection['primary_url'], 'query': {}, 'root_bindings': selection['root_bindings'],
                'accession_number': selection['accession'], 'form': selection['form'],
                'accepted_at': selection['accepted_at']})
        for root_binding in selection['root_bindings']:
            cache = _read_bound(root_binding)[1]
            for body_match in selection['body_cache_matches']:
                outcome = {'cache': body_match['binding'], 'root': root_binding}
                target['body_variants'].append(outcome)
                try:
                    body = _read_bound(body_match['binding'])[1]
                    accepted = frozen._aware(selection['accepted_at'])
                    originals = [(row['binding'], _read_bound(row['binding'])[1])
                        for row in selection.get('existing_same_id_originals', [])]
                    if len({canonical_json_hash(record) for _binding, record in originals}) > 1:
                        outcome.update(status='unknown_conflicting_existing_canonical_records', collision=True,
                            existing_records=[{'original_record': binding, 'canonical_record_hash': canonical_json_hash(record)}
                                for binding, record in originals])
                        continue
                    if originals:
                        binding, record = originals[0]
                        document = RawInfoDocument.from_dict(record)
                        if (document.document_id != selection['candidate_original_document_id']
                                or document.company_id != case['company_id']
                                or canonical_json_hash(document.to_dict()) != canonical_json_hash(record)):
                            raise ReviewedSourceRejected('existing whole original differs from selected native identity')
                        outcome.update(candidate_origin='bound_existing_original', candidate_original_record=binding)
                    else:
                        document = RawInfoDocument.create(document_id=selection['candidate_original_document_id'],
                            company_id=case['company_id'], source_type='filing', published_at=accepted,
                            available_at=accepted, content=body['body'], metadata={
                                'provider': 'sec_edgar', 'cik': cik, 'form': selection['form'],
                                'accession_number': selection['accession'], 'source_url': selection['primary_url']})
                        outcome['candidate_origin'] = 'native_primary_prototype_no_bound_original'
                    outcome['candidate_canonical_record_hash'] = canonical_json_hash(document.to_dict())
                    acceptance = {'issuer_cik': cik, 'accession_number': selection['accession'],
                        'form': selection['form'], 'primary_document': selection['primary_document'],
                        'accepted_at': selection['accepted_at']}
                    _verify_sec_document(document, {'reviewed_available_at': accepted.isoformat()}, {
                        'sec_static_archive_body': ({'endpoint': selection['primary_url'], 'expected_content_hash': document.content_hash}, body),
                        'sec_submissions_acceptance': (acceptance, cache)}, cutoff)
                    outcome.update(status='mechanical_profile_preverified_semantic_scope_pending', **_collision(document, oracle_root))
                except Exception as error:
                    outcome.update(status='unknown_native_profile_failed', error_type=type(error).__name__, error=str(error))
    return {'case_id': case['case_id'], 'retained_selection': selected, 'targets': targets,
        'status': 'pending_wholebody_semantic_review' if targets else 'unknown_no_periodic_target_in_retained_roots',
        'source_admitted': False}


def _find_bindings(value):
    if isinstance(value, dict):
        if isinstance(value.get('path'), str) and isinstance(value.get('sha256'), str):
            yield {'path': value['path'], 'sha256': value['sha256']}
        else:
            for item in value.values():
                yield from _find_bindings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _find_bindings(item)


def _missing_requests(rows):
    grouped = {}
    for row in rows:
        key = canonical_json_hash({'endpoint': row['endpoint'], 'query': row['query']})
        item = grouped.setdefault(key, {'endpoint': row['endpoint'], 'query': row['query'], 'associations': []})
        item['associations'].append({key: value for key, value in row.items() if key not in ('endpoint', 'query')})
    return [grouped[key] for key in sorted(grouped)]


def _prepare(case_projection, base_inputs, candidate_inventory, additional_companyfacts, output, operating_candidates):
    output = Path(output).resolve()
    if output.exists():
        raise ReviewedSourceRejected('source preparation output must be new; partial/completed output cannot rerun')
    paths = {'projection': case_projection, 'base': base_inputs, 'inventory': candidate_inventory, 'operating': operating_candidates}
    authorities, data = {}, {}
    for name, path in paths.items():
        authorities[name], data[name] = _bound_json(path)
        if authorities[name]['sha256'] != FIXED_SHA[name]:
            raise ReviewedSourceRejected('fixed ' + name + ' authority differs')
    projection, base, inventory = data['projection'], data['base'], data['inventory']
    frozen._validate_projection(projection)
    operating = data['operating']
    if operating['input'] != authorities['inventory']:
        raise ReviewedSourceRejected('operating supplement inventory differs')
    original_cases = {row['case_id']: row for row in projection['cases']}
    cases = inventory['cases']
    if len(cases) != 25 or len({row['case_id'] for row in cases}) != 25:
        raise ReviewedSourceRejected('fixed 25 financial family denominator differs')
    nonanchor = [row for row in cases if row['split'] != 'anchor']
    if len(nonanchor) != 24:
        raise ReviewedSourceRejected('fixed 24 market/operating family denominator differs')
    for case in cases:
        original = original_cases.get(case['case_id'])
        if original is None or any(case[key] != original[key] for key in ('company_id', 'split', 'prediction_time')):
            raise ReviewedSourceRejected('source family differs from original40 identity/cutoff/split')
        if case['ticker'] != projection['identities'][case['company_id']]['ticker']:
            raise ReviewedSourceRejected('source family ticker differs from approved identity')
    operating_cases = {row['case_id']: row for row in operating['cases']}
    if len(operating['cases']) != 25 or set(operating_cases) != {row['case_id'] for row in cases}:
        raise ReviewedSourceRejected('operating supplement fixed25 identities differ')
    for case in cases:
        if any(operating_cases[case['case_id']][key] != case[key] for key in ('company_id', 'ticker', 'split', 'prediction_time')):
            raise ReviewedSourceRejected('operating supplement cutoff/identity differs')
    review = _read_bound(base['source_review'])[1]
    if len(review['records']) != 658 or sum(row['verdict'] == 'admitted' for row in review['records']) != 653:
        raise ReviewedSourceRejected('fixed base653/658 view/review differs')
    oracle_root = Path(review['oracle_identity']['path']).resolve().parent
    for protected in (oracle_root, Path(base['reviewed_source_snapshot']['root']).resolve(),
            Path(case_projection).resolve().parent, Path(candidate_inventory).resolve().parent):
        if output.is_relative_to(protected) or protected.is_relative_to(output):
            raise ReviewedSourceRejected('output overlaps a retained source authority')
    additions, addition_bindings = _additional(additional_companyfacts, {case['company_id'] for case in cases})
    cohort_plan_binding, cohort_plan = _bound_json(Path(case_projection).parent / 'plan.json')
    if cohort_plan_binding['sha256'] != COHORT_PLAN_SHA:
        raise ReviewedSourceRejected('exact frozen40 plan changed')
    if cohort_plan['projection'] != authorities['projection']:
        raise ReviewedSourceRejected('original40 plan projection binding differs')
    sources = _bindings([*authorities.values(), cohort_plan_binding, inventory['prior_inventory'],
        *inventory['read_file_bindings'], *operating['read_file_bindings'], *addition_bindings, *_find_bindings(review),
        *_find_bindings(cohort_plan['groups']), base['source_review'],
        *financial._tree(base['reviewed_source_snapshot']['root'])])
    codes = _bindings([*frozen._code_bindings(), frozen._stream_binding(__file__),
        frozen._stream_binding(REPO / 'spec/scripts/diagnose_reviewed_frozen_source_snapshot.md')])
    _check([*sources, *codes])
    output.mkdir(parents=True)
    atomic_write_json(output / 'preparation-start.json', {'started_at': datetime.now(timezone.utc).isoformat(),
        'operation': 'prepare_only', 'fixed_financial_families': 25, 'fixed_market_operating_families': 24})
    plan = {'authorities': authorities, 'original40_plan': cohort_plan_binding,
        'fixed_cases': projection['cases'], 'registry_scopes': cohort_plan['groups'],
        'source_bindings': sources, 'code_bindings': codes,
        'additional_companyfacts': additions, 'global_append_allowed': False,
        'network_allowed': False, 'models_allowed': False, 'signal_apply_allowed': False,
        'prepare_inputs_allowed': False, 'labels_allowed': False, 'future_execute_implemented': False}
    plan['plan_hash'] = canonical_json_hash(plan)
    atomic_write_json(output / 'plan.json', plan)
    results, missing = {'financial': [], 'market': [], 'operating': []}, []
    try:
        for case in cases:
            case_output = output / 'cases' / case['case_id']
            for family, call in [('financial', lambda: _financial(case, additions, case_output, oracle_root)),
                    *([] if case['split'] == 'anchor' else [
                        ('market', lambda: _market(case, missing)),
                        ('operating', lambda: _operating(case, operating_cases[case['case_id']], oracle_root, missing))])]:
                try:
                    outcome = call()
                except Exception as error:
                    outcome = {'case_id': case['case_id'], 'company_id': case['company_id'],
                        'status': 'unknown_native_preflight_failed', 'error_type': type(error).__name__, 'error': str(error),
                        'retained_partial_artifacts': financial._tree(case_output) if case_output.exists() else []}
                results[family].append(outcome)
                atomic_write_json(case_output / (family + '.json'), outcome)
        observed = _bindings([*sources, *_find_bindings(results)])
        # Output products/normalizations are separately bound, never mistaken for retained sources.
        _check([*observed, *codes])
        atomic_write_json(output / 'missing-proof-requests.json', _missing_requests(missing))
        summary = {'status': 'completed_preappend_diagnosis', 'plan_hash': plan['plan_hash'],
            'fixed_case_denominator': 40, 'financial_family_denominator': 25,
            'market_operating_family_denominator': 24, 'outcomes': results,
            'derived_product_count': len(list((output / 'cases').glob('*/products/*.json'))),
            'expected_product_count': sum(len(financial._read(path)['expected_products'])
                for path in (output / 'cases').glob('*/normalization.json')),
            'profile_preverified_product_count': sum(product.get('profile_preverified', False)
                for row in results['financial'] for product in row.get('products', [])),
            'preappend_eligible_product_count': sum(product.get('profile_preverified', False) and not product['collision']
                for row in results['financial'] for product in row.get('products', [])),
            'collisions': sum(product['collision'] for row in results['financial'] for product in row.get('products', [])),
            'missing_proof_request_count': len(_missing_requests(missing)),
            'sources_and_code_unchanged': True, 'verified_bindings': observed,
            'global_store_constructed': False, 'source_appends': 0, 'GET_attempts': 0, 'model_calls': 0,
            'signal_apply_calls': 0, 'prepare_inputs_calls': 0, 'labels_loaded': False,
            'view_materialized': False, 'matrices_executed': False,
            'admission_or_readiness_claim': False}
        atomic_write_json(output / 'result.json', summary)
        return summary
    except Exception as error:
        atomic_write_json(output / 'failure.json', {'error_type': type(error).__name__, 'error': str(error),
            'terminal': True, 'retry_allowed': False})
        raise


def prepare(case_projection=DEFAULT_PROJECTION, base_inputs=DEFAULT_BASE,
        candidate_inventory=DEFAULT_INVENTORY, additional_companyfacts=None, output=DEFAULT_OUTPUT, operating_candidates=DEFAULT_OPERATING):
    """Freeze and diagnose all source families using local proof-only artifacts."""
    with _prepare_only():
        return _prepare(case_projection, base_inputs, candidate_inventory, additional_companyfacts, output, operating_candidates)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', action='store_true', required=True)
    parser.add_argument('--case-projection', type=Path, default=DEFAULT_PROJECTION)
    parser.add_argument('--base-inputs', type=Path, default=DEFAULT_BASE)
    parser.add_argument('--candidate-inventory', type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument('--additional-companyfacts', type=Path)
    parser.add_argument('--operating-candidates', type=Path, default=DEFAULT_OPERATING)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = prepare(args.case_projection, args.base_inputs, args.candidate_inventory, args.additional_companyfacts, args.output, args.operating_candidates)
    print(json.dumps({key: value for key, value in result.items() if key != 'outcomes' and key != 'verified_bindings'}))
