#!/usr/bin/env python3
"""Freeze a five-original market view and consume its real UTC runtime baseline."""
from __future__ import annotations

from stock_opportunity_agent.research.basic_info_orientation import compile_basic_info_requests

import argparse
from datetime import datetime, timedelta
import json
from pathlib import Path
import socket
from types import SimpleNamespace

from diagnose_reviewed_source_snapshot import _binding, restore_inputs
from stock_opportunity_agent.artifacts import atomic_write_json, canonical_json_hash
from stock_opportunity_agent.data.raw_info import RawInfoDocument
from stock_opportunity_agent.data.resolution import DataAcquisitionPolicy, RawInfoRequest
from stock_opportunity_agent.data.reviewed_snapshot import materialize_reviewed_snapshot, ReviewedSourceRejected
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_control import _build_evidence_resolver
from stock_opportunity_agent.research.evolution_core import default_information_plan, project_basic_info_bundle, _prediction_baseline_from_market_documents

REPO = Path(__file__).resolve().parents[1]
OLD_SEC_INPUT = REPO / 'runs/diagnostics/reviewed_source_snapshot_20261019_v3/input_manifest.json'
TIMEZONE_FAILURE = REPO / 'runs/diagnostics/market_baseline_timezone_boundary_20261019_v1/result.json'


