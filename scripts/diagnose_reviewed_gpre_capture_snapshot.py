"""Version four recorded GPRE captures and inspect one source-only input case."""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from types import SimpleNamespace

import diagnose_reviewed_anchor_financial_snapshot as financial
import diagnose_reviewed_frozen_case_inputs as frozen
import diagnose_reviewed_frozen_source_snapshot as preappend
from run_reviewed_posthoc_stage import _historical_code_check
from stock_opportunity_agent.artifacts import atomic_write_json, canonical_json_hash
from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.data.resolution import DataAcquisitionPolicy, _deduplicate_documents, source_types_compatible
from stock_opportunity_agent.data.reviewed_snapshot import (
    ReviewedSourceRejected, _read_bound, _verify_companyfacts_document,
    materialize_reviewed_snapshot, open_raw_info_store,
)
from stock_opportunity_agent.data.sec_company_facts import (
    CAPTURE_IDENTITY_POLICY, LEGACY_IDENTITY_POLICY, materialize_company_fact_documents,
)
from stock_opportunity_agent.research.basic_info_orientation import compile_basic_info_requests
from stock_opportunity_agent.research.evolution_control import _build_evidence_resolver
from stock_opportunity_agent.research.evolution_core import default_information_plan, project_basic_info_bundle
from stock_opportunity_agent.signal_library import SignalExecutor

REPO = Path(__file__).resolve().parents[1]
SPEC = REPO / 'spec/scripts/diagnose_reviewed_gpre_capture_snapshot.md'
BASE = REPO / 'runs/diagnostics/reviewed_frozen_source_completion_20261020_v1/stage'
DIAGNOSIS = REPO / 'runs/diagnostics/reviewed_frozen_source_snapshot_20261020_v1/stage/result.json'
DEFAULT_OUTPUT = REPO / 'runs/diagnostics/reviewed_gpre_capture_snapshot_20261021_v1/stage'
SOURCE_COMMIT = 'c9ad66e80f9b4f72438f5be93496dbaaa9410e92'
AUTHORITIES = {
    BASE / 'result.json': 'e712f77a96278f2f1f41e63131ccee87714e2db487c82789c719daf8728e5dd4',
    BASE / 'input_manifest.json': '853be82912ec717f4b7779d6b0562b3d1792d6ed88602b3c9eb58076498edc73',
    BASE / 'plan.json': 'b099d0af1ecc3720faaa23b884cb810122408c2b7470d494a81b7e4195987761',
    DIAGNOSIS: 'ac71fbcbf40526e04446c0cca25e568d02b0fd9df06ffd28463d03fcc90369ec',
}
CASE_ID = 'cik_0001309402:20250530'
PRODUCTS, CONFLICTS, BASE_DOCS, BASE_ROWS = 57, 4, 1776, 1781
PROFILE = 'sec_companyfacts_capture_filed_next_utc_day_v1'
LATEST_PERIOD_END = '2025-03-31'
_binding, _read, _check = frozen._stream_binding, financial._read, preappend._check
FORBIDDEN = ('network_allowed', 'models_allowed', 'labels_allowed', 'apply_allowed', 'full_prepare_allowed')


