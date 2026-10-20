"""One source-only S1 export/materialization; not a new Fast/Slow run.

Execute only after the expected committed revision/control/script SHAs are supplied.
Retrospective committed source reads are authorized; fixture audits, Signals,
models, labels, network, source writes and new execution contracts are not.
Every attempted export is terminal. No automatic retry or alternate source.
"""
from __future__ import annotations

import argparse
import builtins
from contextlib import ExitStack, contextmanager
from dataclasses import replace
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
from time import monotonic
from unittest.mock import patch

sys.dont_write_bytecode = True
from stock_opportunity_agent import artifacts, signal_library as library
from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.cases.label_store import LabelStore
from stock_opportunity_agent.data.raw_info import RawInfoStore
from stock_opportunity_agent.memory import knowledge
from stock_opportunity_agent.research import evolution_control as control
from stock_opportunity_agent.research.evolution_transport import StructuredRoleClient
import run_minimal_rounds

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
SOURCE = REPO / 'runs/cold_start/minimal_rounds_v182_integrated'
STAGE = ROOT / 'stage'
CONTROL = REPO / 'src/stock_opportunity_agent/research/evolution_control.py'
REAL_OPEN = builtins.open
SOURCE_AUTHORITY_SHAS = {
    'run_contract.json': '5789b5a8512556b614949b3705ced68968aeec78df801e2912f008369a700d81',
    'state.json': 'e2cb3bbef7bfcfa62c4a1c218c181ac49796e6ebbd94851224ddbe1ed8dc2de9',
    'cycle_state.json': '5619ac234153d2946c4d186e18a04043d4bf7e0739ae75859a6c91180fb00bf6',
    'signals/registry.json': '41da62a18a371e11376933fb7dfe57f22440f3129467e2248a8c5d45d63ee0f4',
}


def sha(path):
    with REAL_OPEN(path, 'rb') as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    with Path(path).open('x') as handle:
        json.dump(value, handle, sort_keys=True, indent=2)
        handle.write('\n'); handle.flush(); os.fsync(handle.fileno())


def file_inventory(root):
    return [{'path': str(path), 'sha256': sha(path)} for path in sorted(root.rglob('*')) if path.is_file()]


class ScopeStop(RuntimeError):
    """An undeclared read/write is terminal, never permission to expand scope."""