def diagnose(review_path: Path, output: Path):
    """Verify one new view without altering old originals or calling any model."""
    if output.exists():
        raise ReviewedSourceRejected('diagnostic output must be new')
    review = json.loads(review_path.read_bytes())
    originals = [_binding(row['original_record']['path']) for row in review['records']]
    old_binding = json.loads(OLD_SEC_INPUT.read_bytes())['reviewed_source_snapshot']
    old_root = Path(old_binding['root'])
    old_files = [_binding(p) for p in sorted(old_root.rglob('*.json'))]
    binding = materialize_reviewed_snapshot(review_path, output / 'snapshot')
    atomic_write_json(output / 'snapshot_binding.json', binding)
    inputs = {'schema_version':'narrow-reviewed-market-inputs-v1','source_review':_binding(review_path),
        'reviewed_source_snapshot':binding,'fixed_source_denominator':len(review['records']),
        'scope':review['scope'],'full_approved_dataset_freeze':False,'model_calls_authorized':False}
    atomic_write_json(output / 'input_manifest.json', inputs)
    digest = canonical_json_hash(inputs)
    store = restore_inputs(output / 'input_manifest.json', digest)
    worker = store.snapshot()
    resolver = _build_evidence_resolver(output / 'runtime', worker,
        contract=SimpleNamespace(data_acquisition=DataAcquisitionPolicy()), allow_data_external=False, environ={}, cycle_id=1)
    cutoff = datetime.fromisoformat(review['scope']['as_of'])
    markets = [d for d in store.documents if d.source_type == 'market_data']
    if len(markets) != 1:
        raise ReviewedSourceRejected('this diagnostic expects exactly one scoped original market record')
    market = markets[0]
    identity = {'ticker':market.metadata['symbol']}
    bundle = resolver.resolve_basic_info(compile_basic_info_requests(default_information_plan().basic_info_policy),
        company_id=market.company_id, identity=identity, as_of=cutoff)
    model, lineage = project_basic_info_bundle(bundle)
    market_docs = tuple(d for result in bundle.requests if 'market_data' in result.request.source_types
        for d in resolver.load_documents(result, as_of=cutoff))
    baseline = _prediction_baseline_from_market_documents(market_docs, cutoff)
    atomic_write_json(output / 'basic_info.json', {'bundle':bundle.to_dict(),'model_context':model,'lineage':lineage})
    atomic_write_json(output / 'runtime_baseline.json', baseline)
    rows = []
    for row in review['records']:
        if row['verdict'] == 'admitted':
            doc = store.load(row['document_id'], as_of=cutoff)
            original = json.loads(Path(row['original_record']['path']).read_bytes())
            try:
                store.load(doc.document_id, as_of=doc.available_at-timedelta(seconds=1))
                before_rejected=False
            except ValidationError:
                before_rejected=True
            rows.append({'document_id':doc.document_id,'verdict':'admitted','whole_record_equal':doc.to_dict()==original,
                'before_available_rejected':before_rejected,'at_available_equal':store.load(doc.document_id,as_of=doc.available_at)==doc,
                'idempotent_replay_added':worker.append(doc)})
        else:
            original=RawInfoDocument.from_dict(json.loads(Path(row['original_record']['path']).read_bytes()))
            resolution=resolver.resolve(RawInfoRequest('unadmitted-'+row['verdict'],'Read scoped original source.',(original.source_type,)),
                company_id=original.company_id,identity=identity,as_of=cutoff)
            try:
                worker.append(original)
                append_rejected=False
            except ReviewedSourceRejected:
                append_rejected=True
            rows.append({'document_id':original.document_id,'verdict':row['verdict'],'is_gap':resolution.gap is not None,
                'append_rejected':append_rejected,'negative_company_observation':False})
    restored = restore_inputs(output / 'input_manifest.json', digest)
    old_store = restore_inputs(OLD_SEC_INPUT, canonical_json_hash(json.loads(OLD_SEC_INPUT.read_bytes())))
    proof_bindings={p['artifact']['path']:p['artifact'] for row in review['records'] for p in row['proofs']}
    proof_bindings.update({p['request_record']['path']:p['request_record'] for row in review['records']
        for p in row['proofs'] if 'request_record' in p})
    result={'schema_version':'reviewed-market-snapshot-diagnostic-v1','input_manifest_hash':digest,
        'fixed_source_denominator':len(review['records']),'outcomes':rows,'reviewed_source_snapshot':binding,
        'original_bindings':originals,'proof_bindings':list(proof_bindings.values()),
        'source_records_unchanged':originals==[_binding(row['original_record']['path']) for row in review['records']],
        'admitted_document_ids':[d.document_id for d in store.documents],
        'restored_whole_records_equal':restored.documents==store.documents,
        'worker_preserves_review_type':type(worker) is type(store),
        'old_sec_view_unchanged':old_files==[_binding(p) for p in sorted(old_root.rglob('*.json'))],
        'old_sec_view_only_filings':len(old_store.documents)==2 and all(d.source_type=='filing' for d in old_store.documents),
        'default_market_request_resolved':any(r.request.request_id=='orientation.v1.market_backbone' and r.status=='resolved' for r in bundle.requests),
        'runtime_baseline':baseline,'runtime_baseline_source_ids':[d.document_id for d in market_docs],
        'actual_market_bar_count':len(json.loads(market.content)),
        'basic_info_market_visibility':[{'request_id':r.request.request_id,
            'upstream_coverage':r.coverage.to_dict(),
            'model_projection':next(m for m in model['requests'] if m['request']['request_id']==r.request.request_id)}
            for r in bundle.requests if 'market_data' in r.request.source_types],
        'basic_info_market_visibility_family_closed':False,
        'known_baseline_timezone_failure':_binding(TIMEZONE_FAILURE),
        'baseline_day_boundary_family_closed':False,'full_factory_zero_external_preflight_proven':False,
        'full_preflight_executed':False,'full_dataset_readiness_proven':False,'new_model_responses':0,
        'external_llm_calls':0,'readonly_data_requests':0,'engineering_mvp_closed':False,
        'code_bindings':[_binding(p) for p in sorted([*(REPO/'src').rglob('*.py'),Path(__file__),
            REPO/'scripts/diagnose_reviewed_source_snapshot.py'])]}
    result['narrow_source_checks_passed']=(len(rows)==5 and len(store.documents)==3
        and result['source_records_unchanged'] and result['restored_whole_records_equal'] and result['worker_preserves_review_type']
        and result['old_sec_view_unchanged'] and result['old_sec_view_only_filings'] and market_docs==(market,)
        and result['default_market_request_resolved'] and baseline['status']=='available'
        and all((r['whole_record_equal'] and r['before_available_rejected'] and r['at_available_equal'] and not r['idempotent_replay_added'])
            if r['verdict']=='admitted' else (r['is_gap'] and r['append_rejected']) for r in rows))
    atomic_write_json(output/'result.json',result)
    return result


def main():
    """Run one new local source diagnostic with network use forbidden."""
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--review',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    def forbidden(*_args,**_kwargs):
        raise AssertionError('network forbidden in reviewed market diagnostic')
    socket.socket=forbidden
    result=diagnose(args.review.resolve(),args.output.resolve())
    print(json.dumps({k:v for k,v in result.items() if k not in {'outcomes','original_bindings','proof_bindings','code_bindings'}},indent=2))


if __name__=='__main__':
    main()