def _exclusive(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as handle:
        json.dump(value, handle, sort_keys=True); handle.flush(); os.fsync(handle.fileno())


def _identity(document):
    return {'document_id': document.document_id, 'content_hash': document.content_hash,
            'canonical_record_hash': canonical_json_hash(document.to_dict())}


def _proofs(normalization, binding):
    return [{'kind': kind, 'artifact': artifact} for kind, artifact in (
        ('sec_companyfacts_cache', normalization['source_cache']),
        ('sec_companyfacts_raw_response', normalization['raw_response']),
        ('sec_companyfacts_normalization', binding))]


def _row(document, original, proofs):
    return {'document_id': document.document_id, 'company_id': document.company_id,
        'content_hash': document.content_hash, 'original_record': original, 'verdict': 'admitted',
        'reviewed_available_at': document.available_at.isoformat(), 'proof_profile': PROFILE,
        'proofs': proofs, 'reason': 'Complete recorded SEC Company Facts capture version; filed-next-UTC-day policy. Retrospective extraction and primary-filing audit limits unchanged.'}


def _derive(case, old_review, oracle_root):
    """Reconstruct both complete sets; select only the four recorded collisions."""
    normalization = _read_bound(case['normalization'])[1]
    cache = _read_bound(normalization['source_cache'])[1]
    kwargs = {key: normalization[key] for key in ('item', 'selection', 'provenance')}
    kwargs['retrieved_at'] = frozen._aware(normalization['normalized_at'])
    legacy, _ = materialize_company_fact_documents(cache['body'], **kwargs, identity_policy=LEGACY_IDENTITY_POLICY)
    capture, _ = materialize_company_fact_documents(cache['body'], **kwargs, identity_policy=CAPTURE_IDENTITY_POLICY)
    expected = {_identity(doc)['document_id']: _identity(doc) for doc in legacy}
    saved = {p['document_id']: p for p in case['products']}
    recorded = {p['document_id']: p for p in normalization['expected_products']}
    if (len(legacy) != PRODUCTS or len(capture) != PRODUCTS or len(saved) != PRODUCTS
            or len(case['products']) != PRODUCTS or len(recorded) != PRODUCTS
            or len(normalization['expected_products']) != PRODUCTS
            or canonical_json_hash(expected) != canonical_json_hash(recorded) or set(saved) != set(expected)):
        raise ReviewedSourceRejected('complete recorded legacy/capture product denominator differs')
    review_ids = {r['document_id']: r for r in old_review['records']}
    mapping, selected = [], []
    for old, new in zip(legacy, capture, strict=True):
        financial._require_same_record(new, old.as_capture())
        product = saved[old.document_id]
        financial._require_same_record(old, RawInfoDocument.from_dict(_read_bound(product['product'])[1]))
        if product.get('profile_preverified') is not True or type(product.get('collision')) is not bool:
            raise ReviewedSourceRejected('recorded product qualification/disposition differs')
        collision = preappend._collision(old, oracle_root)
        if collision['collision'] != product['collision']:
            raise ReviewedSourceRejected('recorded legacy collision originals differ')
        if product['collision'] and canonical_json_hash(collision['matches']) != canonical_json_hash(product['matches']):
            raise ReviewedSourceRejected('recorded conflicting original bindings differ')
        capture_collision = preappend._collision(new, oracle_root)
        if capture_collision['collision']:
            raise ReviewedSourceRejected('capture ID has a different canonical original')
        if product['collision']:
            if old.document_id in review_ids:
                raise ReviewedSourceRejected('colliding legacy candidate unexpectedly admitted')
            if capture_collision['matches']:
                raise ReviewedSourceRejected('fresh capture subset already exists')
            selected.append(new)
        else:
            row = review_ids.get(old.document_id)
            if row is None or row['verdict'] != 'admitted':
                raise ReviewedSourceRejected('retained legacy product is not admitted')
            financial._require_same_record(old, RawInfoDocument.from_dict(_read_bound(row['original_record'])[1]))
        mapping.append({'legacy_id': old.document_id, 'capture_id': new.document_id,
                        'selected': product['collision'], 'content_hash': new.content_hash})
    if len(selected) != CONFLICTS:
        raise ReviewedSourceRejected('exact recorded four-collision subset differs')
    normalized = deepcopy(normalization)
    normalized.update(schema_version='sec-companyfacts-normalization-v2', normalizer_profile=PROFILE,
                      identity_policy=CAPTURE_IDENTITY_POLICY, expected_products=[_identity(d) for d in capture])
    return capture, selected, normalized, mapping


def _qualify(documents, normalization, binding, cutoff):
    """Use the complete actual profile, including its full expected-product set."""
    proofs = _proofs(normalization, binding)
    decoded = {p['kind']: (p, _read_bound(p['artifact'])[1]) for p in proofs}
    memo = {}
    for document in documents:
        _verify_companyfacts_document(document, _row(document, {}, proofs), decoded, cutoff, memo)
    return proofs


def _authorities(output):
    authorities = [{'path': str(p.resolve()), 'sha256': sha} for p, sha in AUTHORITIES.items()]
    _check(authorities)
    result, inputs, old_plan, diagnosis = (_read(p) for p in (BASE/'result.json', BASE/'input_manifest.json', BASE/'plan.json', DIAGNOSIS))
    if (result['status'] != 'completed' or result['plan_hash'] != old_plan['plan_hash']
            or canonical_json_hash({k:v for k,v in old_plan.items() if k != 'plan_hash'}) != old_plan['plan_hash']
            or inputs['source_review'] != result['source_review']
            or inputs['reviewed_source_snapshot'] != result['reviewed_source_snapshot']):
        raise ReviewedSourceRejected('completed source authority differs')
    _historical_code_check(old_plan['code_bindings'], SOURCE_COMMIT)
    review = _read_bound(inputs['source_review'])[1]
    if len(review['records']) != BASE_ROWS or sum(r['verdict']=='admitted' for r in review['records']) != BASE_DOCS:
        raise ReviewedSourceRejected('base complete review/document count differs')
    root = Path(review['oracle_identity']['path']).resolve().parent
    for protected in (root, BASE.resolve(), DIAGNOSIS.parent.resolve()):
        if output.is_relative_to(protected) or protected.is_relative_to(output):
            raise ReviewedSourceRejected('new diagnostic overlaps a retained source root')
    projection = _read_bound(inputs['projection'])[1]
    frozen._validate_projection(projection)
    cases = [c for c in projection['cases'] if c['case_id']==CASE_ID]
    financials = [c for c in diagnosis['outcomes']['financial'] if c['case_id']==CASE_ID]
    if len(cases)!=1 or len(financials)!=1:
        raise ReviewedSourceRejected('exact GPRE case is absent/ambiguous')
    groups = inputs['groups']
    if groups != old_plan['groups'] or [g['name'] for g in groups] != ['default_v6','latest_v12']:
        raise ReviewedSourceRejected('exact two Registry groups differ')
    data = [*authorities, *old_plan['source_bindings'], *preappend._find_bindings(inputs),
            *preappend._find_bindings(review), *preappend._find_bindings(financials[0]),
            *financial._tree(inputs['reviewed_source_snapshot']['root'])]
    for group in groups:
        _, bindings = frozen._snapshot(group, output); data += bindings
    data = preappend._bindings(data); _check(data)
    return review, root, financials[0], cases[0], projection['identities'][cases[0]['company_id']], groups, data, inputs['reviewed_source_snapshot']


def _code_bindings():
    helpers = [__file__, SPEC, financial.__file__, frozen.__file__, preappend.__file__,
               REPO/'scripts/run_reviewed_posthoc_stage.py',
               REPO/'spec/scripts/run_reviewed_posthoc_stage.md',
               REPO/'spec/scripts/diagnose_reviewed_frozen_source_snapshot.md',
               REPO/'spec/src/stock_opportunity_agent/data/raw_info.md',
               REPO/'spec/src/stock_opportunity_agent/data/reviewed_companyfacts_profile.md',
               REPO/'spec/src/stock_opportunity_agent/data/sec_company_facts.md']
    return preappend._bindings([*frozen._code_bindings(), *map(_binding, helpers)])


def _validate_destination(output):
    """Reject protected roots before creating any directory or terminal marker."""
    inputs_path = BASE/'input_manifest.json'
    inputs = _read_bound({'path':str(inputs_path.resolve()), 'sha256':AUTHORITIES[inputs_path]})[1]
    review = _read_bound(inputs['source_review'])[1]
    oracle_root = Path(review['oracle_identity']['path']).resolve().parent
    protected = (oracle_root, BASE.resolve(), DIAGNOSIS.parent.resolve(),
                 Path(inputs['reviewed_source_snapshot']['root']).resolve())
    if any(output.is_relative_to(root) or root.is_relative_to(output) for root in protected):
        raise ReviewedSourceRejected('new diagnostic overlaps a retained source root')


def _plan_header(output, expected):
    """Require an existing authentic stage plan before an execution marker."""
    plan = _read(output/'plan.json')
    if (plan['schema_version']!='gpre-capture-source-plan-v1' or plan['output']!=str(output)
            or plan['plan_hash']!=expected or canonical_json_hash({k:v for k,v in plan.items() if k!='plan_hash'})!=expected
            or any(plan[k] is not False for k in FORBIDDEN)
            or any(type(plan[k]) is not int or plan[k]!=v for k,v in (
                ('products_count',PRODUCTS),('new_capture_count',CONFLICTS),('retained_count',PRODUCTS-CONFLICTS),
                ('base_documents',BASE_DOCS),('base_review_rows',BASE_ROWS)))):
        raise ReviewedSourceRejected('capture plan scope/hash differs')
    return plan


def prepare(output):
    """Freeze all sources and qualify local products without global store access."""
    output = Path(output).resolve()
    with preappend._prepare_only():
        if output.exists(): raise ReviewedSourceRejected('capture diagnostic output must be new')
        _validate_destination(output)
        _exclusive(output/'preparation-start.json', {'started_at': datetime.now(timezone.utc).isoformat()})
        try:
            review, root, case, identity_case, identity, groups, data, view = _authorities(output)
            documents, selected, normalized, mapping = _derive(case, review, root)
            for doc in documents: atomic_write_json(output/'products'/(doc.document_id+'.json'), doc.to_dict())
            atomic_write_json(output/'normalization.json', normalized)
            normal_binding = _binding(output/'normalization.json')
            _qualify(documents, normalized, normal_binding, frozen._aware(identity_case['prediction_time']))
            old_global = financial._tree(root)
            atomic_write_json(output/'global-originals-before.json', old_global)
            atomic_write_json(output/'identity-mapping.json', mapping)
            plan = {'schema_version':'gpre-capture-source-plan-v1', 'output':str(output),
                'source_bindings':data, 'code_bindings':_code_bindings(), 'global_before':_binding(output/'global-originals-before.json'),
                'normalization':normal_binding, 'mapping':_binding(output/'identity-mapping.json'),
                'products':[_binding(output/'products'/(d.document_id+'.json')) for d in documents],
                'selected_ids':[d.document_id for d in selected], 'old_review':_binding(BASE/'source-review.json'),
                'old_view':view, 'oracle_root':str(root), 'case':identity_case, 'identity':identity, 'groups':groups,
                'products_count':PRODUCTS,'new_capture_count':CONFLICTS,'retained_count':PRODUCTS-CONFLICTS,
                'base_documents':BASE_DOCS,'base_review_rows':BASE_ROWS, **{k:False for k in FORBIDDEN}}
            plan['plan_hash'] = canonical_json_hash(plan)
            atomic_write_json(output/'plan.json', plan)
            return plan
        except Exception as error:
            atomic_write_json(output/'preparation-failure.json', {'terminal':True,'error_type':type(error).__name__}); raise


def _verify_plan(output, expected):
    plan = _plan_header(output, expected)
    _check(plan['source_bindings']+plan['code_bindings']+plan['products']+
           [plan[k] for k in ('global_before','normalization','mapping','old_review')])
    review, root, case, identity_case, identity, groups, data, view = _authorities(output)
    docs, selected, normalized, mapping = _derive(case, review, root)
    if canonical_json_hash([_identity(d) for d in docs]) != canonical_json_hash([_identity(RawInfoDocument.from_dict(_read_bound(b)[1])) for b in plan['products']]):
        raise ReviewedSourceRejected('saved capture complete products differ')
    if canonical_json_hash(normalized)!=canonical_json_hash(_read_bound(plan['normalization'])[1]) or canonical_json_hash(mapping)!=canonical_json_hash(_read_bound(plan['mapping'])[1]):
        raise ReviewedSourceRejected('saved normalization/mapping differs')
    actual = (str(root),identity_case,identity,groups,data,view,[d.document_id for d in selected])
    frozen_values = (plan['oracle_root'],plan['case'],plan['identity'],plan['groups'],plan['source_bindings'],plan['old_view'],plan['selected_ids'])
    if canonical_json_hash(actual)!=canonical_json_hash(frozen_values):
        raise ReviewedSourceRejected('frozen source identities differ')
    _qualify(docs, normalized, plan['normalization'], frozen._aware(identity_case['prediction_time']))
    _check(_read_bound(plan['global_before'])[1])
    return plan, review, selected


def _selected_scope(resolution, store, cutoff):
    """Report actual consumer selection, never substitute all visible documents."""
    financial_request = source_types_compatible(('sec_company_facts',), resolution.request.source_types)
    rows = []
    for reference in resolution.documents:
        document = store.load(reference.document_id, as_of=cutoff)
        facts = []
        if document.source_type == 'sec_company_facts':
            body = json.loads(document.content)
            facts = [{key: fact.get(key) for key in ('taxonomy','tag','start','end','unit')}
                     for fact in body.get('facts',[])]
        rows.append({'document_id':document.document_id,'content_hash':document.content_hash,'facts':facts})
    q1 = [r['document_id'] for r in rows if any(f['end']==LATEST_PERIOD_END and f['tag'] and f['unit'] for f in r['facts'])]
    return {'request_id':resolution.request.request_id,'financial_source_request':financial_request,
        'status':('latest_q1_selected' if q1 else 'gap_latest_q1_not_selected') if financial_request else 'not_applicable',
        'selected_documents':rows,'latest_period_end':LATEST_PERIOD_END,'latest_q1_source_ids':q1,
        'resolution_status':resolution.status,'coverage':resolution.coverage.to_dict()}


def _consume(output, view, plan):
    store = open_raw_info_store(view['root'], reviewed_snapshot=view); worker = store.snapshot()
    if len(store.documents) != BASE_DOCS+CONFLICTS:
        raise ReviewedSourceRejected('new view membership denominator differs')
    resolver = _build_evidence_resolver(output/'runtime', worker,
        contract=SimpleNamespace(data_acquisition=DataAcquisitionPolicy()), allow_data_external=False, environ={}, cycle_id=1)
    case, identity = plan['case'], plan['identity']; cutoff = frozen._aware(case['prediction_time'])
    summaries = {}; selections = {}
    for group in plan['groups']:
        executor = SignalExecutor(frozen._snapshot(group, output)[0], worker, resolver=resolver)
        resolutions = executor.prepare_inputs(tuple(group['refs']), company_id=case['company_id'], as_of=cutoff, identity=identity)
        atomic_write_json(output/(group['name']+'.json'), {'registry':group,
            'resolutions':[{'signal_ref':ref,'resolution':r.to_dict()} for ref,r in zip(group['refs'],resolutions,strict=True)]})
        summaries[group['name']] = {'resolved':sum(r.status=='resolved' for r in resolutions),'denominator':len(group['refs'])}
        selections[group['name']] = [{'signal_ref':ref, **_selected_scope(r,worker,cutoff)}
            for ref,r in zip(group['refs'],resolutions,strict=True)]
    bundle = resolver.resolve_basic_info(compile_basic_info_requests(default_information_plan().basic_info_policy),
        company_id=case['company_id'], identity=identity, as_of=cutoff)
    model, lineage = project_basic_info_bundle(bundle)
    atomic_write_json(output/'basic-info.json', {'bundle':bundle.to_dict(),'model':model,'lineage':lineage})
    selections['basic_info'] = [_selected_scope(r,worker,cutoff) for r in bundle.requests]
    atomic_write_json(output/'consumer-selection-evidence.json', selections)
    visible = worker.search(case['company_id'], source_types=('sec_company_facts',), as_of=cutoff)
    deduped, duplicates = _deduplicate_documents(visible)
    rows = []
    for document in deduped:
        body = json.loads(document.content)
        rows.append({'document_id':document.document_id,'content_hash':document.content_hash,
            'facts':[{'tag':f.get('tag'),'unit':f.get('unit'),'end':f.get('end'),'filed':f.get('filed')}
                     for f in body.get('facts',[])]})
    atomic_write_json(output/'visible-financial-scope.json', {'documents':rows,'duplicate_ids':list(duplicates),
        'independent_content_units':len(deduped),'q1_source_ids':[r['document_id'] for r in rows if any(f['end']=='2025-03-31' for f in r['facts'])]})
    reopened = open_raw_info_store(view['root'], reviewed_snapshot=view)
    if type(reopened) is not type(worker) or not financial._same_document_set(worker.documents,reopened.documents):
        raise ReviewedSourceRejected('snapshot/reopen canonical document set differs')
    return summaries


def execute(output, expected_plan_hash):
    """Append exactly four already qualified capture versions once; preserve failures."""
    output = Path(output).resolve()
    with frozen._source_only():
        _validate_destination(output)
        _plan_header(output, expected_plan_hash)
        _exclusive(output/'execution-start.json', {'plan_hash':expected_plan_hash,'started_at':datetime.now(timezone.utc).isoformat()})
        try:
            plan, review, selected = _verify_plan(output, expected_plan_hash)
            root = Path(plan['oracle_root']); before = _read_bound(plan['global_before'])[1]
            # Reject unexpected intervening additions too, before constructing the store.
            if canonical_json_hash(financial._tree(root)) != canonical_json_hash(before):
                raise ReviewedSourceRejected('global source inventory changed before append')
            store = RawInfoStore(root); receipts = []; added_rows = []; expected_paths = []
            proofs = _proofs(_read_bound(plan['normalization'])[1],plan['normalization'])
            for doc in selected:
                inserted = store.append(doc); financial._require_same_record(store.load(doc.document_id),doc)
                if inserted is not True:
                    raise ReviewedSourceRejected('fresh capture did not create its required new original')
                if store.append(doc) is not False:
                    raise ReviewedSourceRejected('same recorded capture replay inserted')
                financial._require_same_record(store.load(doc.document_id),doc)
                original = _binding(root/doc.source_type/doc.company_id/(doc.document_id+'.json'))
                expected_paths.append(original['path'])
                receipt = {'document_id':doc.document_id,'inserted':inserted,'same_capture_replay_inserted':False,
                           'canonical_load_equal':True,'original_record':original}
                receipts.append(receipt); atomic_write_json(output/'append-receipts'/(doc.document_id+'.json'),receipt)
                added_rows.append(_row(doc,original,proofs))
            new_review = deepcopy(review); new_review.pop('manifest_hash',None); new_review['records'].extend(added_rows)
            new_review['manifest_hash'] = canonical_json_hash(new_review)
            atomic_write_json(output/'source-review.json',new_review)
            view = materialize_reviewed_snapshot(output/'source-review.json',output/'snapshot')
            summaries = _consume(output,view,plan)
            _check(plan['source_bindings']+plan['code_bindings'])
            additions = financial._check_global(before,root,expected_paths)
            if canonical_json_hash(new_review['records'][:len(review['records'])]) != canonical_json_hash(review['records']):
                raise ReviewedSourceRejected('old complete review rows changed')
            result = {'status':'completed','plan_hash':plan['plan_hash'],'products':PRODUCTS,'new_capture_versions':CONFLICTS,
                'retained_legacy_products':PRODUCTS-CONFLICTS,'source_review':_binding(output/'source-review.json'),
                'reviewed_source_snapshot':view,'append_receipts':receipts,'global_additions':additions,
                'old_global_bytes_preserved':True,'old_review_rows_preserved':True,'snapshot_reopen_canonical_equal':True,
                'groups':summaries,'GETs':0,'models':0,'labels':False,'Signal_apply':False,'fullprepare':False,'MVP_closed':False}
            atomic_write_json(output/'input_manifest.json', {'plan':_binding(output/'plan.json'),
                'source_review':result['source_review'],'reviewed_source_snapshot':view,'case':plan['case'],'groups':plan['groups']})
            atomic_write_json(output/'result.json',result); return result
        except Exception as error:
            atomic_write_json(output/'failure.json',{'terminal':True,'retry_allowed':False,'error_type':type(error).__name__}); raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--prepare',action='store_true'); action.add_argument('--execute',action='store_true')
    parser.add_argument('--output',type=Path,default=DEFAULT_OUTPUT); parser.add_argument('--expected-plan-hash')
    args = parser.parse_args()
    prepare(args.output) if args.prepare else execute(args.output,args.expected_plan_hash)
