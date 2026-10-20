"""Read the sealed imported-unit producer and bounded reader, without a runtime."""
from __future__ import annotations

import builtins
from collections import Counter
from contextlib import ExitStack
import hashlib
import io
import json
from pathlib import Path
import socket
from types import SimpleNamespace
from unittest.mock import patch

from stock_opportunity_agent.cases.label_store import LabelStore
from stock_opportunity_agent.research.plan_evolution import EvolutionWorkspace
from stock_opportunity_agent.research.evolution_transport import StructuredRoleClient
from stock_opportunity_agent.research import signal_evolution as native
from stock_opportunity_agent.signal_library import SignalExecutor, SignalRegistry

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[3]
EXPORT = REPO / 'runs/diagnostics/reviewed_slow_history_export_20261021_v2'
STAGE = EXPORT / 'stage'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class ImportedProducer:
    """Only the original imported producer methods; no Engine initialization."""

    _imported_slow_history_manifest = native.SignalEvolutionEngine._imported_slow_history_manifest
    _imported_artifact_units = staticmethod(native.SignalEvolutionEngine._imported_artifact_units)
    _imported_slow_feedback = native.SignalEvolutionEngine._imported_slow_feedback


def execute():
    """Run one read-only source projection; never dispatch or stage a Slow cycle."""
    seal = json.loads((EXPORT / 'completed-files.json').read_text())
    assert sha(EXPORT / 'completed-files.json') == 'af51a017053d258b15b2bda7defcf73bbd86bf76c11b790e2fa2d4bff927352c'
    before = {p.relative_to(STAGE).as_posix(): sha(p) for p in STAGE.rglob('*') if p.is_file()}
    assert before == seal['files']
    assert seal['manifest_hash'] == 'ba60fd7c7aa4472900ef26c8068deee66e9d4e51c8a699455432f7eed626bc55'
    with (ROOT / 'execution-start.json').open('x') as out:
        json.dump({'scope': __doc__, 'script_sha256': sha(__file__),
            'native_source_sha256': sha(Path(native.__file__)), 'seal_sha256': sha(EXPORT / 'completed-files.json')}, out, indent=2)
        out.write('\n')
    forbidden_calls = []
    reads = set()
    def forbidden(*args, **kwargs):
        forbidden_calls.append(True)
        raise AssertionError('Runtime/model/Signal/network/label operation forbidden')
    real_open, real_io = builtins.open, io.open
    def check(path, mode):
        path = Path(path).resolve()
        if any(c in mode for c in 'wax+'):
            raise AssertionError('No writes during native producer/reader probe')
        if path.is_relative_to(REPO / 'runs'):
            assert path.is_relative_to(STAGE), str(path)
            reads.add(path.relative_to(STAGE).as_posix())
    def opened(path, mode='r', *args, **kwargs):
        check(path, mode)
        return real_open(path, mode, *args, **kwargs)
    def io_opened(path, mode='r', *args, **kwargs):
        check(path, mode)
        return real_io(path, mode, *args, **kwargs)
    owner = ImportedProducer()
    owner.workspace = SimpleNamespace(root=STAGE)
    with ExitStack() as stack:
        stack.enter_context(patch.object(builtins, 'open', opened))
        stack.enter_context(patch.object(io, 'open', io_opened))
        for cls, method in ((EvolutionWorkspace, '__init__'), (native.SignalEvolutionEngine, '__init__'),
                (LabelStore, '__init__'), (SignalRegistry, 'freeze'), (SignalRegistry, 'audit_capabilities'),
                (SignalExecutor, 'execute_batch'), (StructuredRoleClient, 'complete_json'),
                (socket, 'socket'), (socket, 'create_connection')):
            stack.enter_context(patch.object(cls, method, forbidden))
        rows, manifest = owner._imported_slow_feedback()
        catalog = native._slow_feedback_source_catalog(rows, manifest)
        target = next(row for row in rows if row['feedback_ref'].endswith(':1:slow_memory:summary'))
        ref = target['feedback_ref']
        assert target['artifact']['status'] == 'failed'
        assert len(target['artifact']['pending_feedback_refs']) == 3518
        assert target['artifact']['processed_feedback_refs'] == []
        included, view = native.read_slow_sources([ref], role_scope='reflection',
            source_catalog=catalog, budget_bytes=64000, max_items=3)
        positive = next(row['feedback_ref'] for row in rows if row['feedback_ref'].endswith(':1:slow_loop_result:summary'))
        small, small_view = native.read_slow_sources([positive], role_scope='reflection',
            source_catalog=catalog, budget_bytes=64000, max_items=3)
        headers = [row for row in rows if row.get('artifact', {}).get('schema_version') == 'imported-slow-method-memory-header-v1']
        assert len(headers) == 1
        compact = headers[0]
        compact_read, compact_view = native.read_slow_sources([compact['feedback_ref']], role_scope='reflection',
            source_catalog=catalog, budget_bytes=64000, max_items=3)
        h1_read, h1_view = native.read_slow_sources([compact['feedback_ref']], role_scope='H1',
            source_catalog=catalog, budget_bytes=64000, max_items=3)
        assert len(compact_read) == len(h1_read) == 1
        assert compact['artifact']['projection_status'] == 'available'
        delta = compact['artifact']['view']['memory_deltas'][0]
        assert delta['failure_ref'] == target['artifact']['failure_ref']
        assert delta['status'] == target['artifact']['status'] == 'failed'
        assert not any(key in delta for key in ('pending_feedback_refs', 'processed_feedback_refs'))
        assert '3518' not in json.dumps(compact['artifact'])
        hidden = [row['ref'] for row in manifest if row['ref'] == ref and 'H1' not in row['visible_to']]
        assert hidden == [ref]
        assert len(rows) == 3532 and not included
        entry_size = len(json.dumps({'ref': ref, **catalog[ref]}, sort_keys=True, ensure_ascii=False).encode())
        result = {'scope': 'Native imported producer/catalog/reader only; not full Engine/S1 input or S2/model consumption.',
            'native_imported_rows': len(rows), 'kind_counts': dict(Counter(row['kind'] for row in rows)),
            'manifest_rows': len(manifest), 'target_ref': ref, 'target_complete_entry_bytes': entry_size,
            'target_artifact_hash': native._canonical_hash(target['artifact']), 'target_view': view,
            'target_included_count': len(included), 'positive_ref': positive, 'positive_view': small_view,
            'positive_included_count': len(small), 'source_status': target['artifact']['status'],
            'source_pending': len(target['artifact']['pending_feedback_refs']), 'source_processed': 0,
            'observed_stage_reads': sorted(reads), 'forbidden_calls': len(forbidden_calls),
            'new_header': compact, 'reflection_header_read_manifest': compact_view,
            'H1_header_read_manifest': h1_view, 'old_summary_H1_hidden': True,
            'header_entry_bytes': len(json.dumps({'ref': compact['feedback_ref'], **catalog[compact['feedback_ref']]}, sort_keys=True, ensure_ascii=False).encode())}
    after = {p.relative_to(STAGE).as_posix(): sha(p) for p in STAGE.rglob('*') if p.is_file()}
    assert before == after == seal['files']
    result['all_228_completed_files_unchanged'] = True
    result['finding'] = ('additive_header_readable_original_and_pending_preserved'
        if not included and view['deferred'] == [{'ref': ref, 'reason': 'whole_entry_budget'}]
        else 'static_oversize_hypothesis_not_confirmed')
    with (ROOT / 'result.json').open('x') as out:
        json.dump(result, out, indent=2, sort_keys=True)
        out.write('\n')
    print(json.dumps({key: result[key] for key in ('finding', 'native_imported_rows', 'target_complete_entry_bytes', 'positive_included_count', 'all_228_completed_files_unchanged')}))


if __name__ == '__main__':
    execute()
