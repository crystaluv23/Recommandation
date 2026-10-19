"""One bounded operating-source view and exact-ref input-only diagnostic."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import socket
from types import SimpleNamespace

from stock_opportunity_agent.artifacts import atomic_write_json, canonical_json_hash
from stock_opportunity_agent.data.raw_info import RawInfoDocument
from stock_opportunity_agent.data.reviewed_snapshot import (
    _read_bound, _verify_sec_document, materialize_reviewed_snapshot,
    open_raw_info_store, ReviewedSourceRejected,
)
from stock_opportunity_agent.data.resolution import DataAcquisitionPolicy
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.basic_info_orientation import compile_basic_info_requests
from stock_opportunity_agent.research.evolution_control import _build_evidence_resolver
from stock_opportunity_agent.research.evolution_core import default_information_plan, project_basic_info_bundle
from stock_opportunity_agent.signal_library import SignalRegistry, SignalExecutor

ROOT = Path(__file__).resolve().parents[3]
OUTPUT = Path(__file__).resolve().parent
NARRATIVE = ROOT / 'runs/diagnostics/market_source_qualification_20261020_v1/narrative-inventory.json'
MARKET_REVIEW = ROOT / 'reports/local-trusted-anchor-market-review-20261020.json'
MARKET_INPUT = ROOT / 'runs/diagnostics/reviewed_anchor_market_snapshot_20261020_v1/input_manifest.json'
REGISTRY_INPUT = ROOT / 'runs/diagnostics/reviewed_measurement_latest_stage_20261020_v1/inputs.json'
REVIEW = ROOT / 'reports/local-trusted-anchor-operating-review-20261020.json'


def read(path):
    return json.loads(Path(path).read_bytes())


def binding(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def verify_all(value):
    """Verify every nested file binding without changing source records."""
    if isinstance(value, dict):
        if 'path' in value and 'sha256' in value and binding(value['path']) != value:
            raise ReviewedSourceRejected('bound input differs: ' + value['path'])
        for child in value.values():
            verify_all(child)
    elif isinstance(value, list):
        for child in value:
            verify_all(child)


def narrative_row(case, source):
    document = RawInfoDocument.from_dict(_read_bound(source['original_record'])[1])
    row = {'document_id': document.document_id, 'company_id': document.company_id,
        'content_hash': document.content_hash, 'original_record': source['original_record'],
        'verdict': 'unknown', 'reason': 'Native proof and operating-purpose review pending.',
        'reviewed_available_at': document.available_at.isoformat(), 'proofs': [
            {'kind': 'sec_static_archive_body', 'artifact': source['static_body_cache'],
             'endpoint': source['static_body_endpoint'], 'expected_content_hash': document.content_hash},
            {'kind': 'sec_submissions_acceptance', 'artifact': source['submissions_cache'],
             'issuer_cik': case['company_id'].removeprefix('cik_'),
             'accession_number': source['accession_number'],
             'accepted_at': document.available_at.isoformat(),
             'primary_document': source['primary_document'], 'form': source['form']}],
        'operating_source_classification': {key: source[key] for key in
            ('form', 'body_scope', 'operating_periodic_source_present',
             'business_risks_segments_fact_sufficiency_verified')}}
    native_pass, error_text = False, None
    try:
        proofs = {proof['kind']: (proof, _read_bound(proof['artifact'])[1]) for proof in row['proofs']}
        _verify_sec_document(document, row, proofs, datetime.fromisoformat(case['prediction_time']))
        native_pass = True
    except (ReviewedSourceRejected, ValidationError, KeyError, ValueError, TypeError) as error:
        error_text = str(error)
    appropriate = (source['operating_periodic_source_present'] is True
        and source['form'] in ('10-K', '10-Q', '20-F', '40-F')
        and source['body_scope'] in ('static annual primary report', 'static interim primary report'))
    if native_pass and appropriate:
        row.update(verdict='admitted', reason='Native exact SEC body/issuer/acceptance/PIT proof and retained full annual/interim operating primary scope; complete business/risk/segment fact visibility is unverified.')
    elif not native_pass:
        row['reason'] = 'Native SEC proof remains unproven: ' + str(error_text)
    else:
        row['reason'] = 'Native SEC identity/time proof passed, but the selected primary is a cover/current-report index referring to separate operating exhibits; full annual/interim operating body is not established in this frozen scope.'
    return row, {'document_id': document.document_id, 'case_id': case['case_id'],
        'native_sec_profile_pass': native_pass, 'native_error': error_text,
        'operating_purpose_eligible': appropriate, 'verdict': row['verdict'], 'reason': row['reason']}


def main():
    if REVIEW.exists() or (OUTPUT / 'input_manifest.json').exists() or (OUTPUT / 'snapshot').exists():
        raise ReviewedSourceRejected('new operating diagnostic outputs required')
    if binding(NARRATIVE)['sha256'] != 'a174dca9dc02a178713112c53746e1bded6703306e01b130d6d17bcdf94d335d':
        raise ReviewedSourceRejected('narrative inventory changed')
    inventory, market_review, registry_input = map(read, (NARRATIVE, MARKET_REVIEW, REGISTRY_INPUT))
    verify_all(inventory)
    if len(inventory['cases']) != 15 or sum(len(case['records']) for case in inventory['cases']) != 27:
        raise ReviewedSourceRejected('fixed narrative scope differs')
    old_binding = read(MARKET_INPUT)['reviewed_source_snapshot']
    old_files = [binding(path) for path in sorted(Path(old_binding['root']).rglob('*')) if path.is_file()]
    registry = SignalRegistry(registry_input['registry_root'], candidate_root=OUTPUT / 'unused_candidates')
    snapshot = registry.snapshot_from_refs(registry_input['registry_version'], tuple(registry_input['registry_refs']))
    if len(snapshot.specs) != 18 or snapshot.registry_hash != registry_input['registry_hash']:
        raise ReviewedSourceRejected('frozen exact-ref Registry differs')
    registry_bindings = [binding(Path(registry_input['registry_root']) / 'registry.json')]
    for spec in snapshot.specs:
        version_root = Path(registry_input['registry_root']) / spec.category / spec.signal_id / 'versions' / ('v' + str(spec.version))
        registry_bindings.append(binding(version_root / 'spec.json'))
        if spec.ref in snapshot.skills:
            registry_bindings.append(binding(version_root / 'skill.md'))
    new_rows, source_checks = [], []
    for case in inventory['cases']:
        for source in case['records']:
            row, check = narrative_row(case, source)
            new_rows.append(row)
            source_checks.append(check)
    review = {key: value for key, value in market_review.items() if key != 'manifest_hash'}
    review['records'] = market_review['records'] + new_rows
    review['scope'] = {**market_review['scope'], 'purpose': 'Fixed 15-case market plus same27 selected operating-primary qualification and label-free exact v12 input readiness; no full run.'}
    review['manifest_hash'] = canonical_json_hash(review)
    atomic_write_json(REVIEW, review)
    view = materialize_reviewed_snapshot(REVIEW, OUTPUT / 'snapshot')
    inputs = {'schema_version': 'fixed-anchor-operating-inputs-v1', 'source_review': binding(REVIEW),
        'reviewed_source_snapshot': view, 'narrative_inventory': binding(NARRATIVE),
        'previous_market_review': binding(MARKET_REVIEW), 'previous_market_input': binding(MARKET_INPUT),
        'previous_view_bindings': old_files, 'registry_source_inputs': binding(REGISTRY_INPUT),
        'registry_version': snapshot.version, 'registry_hash': snapshot.registry_hash,
        'registry_refs': [spec.ref for spec in snapshot.specs], 'registry_bindings': registry_bindings,
        'registry_scope': 'Completed latest-measurement definition pool v12 only, not run_minimal_rounds default HISTORY v6.',
        'original_narrative_bindings': [row['original_record'] for row in new_rows],
        'native_code_bindings': [binding(Path(__file__)), *[binding(ROOT / 'src/stock_opportunity_agent' / name) for name in
            ('data/reviewed_snapshot.py', 'data/raw_info.py', 'data/resolution.py', 'data/filing_orientation.py',
             'research/basic_info_orientation.py', 'research/evolution_core.py', 'research/evolution_control.py', 'signal_library.py')]],
        'fixed_case_denominator': 15, 'selected_narrative_denominator': 27, 'fixed_signal_ref_denominator': 18,
        'acquisition_allowed': False, 'model_calls_authorized': False, 'labels_loaded': False,
        'full_prepare_executed': False}
    atomic_write_json(OUTPUT / 'input_manifest.json', inputs)
    input_hash = canonical_json_hash(inputs)
    frozen_view = read(OUTPUT / 'input_manifest.json')['reviewed_source_snapshot']
    store = open_raw_info_store(frozen_view['root'], reviewed_snapshot=frozen_view)
    worker = store.snapshot()
    resolver = _build_evidence_resolver(OUTPUT / 'runtime', worker,
        contract=SimpleNamespace(data_acquisition=DataAcquisitionPolicy()), allow_data_external=False, environ={}, cycle_id=1)
    executor = SignalExecutor(snapshot, worker, resolver=resolver)
    summaries = []
    for case in inventory['cases']:
        cutoff = datetime.fromisoformat(case['prediction_time'])
        identity = {'ticker': case['ticker'], 'company_name': case['company_name']}
        bundle = resolver.resolve_basic_info(compile_basic_info_requests(default_information_plan().basic_info_policy),
            company_id=case['company_id'], identity=identity, as_of=cutoff)
        model, lineage = project_basic_info_bundle(bundle)
        resolutions = executor.prepare_inputs(tuple(spec.ref for spec in snapshot.specs),
            company_id=case['company_id'], as_of=cutoff, identity=identity)
        operating = next(item for item in bundle.requests if item.request.request_id == 'orientation.v1.operating_report')
        projected = next(item for item in model['requests'] if item['request']['request_id'] == operating.request.request_id)
        selected = resolver.load_documents(operating, as_of=cutoff)
        ready = sum(item.status == 'resolved' for item in resolutions)
        summary = {'case_id': case['case_id'], 'ticker': case['ticker'], 'prediction_time': case['prediction_time'],
            'operating_request_status': operating.status, 'operating_source_ids': [item.document_id for item in selected],
            'operating_coverage': operating.coverage.to_dict(),
            'operating_model_projection_present': bool(projected['projections']),
            'operating_projection_status': projected['projection_status'],
            'operating_visible_projection_count': projected['visible_projection_count'],
            'operating_omitted_projection_count': projected['omitted_projection_count'],
            'resolved_signal_input_count': ready, 'signal_ref_denominator': 18,
            'resolved_fraction': ready / 18, 'meets_existing_0_8_signal_input_fraction': ready / 18 >= 0.8,
            'source_preservation': all(document.to_dict() == read(next(row['original_record']['path'] for row in new_rows
                if row['document_id'] == document.document_id)) for document in selected)}
        atomic_write_json(OUTPUT / 'cases' / (case['case_id'] + '.json'), {'case': case, 'summary': summary,
            'basic_info_bundle': bundle.to_dict(), 'model_context': model, 'lineage': lineage,
            'exact_signal_input_resolutions': [item.to_dict() for item in resolutions]})
        summaries.append(summary)
        print(case['ticker'] + ': operating=' + operating.status + ', exact-v12-inputs=' + str(ready) + '/18', flush=True)
    verify_all(inventory)
    verify_all(inputs)
    if canonical_json_hash(read(OUTPUT / 'input_manifest.json')) != input_hash:
        raise ReviewedSourceRejected('frozen diagnostic input changed')
    restored = open_raw_info_store(view['root'], reviewed_snapshot=read(OUTPUT / 'input_manifest.json')['reviewed_source_snapshot'])
    result = {'schema_version': 'fixed-anchor-operating-readiness-result-v1', 'input_manifest_hash': input_hash,
        'fixed_case_denominator': 15, 'selected_narrative_denominator': 27,
        'new_native_sec_profile_pass_count': sum(row['native_sec_profile_pass'] for row in source_checks),
        'new_operating_admitted_count': sum(row['verdict'] == 'admitted' for row in new_rows),
        'new_operating_unknown_count': sum(row['verdict'] == 'unknown' for row in new_rows),
        'old21_rows_preserved_verbatim': review['records'][:21] == market_review['records'],
        'reviewed_total_document_count': len(store.documents), 'source_checks': source_checks,
        'registry_version': snapshot.version, 'registry_hash': snapshot.registry_hash,
        'registry_refs': [spec.ref for spec in snapshot.specs], 'registry_scope': inputs['registry_scope'],
        'operating_requests_resolved': sum(row['operating_request_status'] == 'resolved' for row in summaries),
        'cases_meeting_signal_input_fraction_0_8': sum(row['meets_existing_0_8_signal_input_fraction'] for row in summaries),
        'cases': summaries, 'typed_store_restore_equal': type(restored) is type(store) is type(worker) and restored.documents == store.documents,
        'old_view_unchanged': old_files == [binding(path) for path in sorted(Path(old_binding['root']).rglob('*')) if path.is_file()],
        'bound_originals_and_inputs_unchanged': True, 'readonly_data_requests': 0, 'external_llm_calls': 0,
        'labels_loaded': False, 'signal_apply_executed': False, 'full_prepare_executed': False,
        'full_readiness_proven': False, 'engineering_mvp_closed': False,
        'limits': ['No assertion that annual/interim presence makes every business/risk/segment fact visible.',
            'Filing prose is not financial-facts input; missing financial/news/call families remain measured gaps.',
            'Readiness is input resolution for this exact v12 pool, not default v6 fullprepare, model behavior or prediction benefit.']}
    atomic_write_json(OUTPUT / 'result.json', result)
    print(json.dumps({key: value for key, value in result.items() if key not in ('source_checks', 'cases', 'registry_refs')}, indent=2))


if __name__ == '__main__':
    def forbidden(*_args, **_kwargs):
        raise AssertionError('network forbidden in operating diagnostic')
    socket.socket = forbidden
    main()
