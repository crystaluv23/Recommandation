"""One byte-verifying terminal reopen; no new native construction or role."""
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import socket
from unittest.mock import patch

from scripts import run_reviewed_slow_feedback_stage as stage
from stock_opportunity_agent.artifacts import canonical_json_hash as digest

OUT = Path(__file__).resolve().parent
ROOT = stage.STAGE_ROOT

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def files(root):
    return {p.relative_to(root).as_posix(): sha(p) for p in sorted(root.rglob('*'))
            if p.is_file() and not p.name.endswith('.lock')}

def main():
    assert not (OUT / 'formal-completed-verification.json').exists()
    before = files(ROOT)
    completed = stage.read(ROOT / 'completion.json')
    assert {k: v for k, v in before.items() if k != 'completion.json'} == completed['files']
    manifest = stage.read(ROOT / 'manifest.json')
    assert all(stage.binding(row['path']) == row for row in manifest['code'] + manifest['source_bindings'])
    assert {path: sha(ROOT / 'workspace' / path) for path in manifest['copied_files']} == manifest['copied_files']
    source = ROOT / 'workspace/slow_history'
    old = stage.read(source / 'source-12a50702a856ddc3/experiments/cycles/cycle-0001/slow_memory.json')
    assert old['status'] == 'failed' and old['processed_feedback_refs'] == [] and len(old['pending_feedback_refs']) == 3518
    slow_input = stage.read(ROOT / 'workspace/experiments/cycles/cycle-0001/slow_input.json')
    memory = stage.read(ROOT / 'workspace/experiments/cycles/cycle-0001/slow_memory.json')
    full = {row['feedback_ref'] for row in slow_input['feedback_rows']}
    processed, pending = set(memory['processed_feedback_refs']), set(memory['pending_feedback_refs'])
    assert len(full) == 4493 and len(processed) == 3 and len(pending) == 4490
    assert not processed & pending and processed | pending == full
    assert not any(ref.endswith(':slow_memory:summary') for ref in processed)
    boundary = stage.read(ROOT / 'controller-boundary.json')
    assert boundary['full_backlog_count'] == 265 and len(boundary['pending_need_refs']) == 264
    assert 'reflection-7d08d205fe330564' in boundary['pending_need_refs']
    units = list((ROOT / 'workspace/experiments/cycles/cycle-0001/mining_need_units').glob('*/*.json'))
    assert len(units) == 1
    unit = stage.read(units[0])
    assert unit['accepted_rows'][0]['need_refs'] == ['reflection-68eeb8eb36ca95db']
    assert unit['accepted_rows'][0]['disposition'] == 'fast_plan_action'
    assert not unit['invalid_rows'] and unit['pending_count'] == 264
    receipts = [stage.read(p) for p in sorted((ROOT / 'exchange/receipts').glob('*.json'))]
    assert len(receipts) == len({r['agent_id'] for r in receipts}) == 6
    budget = stage._Budget(ROOT / 'transport/requests')
    assert len(budget.requests) == 6
    tripwires = {'construction': 0, 'model': 0, 'Signal': 0, 'labels': 0, 'network': 0}
    def reject(name):
        def call(*args, **kwargs):
            tripwires[name] += 1
            raise AssertionError('terminal reopen forbids ' + name)
        return call
    with ExitStack() as stack:
        for owner, name, kind in [(stage, '_construct', 'construction'),
                (stage.StructuredRoleClient, 'complete_json', 'model'),
                (stage.SignalExecutor, 'execute_batch', 'Signal'),
                (stage.LabelStore, 'load', 'labels'), (socket, 'socket', 'network'),
                (socket, 'create_connection', 'network')]:
            stack.enter_context(patch.object(owner, name, reject(kind)))
        restored = stage.advance(ROOT)
    assert restored == completed['result']
    after = files(ROOT)
    assert before == after and all(n == 0 for n in tripwires.values())
    result = {'result': restored, 'completed_sealed_files': len(completed['files']),
        'total_files_with_completion': len(before), 'all_bytes_members_unchanged_after_sole_terminal_reopen': True,
        'construction_model_Signal_labels_network_tripwires': tripwires,
        'copied_source_files': len(manifest['copied_files']), 'code_files': len(manifest['code']),
        'source_binding_files': len(manifest['source_bindings']), 'old_failed_memory_pending': 3518,
        'old_failed_memory_processed': 0, 'new_feedback_full': 4493, 'new_processed': 3, 'new_pending': 4490,
        'backlog_full': 265, 'backlog_pending': 264, 'frozen_technical_target_still_pending': True,
        'technical_target_control_passed': False, 'technical_target_control_denominator': 1,
        'first_original_need_unit': stage.binding(units[0]), 'receipts': len(receipts),
        'unique_role_requests': len(budget.requests), 'logical_reservation': sum(row['reservation'] for row in budget.requests.values()),
        'families': {kind: sum(row['family'] == kind for row in budget.requests.values()) for kind in sorted({row['family'] for row in budget.requests.values()})},
        'whole_S1_S2_or_cycle_or_gain': False}
    (OUT / 'formal-completed-verification.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()
