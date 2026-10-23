"""Capture repaired full-request encoding outside the sealed native evaluation."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import socket

import run_icfr_native_capability_stage as native
from stock_opportunity_agent.research.mining_role_model import MiningAgentRoleModel, _MiningReferenceHandles
from stock_opportunity_agent.research.scheme_evolution import EvolutionControlFlow
from stock_opportunity_agent.research.stage_contracts import json_bytes

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
OLD = ROOT / 'runs/diagnostics/mining_catalog_working_context_20261023_v1/terminal-boundary/blocked-offline-native-estimate.json'
STAGE = ROOT / 'runs/diagnostics/icfr_native_capability_20261023_v1/stage-v3'


def sha(path):
    """Bind a local file without entering runtime stage functions."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def files():
    """Capture all sealed-stage bytes, including the original terminal receipt."""
    return {str(p.relative_to(STAGE)): sha(p) for p in sorted(STAGE.rglob('*')) if p.is_file()}


class Captured(EvolutionControlFlow):
    """Stop after native message construction and before exchange prepare."""


def main():
    """Measure only the copied input and preserve the existing evaluation."""
    before = files(); original = json.loads(OLD.read_text()); view = original['payload']
    completion = json.loads((STAGE / 'completion.json').read_text())
    assert all(before[rel] == digest for rel, digest in completion['files'].items())
    original_hash = native.digest(view)
    codec = _MiningReferenceHandles(view); encoded = codec.payload(view)
    restored = codec.transform({key: value for key, value in encoded.items() if key != 'reference_handles'}, restore=True)
    assert restored == view
    captured = []
    def observe(event):
        if event.get('event_type') == 'request_ready':
            captured.append(json.loads(Path(event['request_path']).read_text())['request'])
            raise Captured()
    with TemporaryDirectory() as temporary, patch.object(socket.socket, 'connect', side_effect=AssertionError('network prohibited')), patch.object(native.LocalRoleExchange, 'receive', side_effect=AssertionError('receive prohibited')):
        root = Path(temporary)
        caller = native.Caller(registration=native.get_model('independent-subagent'),
            contract=native.StageContract(json.loads((STAGE / 'contract.json').read_text())),
            workspace=root / 'native', ledger=native.ExternalAttemptLedger(root / 'unused.json', max_attempts=1, max_total_cost=.01),
            local_role_exchange=native.LocalRoleExchange(root / 'exchange', max_calls=1),
            allow_external=False, environ={}, on_progress=observe)
        caller.budget = SimpleNamespace(scope='mining')
        model = MiningAgentRoleModel(caller, max_request_tokens=262144, max_total_tokens=12 * native.MIB, max_calls=80)
        model.reserved_tokens = 2055941; model.reserved_calls = 10
        try:
            model.next_action(deepcopy(view))
        except Captured:
            pass
        else:
            raise AssertionError('expected zero-receive capture')
        assert len(captured) == 1
        request = captured[0]; cost = json_bytes(request['messages']) + request['max_output_tokens']
        wire = json.loads(request['messages'][1]['content'])
        assert int(wire['request_budget']['this_request']) == cost
        assert int(wire['request_budget']['remaining_after']) == 12 * native.MIB - 2055941 - cost
        assert wire['request_budget']['calls_used'] == 10
        assert model.reserved_tokens == 2055941 and model.reserved_calls == 10
        assert not list((root / 'exchange/inbox').glob('*.json'))
        assert not list((root / 'exchange/receipts').glob('*.json'))
        assert cost <= 262144
    assert native.digest(view) == original_hash and files() == before
    (OUT / 'repaired-full-request.json').write_text(json.dumps(request, ensure_ascii=False, indent=2) + '\n')
    (OUT / 'capture-result.json').write_text(json.dumps({'original_input': {'path': str(OLD), 'sha256': sha(OLD)},
        'tested_files': [{'path': name, 'sha256': sha(ROOT / name)} for name in (
            'src/stock_opportunity_agent/research/mining_role_model.py',
            'spec/src/stock_opportunity_agent/research/signal_mining_agent.md',
            'tests/test_mining_reference_handles.py', 'tests/test_icfr_native_capability_stage.py')],
        'original_logical_estimate': original['required'], 'repaired_logical_estimate': cost,
        'saving': original['required'] - cost, 'single_limit': 262144, 'remaining_single': 262144 - cost,
        'fact_count': len(view['known_fact_refs']), 'relation_count': len(view['known_relation_refs']),
        'total_references': len(codec.forward), 'codec_scope_hash': codec.scope_hash,
        'canonical_input_unchanged': True, 'all_sealed_files_unchanged': len(before), 'sealed_table_matches': len(completion['files']),
        'new_inboxes': 0, 'new_answers': 0, 'new_receipts': 0, 'network_calls': 0,
        'logical_used_preserved': [model.reserved_calls, model.reserved_tokens],
        'proof_scope': 'offline full-input encoding and native zero-receive capture only; no new model compliance or stage continuation'}, ensure_ascii=False, indent=2) + '\n')
    print((OUT / 'capture-result.json').read_text())


if __name__ == '__main__':
    main()
