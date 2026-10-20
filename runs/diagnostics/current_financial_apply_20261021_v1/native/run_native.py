"""One independently frozen financial9 native batch; never a research/model run.

Prepare computes no Signal. Execute reserves one irreversible attempt, persists every
returned native result before acceptance checks, and never retries oracle failures.
Restore verifies exact saved bytes only; it is not OS-crash/research recovery.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager, ExitStack
from datetime import datetime, timezone
from dataclasses import asdict
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import socket
import ssl  # Initialize socket classes before the prohibition patches.
import subprocess
from unittest.mock import patch

from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.cases.label_store import LabelStore
from stock_opportunity_agent.data.raw_info import RawInfoStore
from stock_opportunity_agent.data.resolution import EvidenceResolver
from stock_opportunity_agent.data.reviewed_snapshot import open_raw_info_store, ReviewedRawInfoStore
from stock_opportunity_agent.research.evolution_transport import StructuredRoleClient
from stock_opportunity_agent.signal_library import (
    SignalExecutor, SignalRegistry, SignalResult, signal_result_model_view,
)
import run_minimal_rounds

REPO = Path(__file__).resolve().parents[4]
NATIVE = Path(__file__).resolve().parent
OUTPUT = NATIVE / 'stage'
ORACLE = NATIVE.parent / 'oracle'
ORACLE_MANIFEST_SHA = '475f89606878bdc808fcdcc34e8890a2e937c29f680ade1450211f6e69db595e'
ORACLE_HASH = 'ea0331399f394c7e8bc3c67877262ec6dd9c77febbb6da20d4cfc3e2f6f881e5'
INPUTS = REPO / 'runs/diagnostics/measurement_input_selection_20261021_v1'
UNIT_LABELS = {'dimensionless ratio': 'ratio', 'dimensionless fraction': 'fraction'}


def read(path):
    return json.loads(Path(path).read_text())


def binding(path):
    path = Path(path).resolve()
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return {'path': str(path), 'sha256': digest.hexdigest()}


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as handle:
        json.dump(value, handle, sort_keys=True, indent=2, allow_nan=False)
        handle.write('\n'); handle.flush(); os.fsync(handle.fileno())


def check(bindings):
    for item in bindings:
        if binding(item['path']) != {'path': str(Path(item['path']).resolve()), 'sha256': item['sha256']}:
            raise ValueError('frozen file differs: ' + item['path'])


def tree(root):
    root = Path(root)
    return {'directories': sorted(str(p.relative_to(root)) for p in root.rglob('*') if p.is_dir()),
            'files': [binding(p) for p in sorted(root.rglob('*')) if p.is_file()]}


def unique(items):
    result = {}
    for item in items:
        old = result.setdefault(item['path'], item)
        if old != item:
            raise ValueError('conflicting frozen binding: ' + item['path'])
    return [result[key] for key in sorted(result)]


def head():
    return subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip()


@contextmanager
def bounded_operations(*, allow_batch=False):
    """Actual no-network/no-label/no-write/model guards, with one batch allowance."""
    calls = {'batches': 0}
    native_batch = SignalExecutor.execute_batch
    native_store_init = RawInfoStore.__init__
    def forbidden(*args, **kwargs):
        raise RuntimeError('forbidden network/model/label/acquisition/append/fullprepare operation')
    def memory_only_init(self, root=None, documents=()):
        if root is not None or tuple(documents):
            raise RuntimeError('persistent or prepopulated RawInfoStore construction forbidden')
        native_store_init(self)
    def once(self, refs, **kwargs):
        refs = tuple(refs)
        if not allow_batch or calls['batches'] or len(refs) != 9 or len(set(refs)) != 9:
            raise RuntimeError('native batch allowance exhausted or scope differs')
        calls['batches'] += 1
        return native_batch(self, refs, **kwargs)
    with ExitStack() as stack:
        for owner, name in ((socket, 'socket'), (socket, 'create_connection'),
                (LabelStore, '__init__'), (LabelStore, 'load'), (LabelStore, 'record'), (LabelStore, 'ground_truth'),
                (RawInfoStore, 'append'),
                (ReviewedRawInfoStore, 'append'), (run_minimal_rounds, 'prepare'),
                (SignalExecutor, 'prepare_inputs'), (SignalRegistry, 'freeze'),
                (SignalRegistry, 'register_stable')):
            stack.enter_context(patch.object(owner, name, forbidden))
        for name in ('complete_json', 'complete_json_with_token_scores', 'complete_binary_token_with_scores'):
            stack.enter_context(patch.object(StructuredRoleClient, name, forbidden))
        stack.enter_context(patch.object(RawInfoStore, '__init__', memory_only_init))
        stack.enter_context(patch.object(SignalExecutor, 'execute_batch', once))
        yield calls


def readonly_snapshot(group, candidate_root):
    """All constructor directories must already exist; constructor cannot mutate bytes."""
    registry_root, candidate_root = Path(group['root']), Path(candidate_root)
    if not registry_root.is_dir() or not candidate_root.is_dir() or not (registry_root / 'registry.json').is_file():
        raise ValueError('readonly Registry constructor directories/files must already exist')
    before = [tree(registry_root), tree(candidate_root)]
    registry = SignalRegistry(registry_root, candidate_root=candidate_root)
    snapshot = registry.snapshot_from_refs(group['version'], tuple(group['refs']))
    if before != [tree(registry_root), tree(candidate_root)]:
        raise ValueError('readonly Registry construction changed tree')
    if snapshot.registry_hash != group['registry_hash'] or len(snapshot.specs) != 18:
        raise ValueError('exact original18 Registry snapshot differs')
    return snapshot


def verify_group_identity(group, original):
    """Compare exact snapshot identity; separately verify historical definition bytes."""
    fields = ('name','refs','registry_hash','root','version')
    if (set(group) != set(fields) or canonical_json_hash(group) != canonical_json_hash(
            {key:original[key] for key in fields})):
        raise ValueError('exact original latest_v12 group identity differs')
    check(original['definition_bindings'])
    return original['definition_bindings']


def authorities():
    manifest_path = ORACLE / 'frozen-manifest.json'
    manifest = read(manifest_path)
    if binding(manifest_path)['sha256'] != ORACLE_MANIFEST_SHA:
        raise ValueError('fixed oracle manifest bytes differ')
    if manifest.get('manifest_hash') != ORACLE_HASH or canonical_json_hash(
            {k:v for k,v in manifest.items() if k != 'manifest_hash'}) != ORACLE_HASH:
        raise ValueError('fixed independent oracle canonical hash differs')
    check(manifest['files'])
    oracle, definitions, audit = (read(ORACLE / name) for name in ('oracle.json', 'definitions.json', 'binding-audit.json'))
    rows = oracle['rows']
    if (len(rows) != 9 or len({r['signal_ref'] for r in rows}) != 9
            or sum(r['oracle_status'] == 'sufficient_unique' for r in rows) != 7
            or sum(r['oracle_status'] == 'period_policy_ambiguous' for r in rows) != 2):
        raise ValueError('fixed9/7/2 oracle scope differs')
    old = read(INPUTS / 'plan.json')
    group = definitions['group']
    original_group = next(g for g in old['groups'] if g['name'] == 'latest_v12')
    definitions_bound = verify_group_identity(group, original_group)
    if [r['signal_ref'] for r in rows] != [r for r in group['refs'] if r in {x['signal_ref'] for x in rows}]:
        raise ValueError('financial9 order differs from original18')
    # Old code bindings remain historical: freeze old plan bytes; separately bind
    # current code. Do not require historical code to equal current implementation.
    sources = []
    for item in old['bindings'] + audit['bindings']:
        path = Path(item['path'])
        if any(path.is_relative_to(REPO / base) for base in ('src', 'scripts', 'spec')):
            continue
        sources.append({'path': item['path'], 'sha256': item['sha256']})
    sources += definitions_bound + manifest['files'] + [binding(manifest_path), binding(INPUTS / 'plan.json'),
                binding(INPUTS / 'latest_v12.json')]
    sources = unique(sources)
    check(sources)
    codes = [binding(p) for p in sorted((REPO / 'src').rglob('*.py'))]
    codes += [binding(p) for p in sorted((REPO / 'spec').rglob('*.md'))]
    codes += [binding(Path(__file__)), binding(REPO / 'scripts/run_minimal_rounds.py')]
    return {'oracle': oracle, 'group': group, 'case': old['case'], 'identity': old['identity'],
            'reviewed_source_snapshot': old['reviewed_source_snapshot'],
            'source_bindings': sources, 'code_bindings': unique(codes)}


def verify(output):
    output = Path(output).resolve()
    if output != OUTPUT.resolve():
        raise ValueError('fixed fresh diagnostic output differs')
    plan = read(output / 'plan.json')
    if plan['output'] != str(output) or plan['plan_hash'] != canonical_json_hash({k:v for k,v in plan.items() if k != 'plan_hash'}):
        raise ValueError('plan output/hash differs')
    if plan['limits'] != {'batches':1, 'signal_calls':9, 'model_calls':0, 'network_calls':0, 'label_reads':0}:
        raise ValueError('fixed bounded allowance differs')
    check(plan['source_bindings'] + plan['code_bindings'])
    subprocess.run(['git','merge-base','--is-ancestor',plan['head'],head()], cwd=REPO, check=True)
    return plan


def prepare(output):
    output = Path(output).resolve()
    if output != OUTPUT.resolve() or output.exists():
        raise ValueError('prepare requires the fixed previously nonexistent output')
    with bounded_operations():
        frozen = authorities()  # No writes until all protected authorities validate.
        output.mkdir()
        write_new(output / 'preparation-start.json', {'at':datetime.now(timezone.utc).isoformat(), 'head':head()})
        try:
            candidates = output / 'readonly-candidates'
            candidates.mkdir()
            snapshot = readonly_snapshot(frozen['group'], candidates)
            refs = [r['signal_ref'] for r in frozen['oracle']['rows']]
            if any(snapshot.load_spec(ref).execution_type.value != 'deterministic' for ref in refs):
                raise ValueError('financial9 contains a non-deterministic Signal')
            plan = {**frozen, 'head':head(), 'output':str(output), 'signal_refs':refs,
                'unit_label_equivalence': UNIT_LABELS,
                'limits': {'batches':1, 'signal_calls':9, 'model_calls':0, 'network_calls':0, 'label_reads':0},
                'oracle_manifest_hash':ORACLE_HASH,
                'read_semantics':'Input/source/definition bytes frozen; old code historical; no Signal computed.'}
            plan['plan_hash'] = canonical_json_hash(plan)
            write_new(output / 'plan.json', plan)
            return {'status':'prepared','plan':binding(output/'plan.json'),'plan_hash':plan['plan_hash'],
                    'source_count':len(plan['source_bindings']),'code_count':len(plan['code_bindings']), 'fixed_denominator':9}
        except Exception as exc:
            write_new(output / 'preparation-failure.json', {'error_type':type(exc).__name__, 'error':str(exc)})
            raise


def compare(oracle, result):
    """No result-driven oracle changes; only prelisted duplicate literal alternatives."""
    if oracle['oracle_status'] == 'period_policy_ambiguous':
        return {'signal_ref':oracle['signal_ref'], 'status':'record_only_period_policy_ambiguous', 'passed':None}
    measurement = result.get('measurement') or {}
    period = measurement.get('period') or {}
    expected_period = oracle['measurement_period']
    value = measurement.get('value')
    numeric = (type(value) in (int,float) and math.isfinite(value)
               and abs(Decimal(str(value)) - Decimal(oracle['expected_numeric']['decimal']))
               <= Decimal(oracle['numeric_comparison_policy']['raw_numeric_absolute_tolerance']))
    evidence = result.get('evidence', {})
    actual = {(e['document_id'],e['exact_span']) for kind in ('supporting','counter') for e in evidence.get(kind, [])}
    matches = []
    for operand in oracle['operands']:
        alternatives = [operand] + [a for a in oracle.get('current_period_alternatives', [])
            if canonical_json_hash({k:a.get('fact',{}).get(k) for k in ('taxonomy','tag','unit','start','end','value')})
            == canonical_json_hash({k:operand['fact'].get(k) for k in ('taxonomy','tag','unit','start','end','value')})]
        matches.append(any((a['document_id'],a['literal']) in actual for a in alternatives))
    checks = {'execution_success':result.get('execution',{}).get('status') == 'success',
        'state':result.get('state',{}).get('value') == oracle['expected_state'],
        'unit':measurement.get('unit') == UNIT_LABELS.get(oracle['unit'],oracle['unit']),
        'period':period.get('start') == expected_period['start'] and period.get('end') == expected_period['end'],
        'numeric_raw_tolerance':bool(numeric), 'whole_operand_literals':all(matches)}
    return {'signal_ref':oracle['signal_ref'], 'status':'passed' if all(checks.values()) else 'failed',
            'passed':all(checks.values()),'checks':checks,'operand_matches':matches}


def serialize_batch(batch):
    return {'results':[r.to_dict() for r in batch.results], 'signal_calls':batch.signal_calls,
        'usage':asdict(batch.usage), 'resolutions':[r.to_dict() for r in batch.resolutions],
        'document_fingerprints':dict(batch.document_fingerprints),
        'skipped_unchanged_refs':list(batch.skipped_unchanged_refs)}


def execute(output, expected_plan_hash):
    output = Path(output).resolve()
    plan = verify(output)  # No marker before a valid fixed plan.
    if plan['plan_hash'] != expected_plan_hash:
        raise ValueError('expected frozen plan hash differs')
    if any((output/name).exists() for name in ('execution-start.json','result.json','failure.json')):
        raise ValueError('attempt is terminal; reentry forbidden')
    write_new(output/'execution-start.json', {'at':datetime.now(timezone.utc).isoformat(),'head':head(),'pid':os.getpid()})
    try:
        with bounded_operations(allow_batch=True) as calls:
            snapshot = readonly_snapshot(plan['group'],output/'readonly-candidates')
            source = plan['reviewed_source_snapshot']
            store = open_raw_info_store(source['root'],reviewed_snapshot=source)
            before = canonical_json_hash([d.to_dict() for d in store.documents])
            if len(store.documents) != 1780:
                raise ValueError('qualified source view must contain1780 documents')
            executor = SignalExecutor(snapshot,store,resolver=EvidenceResolver(store))
            batch = executor.execute_batch(tuple(plan['signal_refs']),company_id=plan['case']['company_id'],
                as_of=datetime.fromisoformat(plan['case']['prediction_time']),identity=plan['identity'])
            payload = serialize_batch(batch)
            write_new(output/'native-batch.json',payload)  # Preserve before any acceptance assertion.
            cutoff = datetime.fromisoformat(plan['case']['prediction_time'])
            for index, raw in enumerate(payload['results']):
                write_new(output/'results'/f'{index:02d}.json',raw)
            comparisons, consumer_checks = [], []
            for index, (oracle, result) in enumerate(zip(plan['oracle']['rows'],batch.results,strict=True)):
                raw = result.to_dict()
                equal = False
                try:
                    restored = SignalResult.from_dict(raw)
                    equal = canonical_json_hash(restored.to_dict()) == canonical_json_hash(raw)
                    model_view = signal_result_model_view(restored,as_of=cutoff)
                    write_new(output/'consumer-projections'/f'{index:02d}.json',model_view)
                    # The public producer's metadata location is persisted as-is;
                    # canonical measurement and execution remain exact top-level fields.
                    projection_equal = (canonical_json_hash(model_view.get('measurement')) == canonical_json_hash(raw.get('measurement'))
                        and model_view.get('execution',{}).get('status') == raw.get('execution',{}).get('status')
                        and model_view.get('state') == raw.get('state'))
                    consumer_checks.append({'signal_ref':result.ref,'saved_restore_equal':equal,'projection_fields_equal':projection_equal})
                except Exception as exc:
                    write_new(output/'consumer-projections'/f'{index:02d}-error.json',{'error_type':type(exc).__name__,'error':str(exc)})
                    consumer_checks.append({'signal_ref':result.ref,'saved_restore_equal':equal,'projection_fields_equal':False})
                try:
                    comparisons.append(compare(oracle,raw))
                except Exception as exc:
                    comparisons.append({'signal_ref':oracle['signal_ref'],'passed':False,'status':'comparison_error',
                        'error_type':type(exc).__name__,'error':str(exc)})
            same = before == canonical_json_hash([d.to_dict() for d in store.documents])
            check(plan['source_bindings']+plan['code_bindings'])
            complete = (len(payload['results']) == 9 and batch.signal_calls == 9 and calls['batches'] == 1
                and [r.ref for r in batch.results] == plan['signal_refs'] and same
                and all(c['saved_restore_equal'] and c['projection_fields_equal'] for c in consumer_checks))
            accepted = complete and all(c['passed'] is not False for c in comparisons)
            result = {'status':'completed' if accepted else 'completed_acceptance_failed',
                'plan_hash':plan['plan_hash'],'head':head(),'fixed_denominator':9,'sufficient_unique':7,
                'period_policy_ambiguous':2,'passed_unique':sum(c['passed'] is True for c in comparisons),
                'comparisons':comparisons,'consumer_checks':consumer_checks,'native_batches':calls['batches'],
                'signal_calls':batch.signal_calls,'signal_calls_semantics':'Native result count, not an instrumented callable invocation count.',
                'sources_definitions_oracle_unchanged':True,
                'source_documents_canonical_unchanged':same,'native_batch':binding(output/'native-batch.json'),
                'models':0,'GET':0,'labels':0,'append':0,
                'consumer_scope':'Saved result.from_dict and public model projection only; no fresh model consumption.',
                'at':datetime.now(timezone.utc).isoformat()}
            write_new(output/'result.json',result)
            write_new(output/'completed-files.json',tree(output))
            return result
    except Exception as exc:
        write_new(output/'failure.json',{'status':'terminal_technical_failure','error_type':type(exc).__name__,
            'error':str(exc),'at':datetime.now(timezone.utc).isoformat()})
        raise


def restore(output):
    output = Path(output).resolve()
    with bounded_operations():
        verify(output)
        seal = read(output/'completed-files.json')
        current = tree(output)
        current['files'] = [b for b in current['files'] if Path(b['path']) != output/'completed-files.json']
        if canonical_json_hash(current) != canonical_json_hash(seal):
            raise ValueError('completed immutable inventory differs')
        result = read(output/'result.json')
        return {'restored_without_execution':True,'result':result,'new_batches':0,
                'scope':'Exact saved byte verification only; not OS-crash/research recovery.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('prepare','execute','restore'))
    parser.add_argument('--output',type=Path,default=OUTPUT)
    parser.add_argument('--expected-plan-hash')
    args = parser.parse_args()
    if args.command == 'prepare':
        result = prepare(args.output)
    elif args.command == 'execute':
        result = execute(args.output,args.expected_plan_hash)
    else:
        result = restore(args.output)
    print(json.dumps(result,sort_keys=True))


if __name__ == '__main__':
    main()