@contextmanager
def source_only():
    """Permit writes only to this new stage, and only declared S1 source reads."""
    record = {'reads': {}, 'blocked_reads': [], 'blocked_writes': [], 'existing_mkdir': [], 'forbidden_calls': 0}
    permitted = {SOURCE / name for name in ('run_contract.json', 'state.json', 'cycle_state.json')}
    namespace_reads = False
    candidate_ids = set()
    def normalized(path):
        return None if isinstance(path, int) else Path(os.fsdecode(path)).resolve()
    def readable(value):
        path = normalized(value)
        if path is None:
            return
        if any('locked_test' in part.casefold() or 'locked-test' in part.casefold() for part in path.parts):
            record['blocked_reads'].append(str(path))
            raise ScopeStop('Locked Test read forbidden')
        if path.is_relative_to(STAGE):
            return
        if path.is_relative_to(REPO / 'runs'):
            rel = path.relative_to(SOURCE) if path.is_relative_to(SOURCE) else None
            allowed = rel is not None and (
                path in permitted or rel.parts[0] == 'signals'
                or (namespace_reads and rel.parts[0] == 'slow_history')
                or (len(rel.parts) >= 4 and rel.parts[0] == 'signals_candidates' and rel.parts[2] in candidate_ids))
            if not allowed:
                record['blocked_reads'].append(str(path))
                raise ScopeStop('source read outside committed S1 prefix: ' + str(path))
            item = record['reads'].setdefault(str(path), {'sha256_before': sha(path), 'opens': 0})
            item['opens'] += 1
    def writable(value):
        path = normalized(value)
        if path is not None and not path.is_relative_to(STAGE):
            record['blocked_writes'].append(str(path))
            raise ScopeStop('source/global/outside-stage write blocked: ' + str(path))
    def forbidden(*args, **kwargs):
        record['forbidden_calls'] += 1
        raise ScopeStop('forbidden fresh freeze/audit/Signal/model/network/label/promotion/fullprepare')
    old_io, old_os_open, old_mkdir = io.open, os.open, os.mkdir
    def opened(file, mode='r', *args, **kwargs):
        (writable if any(c in mode for c in 'wax+') else readable)(file)
        return REAL_OPEN(file, mode, *args, **kwargs)
    def io_opened(file, mode='r', *args, **kwargs):
        (writable if any(c in mode for c in 'wax+') else readable)(file)
        return old_io(file, mode, *args, **kwargs)
    def os_opened(file, flags, *args, **kwargs):
        (writable if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND) else readable)(file)
        return old_os_open(file, flags, *args, **kwargs)
    def mkdir(path, *args, **kwargs):
        resolved = normalized(path)
        if not resolved.is_relative_to(STAGE) and resolved.is_dir():
            record['existing_mkdir'].append(str(resolved)); raise FileExistsError(str(resolved))
        writable(path); return old_mkdir(path, *args, **kwargs)
    def declare(contract):
        """Resolve only pointer-declared metadata; native validators still judge it."""
        nonlocal namespace_reads
        state, cycle = read(SOURCE / 'state.json'), read(SOURCE / 'cycle_state.json')
        if state.get('last_completed_round') != 1 or cycle.get('last_completed_cycle') != 1 or cycle.get('active_cycle') is not None:
            raise ScopeStop('fixed committed source pointers differ')
        checkpoint = SOURCE / 'experiments/round-0001/checkpoint.json'
        permitted.add(checkpoint); cp = read(checkpoint)
        if cp.get('round_id') != 1 or cp.get('run_contract_hash') != contract.contract_hash:
            raise ScopeStop('committed checkpoint authority differs')
        permitted.add(SOURCE / 'meta/round-0001.json')
        for plan_id in cp['plan_ids']:
            path = SOURCE / 'plans' / plan_id / 'record.json'; permitted.add(path)
            raw = read(path)
            if raw.get('round_id') != 1 or raw.get('plan_id') != plan_id:
                raise ScopeStop('record outside committed round1')
            permitted.add(SOURCE / 'knowledge/observations' / (canonical_json_hash(raw) + '.json'))
        for kind in ('slow_history', 'slow_bootstrap'):
            expected = getattr(contract, kind + '_manifest_hash')
            if expected:
                path = SOURCE / kind / 'manifest.json'; permitted.add(path)
                envelope = read(path)
                if envelope.get('manifest_hash') != expected or canonical_json_hash(envelope.get('manifest')) != expected:
                    raise ScopeStop('source imported-history authority differs')
                if kind == 'slow_history':
                    namespace_reads = True  # Existing immutable imported namespaces carried by native apply.
        for name in ('slow_input.json', 'slow_memory.json', 'slow_experiments.json', 'slow_loop_validation.json', 'slow_loop_result.json'):
            permitted.add(SOURCE / 'experiments/cycles/cycle-0001' / name)
        attempts = read(SOURCE / 'experiments/cycles/cycle-0001/slow_experiments.json').get('attempts', [])
        validation = read(SOURCE / 'experiments/cycles/cycle-0001/slow_loop_validation.json')
        refs = [row.get('candidate_ref') for row in attempts if isinstance(row, dict)]
        refs += list(validation.get('validation', {}).get('candidate_effectiveness', {}))
        candidate_ids.update(ref.rsplit(':', 1)[0] for ref in refs if isinstance(ref, str) and ':' in ref)
    with ExitStack() as stack:
        for owner, name, replacement in ((builtins, 'open', opened), (io, 'open', io_opened), (os, 'open', os_opened), (os, 'mkdir', mkdir)):
            stack.enter_context(patch.object(owner, name, replacement))
        for name in ('rename', 'replace', 'unlink', 'remove', 'rmdir'):
            original = getattr(os, name)
            def guarded(*args, _name=name, _original=original, **kwargs):
                for path in args[:2] if _name in ('rename', 'replace') else args[:1]: writable(path)
                return _original(*args, **kwargs)
            stack.enter_context(patch.object(os, name, guarded))
        for owner, name in ((artifacts, 'atomic_write_json'), (knowledge, 'atomic_write_json'), (library, '_atomic_write_json')):
            original = getattr(owner, name)
            def atomic(path, *args, _original=original, **kwargs):
                writable(path); return _original(path, *args, **kwargs)
            stack.enter_context(patch.object(owner, name, atomic))
        for owner, name in ((socket, 'socket'), (socket, 'create_connection'), (RawInfoStore, '__init__'),
                (LabelStore, '__init__'), (LabelStore, 'load'), (LabelStore, 'record'), (LabelStore, 'ground_truth'),
                (library.SignalRegistry, 'freeze'), (library.SignalRegistry, 'audit_capabilities'),
                (library.SignalRegistry, 'promote_validated_batch'), (library.SignalExecutor, 'execute_batch'),
                (library.SignalExecutor, 'prepare_inputs'), (library, '_audit_deterministic_fixture'), (run_minimal_rounds, 'prepare')):
            stack.enter_context(patch.object(owner, name, forbidden))
        for name in ('complete_json', 'complete_json_with_token_scores', 'complete_binary_token_with_scores'):
            stack.enter_context(patch.object(StructuredRoleClient, name, forbidden))
        for function in library.default_deterministic_signal_functions().values():
            if getattr(library, function.__name__, None) is function:
                stack.enter_context(patch.object(library, function.__name__, forbidden))
        stack.enter_context(patch.object(library, 'default_deterministic_signal_functions', forbidden))
        yield record, declare


