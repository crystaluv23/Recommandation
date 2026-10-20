"""Assemble explicit candidates from terminal source evidence; never append or run consumers.

The owning contract is spec/scripts/diagnose_reviewed_frozen_source_completion.md.
Unknowns preserve all 907 target dispositions. Native profile checks classify
source candidates, not company observations. Post-fetch semantic fragments are
independently authored and supplied explicitly, never inferred here.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path

import diagnose_reviewed_frozen_source_completion as completion
import diagnose_reviewed_frozen_source_snapshot as preappend
from stock_opportunity_agent.artifacts import atomic_write_json, canonical_json_hash
from stock_opportunity_agent.data.raw_info import RawInfoDocument
from stock_opportunity_agent.data.reviewed_snapshot import (
    ReviewedSourceRejected, _read_bound, _verify_market_document,
    _verify_sec_document,
)

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
STAGE = REPO / 'runs/diagnostics/reviewed_frozen_source_snapshot_20261020_v1/stage'
B = completion._binding


def read(path):
    return json.loads(Path(path).read_bytes())


def assemble(output, fragment_paths):
    """Build one new explicit packet from terminal95 and exact previous products."""
    output = Path(output).resolve()
    if output.exists():
        raise ReviewedSourceRejected('new assembly output required')
    collection = HERE / 'final-plan-v2/collection'
    receipts = read(collection / 'results.json')
    plan = read(HERE / 'final-plan-v2/request-plan.json')
    if receipts['terminal'] is not True or receipts['plan_hash'] != plan['plan_hash']:
        raise ReviewedSourceRejected('terminal exact95 source collection required')
    stage = read(STAGE / 'result.json')
    old_plan = read(STAGE / 'plan.json')
    projection_binding = B(preappend.DEFAULT_PROJECTION)
    cases = {r['case_id']: r for r in _read_bound(projection_binding)[1]['cases']}
    targets = completion._targets(stage)
    dispositions = {key: {'candidate_ids': [], 'reason': 'Unknown: no qualified candidate in this explicit source packet.'} for key in targets}
    candidates, audit, evidence, ids = [], [], [], set()

    def add(candidate):
        document = RawInfoDocument.from_dict(_read_bound(candidate['document'])[1])
        if document.document_id in ids:
            raise ReviewedSourceRejected('duplicate assembled candidate ID')
        ids.add(document.document_id)
        candidates.append(candidate)
        for key in candidate['target_keys']:
            dispositions[key]['candidate_ids'].append(document.document_id)
            dispositions[key]['reason'] = candidate['reason']

    for case in stage['outcomes']['financial']:
        normal = _read_bound(case['normalization'])[1]
        proofs = [{'kind': 'sec_companyfacts_cache', 'artifact': normal['source_cache']},
            {'kind': 'sec_companyfacts_raw_response', 'artifact': normal['raw_response']},
            {'kind': 'sec_companyfacts_normalization', 'artifact': case['normalization']}]
        for product in case['products']:
            key = completion._target_key('financial', case['case_id'], product['document_id'])
            if product['collision'] or not product['profile_preverified']:
                dispositions[key]['reason'] = 'Unknown: retained complete product has a canonical ID conflict or failed native proof; full expected set preserved.'
                continue
            add({'document': product['product'], 'target_keys': [key],
                'proof_profile': 'sec_companyfacts_filed_next_utc_day_v1', 'proofs': proofs,
                'reason': 'Exact completed-preappend canonical financial product; complete normalization set and native source profile retained.'})

    semantic_binding = B(HERE / 'operating-content-review.json')
    semantic = _read_bound(semantic_binding)[1]
    for row in semantic['targets']:
        key = completion._target_key('operating', row['case_id'], row['accession'])
        if row['source_record_disposition'] != 'content_qualified_existing_original_candidate':
            dispositions[key]['reason'] = 'Unknown: ' + row['reason']
            continue
        selection = targets[key]['retained_target']
        originals = [v['candidate_original_record'] for v in row['stage_body_variants'] if v.get('candidate_original_record')]
        originals += [v['original'] for v in row['additional_actual_original_as_is_reviews'] if v['as_is_native_verifier'] == 'passed_as_is']
        originals = list({(b['path'], b['sha256']): b for b in originals}.values())
        choices = []
        for original in originals:
            doc = RawInfoDocument.from_dict(_read_bound(original)[1])
            for body in selection['body_cache_matches']:
                for root in selection['root_bindings']:
                    proof = [{'kind': 'sec_static_archive_body', 'artifact': body['binding'],
                        'endpoint': selection['primary_url'], 'expected_content_hash': doc.content_hash},
                        {'kind': 'sec_submissions_acceptance', 'artifact': root,
                        'issuer_cik': doc.company_id.removeprefix('cik_'), 'accession_number': selection['accession'],
                        'form': selection['form'], 'primary_document': selection['primary_document'], 'accepted_at': selection['accepted_at']}]
                    try:
                        _verify_sec_document(doc, {'reviewed_available_at': doc.available_at.isoformat()},
                            {p['kind']: (p, _read_bound(p['artifact'])[1]) for p in proof}, completion.frozen._aware(cases[row['case_id']]['prediction_time']))
                    except (ReviewedSourceRejected, ValueError, KeyError, TypeError) as exc:
                        audit.append({'target': key, 'document': original, 'status': 'native_static_variant_rejected', 'reason': str(exc)})
                    else:
                        choices.append({'document': original, 'target_keys': [key], 'proof_profile': 'sec_archive_acceptance_v1',
                            'proofs': proof, 'semantic_review': semantic_binding,
                            'semantic_target': {'case_id': row['case_id'], 'accession': row['accession'], 'document_id': doc.document_id},
                            'reason': 'Existing original passes native SEC identity/time/body profile and independently reviewed complete report scope; partial fact reading remains explicit.'})
        if not choices:
            raise ReviewedSourceRejected('reviewed existing report has no qualified actual source chain')
        add(min(choices, key=lambda x: canonical_json_hash(x)))

    request_binding = receipts['market_request_record']
    market_records = [] if request_binding is None else _read_bound(request_binding)[1]
    if request_binding is not None and Path(request_binding['path']).resolve() != (collection / 'market-request-records.json').resolve():
        raise ReviewedSourceRejected('terminal market request-record path differs')
    record_by_name = {r['name']: r for r in market_records}
    requests_by_key = {canonical_json_hash({'endpoint': r['endpoint'], 'query': r['query']}): r for r in plan['requests']}
    for case in stage['outcomes']['market']:
        key = completion._target_key('market', case['case_id'])
        grouped = {}
        for variant in case['variants']:
            if variant.get('complete_canonical_reconstruction'):
                grouped.setdefault(variant['original_record']['path'], []).append(variant)
        for variants in grouped.values():
            variant = min(variants, key=lambda v: (v['cache']['path'], v['original_record']['path']))
            document = RawInfoDocument.from_dict(_read_bound(variant['original_record'])[1])
            cache = _read_bound(variant['cache'])[1]
            proofs = [{'kind': 'massive_daily_origin', 'artifact': variant['cache'],
                'provider_retrieved_at': variant['provider_retrieved_at'], 'normalization_retrieved_at': variant['normalized_at']}]
            try:
                _, required = preappend._market_origin(cases[case['case_id']], {'endpoint': cache['endpoint']},
                    {'binding': variant['cache']}, {'original_record': variant['original_record']})
                for required_request in required:
                    lookup = canonical_json_hash({k: required_request[k] for k in ('endpoint', 'query')})
                    request = requests_by_key[lookup]
                    receipt = record_by_name[request['name']]
                    artifact = B(collection / receipt['raw_response'])
                    proof = {'kind': 'massive_historical_issuer' if required_request['purpose'] == 'historical_issuer' else 'massive_no_post_cutoff_splits',
                        'artifact': artifact, 'request_record': request_binding, 'entry_name': request['name']}
                    if required_request['purpose'] == 'historical_issuer':
                        actual = _read_bound(artifact)[1]['results']
                        proof['expected_identity'] = {'ticker': document.metadata['symbol'],
                            'cik': document.company_id.removeprefix('cik_'), 'market': 'stocks', 'locale': 'us',
                            'primary_exchange': actual.get('primary_exchange'), 'type': 'CS', 'currency_name': 'usd'}
                    proofs.append(proof)
                _verify_market_document(document, {'reviewed_available_at': document.available_at.isoformat()},
                    {p['kind']: (p, _read_bound(p['artifact'])[1]) for p in proofs}, completion.frozen._aware(cases[case['case_id']]['prediction_time']))
            except (ReviewedSourceRejected, ValueError, KeyError, TypeError) as exc:
                audit.append({'target': key, 'document': variant['original_record'], 'status': 'unknown_native_market_proof', 'reason': str(exc)})
            else:
                add({'document': variant['original_record'], 'target_keys': [key],
                    'proof_profile': 'massive_daily_no_post_cutoff_split_v1', 'proofs': proofs,
                    'reason': 'Exact retained daily original reconstructed with historical issuer and all-type post-cutoff split proofs; no predictive interpretation.'})

    additional_market_products = []
    for path in fragment_paths:
        binding = B(path)
        fragment = _read_bound(binding)[1]
        evidence.append(binding)
        for candidate in fragment['candidates']:
            add(deepcopy(candidate))
        evidence.extend(fragment.get('evidence_bindings', []))
        additional_market_products.extend(fragment.get('additional_market_products', []))

    bundle = {'schema_version': 'frozen40-source-completion-bundle-v1',
        'projection': projection_binding, 'original40_plan': old_plan['original40_plan'],
        'base_inputs': B(preappend.DEFAULT_BASE), 'preappend_result': B(STAGE / 'result.json'),
        'operating_review': semantic_binding, 'collection_plan': B(HERE / 'final-plan-v2/request-plan.json'),
        'collection_results': B(collection / 'results.json'), 'evidence_bindings': evidence + ([request_binding] if request_binding is not None else []),
        'candidates': candidates, 'target_dispositions': dispositions,
        'additional_market_products': additional_market_products}
    # Source-only preflight uses exact real records/profiles. No store/view/matrix.
    base = _read_bound(bundle['base_inputs'])[1]
    review = _read_bound(base['source_review'])[1]
    with preappend._prepare_only():
        completion._qualify(candidates, targets, dispositions, list(cases.values()),
            Path(review['oracle_identity']['path']).parent, bundle['additional_market_products'])
    output.mkdir(parents=True, exist_ok=False)
    atomic_write_json(output / 'bundle.json', bundle)
    atomic_write_json(output / 'assembly-audit.json', {'candidates': len(candidates), 'targets': len(targets),
        'family_target_counts': {f: sum(k.startswith(f+'|') for k in targets) for f in ('financial', 'market', 'operating')},
        'unknown_targets': [k for k,v in dispositions.items() if not v['candidate_ids']],
        'variant_rejections': audit, 'GET_attempts': 0, 'global_appends': 0, 'models': 0,
        'prepare_inputs_calls': 0, 'labels_loaded': False})
    return B(output / 'bundle.json')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--fragment', action='append', default=[])
    args = parser.parse_args()
    print(json.dumps(assemble(args.output, args.fragment), ensure_ascii=False))
