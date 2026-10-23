"""One fixed two-version deterministic diagnostic; no stable publication or model.

Prepare freezes code, approved definitions and independent source oracle without
executing real Signals. Execute consumes one irreversible batch allowance, saves
the native output before review, and never reenters a terminal attempt.
"""
from contextlib import ExitStack
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import socket
import ssl
import sys
from unittest.mock import patch

from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.cases.label_store import LabelStore
from stock_opportunity_agent.data.raw_info import RawInfoStore
from stock_opportunity_agent.data.resolution import EvidenceResolver
from stock_opportunity_agent.data.reviewed_snapshot import ReviewedRawInfoStore, open_raw_info_store
from stock_opportunity_agent.research.evolution_transport import StructuredRoleClient
from stock_opportunity_agent.signal_library import (
    FrozenSignalRegistry, SignalExecutor, SignalRegistry, SignalResult, SignalSpec,
    signal_result_model_view,
)

BASE = Path(__file__).resolve().parent
REPO = BASE.parents[2]
ORIGINAL = Path('/Users/l/Project/Recommandation')
OUT = BASE / 'native-approved'
REFS = ('gross_margin_change:v4', 'revenue_acceleration:v3')


def read(path):
    return json.loads(Path(path).read_bytes())


def binding(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def check(rows):
    for row in rows:
        if binding(row['path']) != row:
            raise ValueError('frozen binding changed: ' + row['path'])


def write_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write('\n')


def prepare():
    if OUT.exists():
        raise ValueError('prepare requires a new output directory')
    old = ORIGINAL / 'runs/diagnostics/current_financial_apply_20261021_v1/native/stage'
    previous = read(old / 'plan.json')
    specs_path = BASE / 'independent/new-version-specs.json'
    specs = read(specs_path)['specs']
    if tuple(SignalSpec.from_dict(s).ref for s in specs) != REFS:
        raise ValueError('fixed next-version scope differs')
    independent = [binding(p) for p in sorted((BASE / 'independent').glob('*')) if p.is_file()]
    source = read(BASE / 'independent/source-only-bindings.json')
    historical_code_path = str(REPO / 'src/stock_opportunity_agent/signal_library.py')
    historical_code = {'path': historical_code_path, 'sha256': source[historical_code_path]}
    # Source-only freeze also records the pre-implementation code identity. That
    # historical identity is retained, while current implementation binds separately.
    source_rows = [{'path': path, 'sha256': digest} for path, digest in source.items()
                   if path != historical_code_path]
    code = [binding(p) for p in sorted((REPO / 'src').rglob('*.py'))]
    code += [binding(__file__), binding(REPO / 'spec/src/stock_opportunity_agent/signal_library.md')]
    old_rows = [binding(p) for p in sorted(old.rglob('*')) if p.is_file()]
    check(source_rows)
    plan = dict(schema_version='approved-period-two-plan-v1', specs=specs,
        fixed_denominator=2, signal_refs=list(REFS), case=previous['case'],
        identity=previous['identity'], reviewed_source_snapshot=previous['reviewed_source_snapshot'],
        source_bindings=source_rows, code_bindings=code, old_completed_stage=old_rows,
        independent_bindings=independent, historical_code_binding=historical_code,
        prepared_at=datetime.now(timezone.utc).isoformat(),
        network=0, models=0, labels=0, append=0, batches_allowed=1,
        publication_allowed=False, business_pointer_advance_allowed=False,
        acceptance='One measured margin and one explicit missing-quarter unavailable, source oracle unchanged',
        consumer_scope='Saved roundtrip and public model projection only; no fresh model')
    plan['plan_hash'] = canonical_json_hash(plan)
    write_new(OUT / 'plan.json', plan)
    print(plan['plan_hash'])


def forbidden(*args, **kwargs):
    raise RuntimeError('forbidden network/model/label/append/publication operation')


def execute(expected_hash):
    plan = read(OUT / 'plan.json')
    payload = {k: v for k, v in plan.items() if k != 'plan_hash'}
    if canonical_json_hash(payload) != expected_hash or plan['plan_hash'] != expected_hash:
        raise ValueError('exact prepared plan hash required')
    for name in ('source_bindings', 'code_bindings', 'independent_bindings', 'old_completed_stage'):
        check(plan[name])
    if any((OUT / name).exists() for name in ('execution-start.json', 'native-batch.json', 'result.json', 'failure.json')):
        raise ValueError('terminal attempt cannot reenter')
    write_new(OUT / 'execution-start.json', {'at': datetime.now(timezone.utc).isoformat(), 'plan_hash': expected_hash})
    try:
        with ExitStack() as stack:
            for owner, name in ((socket, 'socket'), (socket, 'create_connection'),
                    (LabelStore, '__init__'), (LabelStore, 'load'), (LabelStore, 'record'),
                    (LabelStore, 'ground_truth'), (RawInfoStore, 'append'),
                    (ReviewedRawInfoStore, 'append'), (SignalRegistry, 'register_stable'),
                    (SignalRegistry, 'freeze'), (SignalExecutor, 'prepare_inputs')):
                stack.enter_context(patch.object(owner, name, forbidden))
            for name in ('complete_json', 'complete_json_with_token_scores', 'complete_binary_token_with_scores'):
                stack.enter_context(patch.object(StructuredRoleClient, name, forbidden))
            specs = tuple(SignalSpec.from_dict(s) for s in plan['specs'])
            snapshot = FrozenSignalRegistry(version=1,
                registry_hash=canonical_json_hash(plan['specs']), specs=specs, skills={})
            source = plan['reviewed_source_snapshot']
            store = open_raw_info_store(source['root'], reviewed_snapshot=source)
            before = canonical_json_hash([d.to_dict() for d in store.documents])
            if len(store.documents) != 1780:
                raise ValueError('reviewed source view differs')
            executor = SignalExecutor(snapshot, store, resolver=EvidenceResolver(store))
            batch = executor.execute_batch(REFS, company_id=plan['case']['company_id'],
                as_of=datetime.fromisoformat(plan['case']['prediction_time']), identity=plan['identity'])
            result = dict(results=[r.to_dict() for r in batch.results], signal_calls=batch.signal_calls,
                usage=asdict(batch.usage), resolutions=[r.to_dict() for r in batch.resolutions],
                document_fingerprints=dict(batch.document_fingerprints))
            write_new(OUT / 'native-batch.json', result)
            contracts = executor.classification_contracts_for(batch.results)
            write_new(OUT / 'classification-contracts.json', contracts)
            projections = []
            for r in batch.results:
                restored = SignalResult.from_dict(r.to_dict())
                if restored.to_dict() != r.to_dict():
                    raise ValueError('saved roundtrip differs')
                projections.append(signal_result_model_view(restored,
                    classification_contract=contracts.get(r.ref)))
            write_new(OUT / 'consumer-projections.json', projections)
            if before != canonical_json_hash([d.to_dict() for d in store.documents]):
                raise ValueError('source view mutated')
        for name in ('source_bindings', 'code_bindings', 'independent_bindings', 'old_completed_stage'):
            check(plan[name])
        if tuple(r.ref for r in batch.results) != REFS or batch.signal_calls != 2:
            raise ValueError('fixed two-result scope differs')
        final = dict(status='completed_pending_independent_semantic_review', plan_hash=expected_hash,
            fixed_denominator=2, native_batches=1, signal_calls=2,
            signal_calls_semantics='Native result count, not instrumented callable invocations',
            source_documents=1780, originals_unchanged=True, network=0, models=0,
            labels=0, append=0, publication=0, business_pointer_advance=0)
        write_new(OUT / 'result.json', final)
        print(json.dumps(final))
    except Exception as exc:
        write_new(OUT / 'failure.json', {'type': type(exc).__name__, 'error': str(exc)})
        raise


if __name__ == '__main__':
    if sys.argv[1:] == ['prepare']:
        prepare()
    elif len(sys.argv) == 3 and sys.argv[1] == 'execute':
        execute(sys.argv[2])
    else:
        raise SystemExit('prepare | execute EXACT_PLAN_HASH')