def source_authorities():
    """Verify the fixed source authority and real metadata shape before any write."""
    bindings = {str(SOURCE / name): sha(SOURCE / name) for name in SOURCE_AUTHORITY_SHAS}
    if any(bindings[str(SOURCE / name)] != expected for name, expected in SOURCE_AUTHORITY_SHAS.items()):
        raise ScopeStop('fixed source authority SHA differs before attempt')
    envelope = read(SOURCE / 'run_contract.json')
    checkpoint = SOURCE / 'experiments/round-0001/checkpoint.json'
    meta = SOURCE / 'meta/round-0001.json'
    cp = read(checkpoint)
    if (cp.get('round_id') != 1 or cp.get('run_contract_hash') != envelope.get('contract_hash')
            or not isinstance(cp.get('plan_ids'), list) or not cp['plan_ids']
            or not all(isinstance(plan_id, str) and plan_id for plan_id in cp['plan_ids'])
            or not meta.is_file() or Path(cp.get('meta_ref', '')).resolve() != meta.resolve()):
        raise ScopeStop('fixed source checkpoint/meta shape differs before attempt')
    return {'bindings': bindings, 'checkpoint': {'path': str(checkpoint), 'sha256': sha(checkpoint),
        'keys': sorted(cp), 'run_contract_hash_matches': True},
        'meta': {'path': str(meta), 'sha256': sha(meta)}}


def execute(expected_revision, expected_control_sha, expected_script_sha):
    """Run one exact native export/validate/materialize sequence, never a research cycle."""
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip()
    if revision != expected_revision or sha(CONTROL) != expected_control_sha:
        raise ScopeStop('expected revision/control SHA differs before attempt')
    if sha(__file__) != expected_script_sha:
        raise ScopeStop('diagnostic script differs from reviewed script SHA')
    subprocess.run(['git', 'diff', '--quiet', revision, '--', 'src', 'scripts'], cwd=REPO, check=True)
    if STAGE.exists():
        raise ScopeStop('fixed stage already exists; every prior attempt is terminal')
    authority = source_authorities()
    STAGE.mkdir()
    started = monotonic()
    save(STAGE / 'execution-start.json', {'pid': os.getpid(), 'revision': revision, 'control_sha256': expected_control_sha,
        'script_sha256': expected_script_sha, 'source_authority': authority,
        'command': sys.argv, 'python': sys.executable, 'scope': 'S1 history-only, no new execution contract or pointer advancement'})
    audit = None
    try:
        with source_only() as (audit, declare):
            original = control.EvolutionRunContract.load_frozen(SOURCE / 'run_contract.json')
            declare(original)
            digest = control.build_slow_history_manifest(workspace=STAGE, source_workspace=SOURCE,
                dataset_manifest_hash=original.dataset_manifest_hash)
            save(STAGE / 'build-receipt.json', {'manifest_hash': digest})
            carrier = replace(original, slow_history_manifest_hash=digest)
            manifest = control.validate_slow_history_manifest(workspace=STAGE, contract=carrier)
            save(STAGE / 'validation-receipt.json', {'manifest_hash': digest, 'source_contract_hash': original.contract_hash,
                'carrier_contract_hash': carrier.contract_hash, 'carrier_scope': 'In-memory validator argument only; not frozen, executed or a new budget authority.'})
            control.apply_slow_history_manifest(workspace=STAGE, manifest=manifest)
            registry = library.SignalRegistry(STAGE / 'signals', candidate_root=STAGE / 'signals_candidates')
            snapshot = control._historical_registry_snapshot(registry)
            if snapshot.version != manifest['registry_version'] or snapshot.registry_hash != manifest['registry_hash']:
                raise ScopeStop('materialized pure target identity differs')
            save(STAGE / 'materialization-receipt.json', {'version': snapshot.version, 'registry_hash': snapshot.registry_hash,
                'refs': [spec.ref for spec in snapshot.specs], 'learning_events': len(manifest['learning_events']),
                'definition_files': len(manifest['registry_definition_files']), 'cycle_artifacts': len(manifest['cycle_artifacts']),
                'candidate_files': len(manifest['candidate_files']), 'knowledge_observations': len(manifest.get('knowledge_observations', [])),
                'scope': 'Pure definition identity and committed file/event materialization only; no capability, synthesized learned profile, semantic learning or research execution claim.'})
        for path, item in audit['reads'].items():
            item['sha256_after'] = sha(path); item['unchanged'] = item['sha256_before'] == item['sha256_after']
        if not all(item['unchanged'] for item in audit['reads'].values()):
            raise ScopeStop('source bytes changed during read-only export')
        save(STAGE / 'result.json', {'status': 'completed_source_history_materialization', 'manifest_hash': digest,
            'source_audit': audit, 'revision': revision, 'control_sha256': sha(CONTROL), 'wall_seconds': monotonic() - started,
            'materialized_files': file_inventory(STAGE), 'new_fast_slow_pointer_or_execution_contract': False,
            'Signal_calls': 0, 'models': 0, 'GET': 0, 'LabelStore_or_LockedTest': 0})
    except Exception as exc:
        import traceback
        if audit is not None:
            for path, item in audit['reads'].items():
                item['sha256_after'] = sha(path); item['unchanged'] = item['sha256_before'] == item['sha256_after']
        save(STAGE / 'failure.json', {'status': 'terminal_failure', 'error_type': type(exc).__name__, 'error': str(exc),
            'traceback': traceback.format_exc(), 'source_audit': audit, 'wall_seconds': monotonic() - started,
            'partial_files': file_inventory(STAGE)})
        raise
    return read(STAGE / 'result.json')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true', required=True)
    parser.add_argument('--expected-revision', required=True)
    parser.add_argument('--expected-control-sha', required=True)
    parser.add_argument('--expected-script-sha', required=True)
    args = parser.parse_args()
    result = execute(args.expected_revision, args.expected_control_sha, args.expected_script_sha)
    print(json.dumps({'status': result['status'], 'manifest_hash': result['manifest_hash'], 'wall_seconds': result['wall_seconds']}, sort_keys=True))
