"""Verify the prepared formal child by JSON/hash reads only."""
from pathlib import Path
import hashlib
import json

REPO = Path('/Users/l/Project/Recommandation')
BASE = REPO / 'runs/diagnostics/assigned_slow_target_20261021_v1'
ROOT = BASE / 'stage'
SOURCE = REPO / 'runs/diagnostics/reviewed_slow_feedback_stage_20261021_v1'
OWN = Path(__file__).resolve().parent
bindings = {}


def sha(path):
    path = Path(path)
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1048576), b''):
            h.update(chunk)
    bindings[str(path)] = h.hexdigest()
    return h.hexdigest()


def read(path):
    path = Path(path)
    assert path.name not in {'approved_cases.json', 'input_manifest.json'}
    sha(path)
    return json.loads(path.read_text())


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


if __name__ == '__main__':
    manifest = read(ROOT / 'manifest.json')
    assert digest({k: v for k, v in manifest.items() if k != 'manifest_hash'}) == manifest['manifest_hash'] == '7f39f03f28dfa9e2c276fccf57793f53f7b8e62a1b01e51ecc0fc9326d4aa267'
    assert len(manifest['code']) == 178 and len(manifest['source_bindings']) == 3
    for row in manifest['code'] + manifest['source_bindings']:
        assert sha(row['path']) == row['sha256']
    copies = {str(p.relative_to(ROOT / 'workspace')): sha(p)
              for name in ('signals', 'slow_history', 'signals_candidates')
              for p in (ROOT / 'workspace' / name).rglob('*') if p.is_file()}
    assert copies == manifest['copied_files'] and len(copies) == 223
    source_seal = read(SOURCE / 'completion.json')
    for relative, expected in source_seal['files'].items():
        assert sha(SOURCE / relative) == expected
    assert len(source_seal['files']) == 272
    assert not source_seal['result']['complete_S1_S2']
    contract = read(ROOT / 'run_contract.json')
    assert contract == read(ROOT / 'workspace/run_contract.json')
    assert (ROOT / 'run_contract.json').read_bytes() == (ROOT / 'workspace/run_contract.json').read_bytes()
    assert contract['contract'] == manifest['run_contract'] and digest(contract['contract']) == contract['contract_hash']
    assert (manifest['max_calls'], manifest['request_cap'], manifest['total_cap']) == (3, 131072, 393216)
    state, cycle = read(ROOT / 'workspace/state.json'), read(ROOT / 'workspace/cycle_state.json')
    assert state['last_completed_round'] == cycle['last_completed_cycle'] == 0
    assert cycle['active_cycle']['phase'] == 'slow_loop'
    oracle_freeze = read(BASE / 'oracle/final-source-oracle-freeze.json')
    assert sha(oracle_freeze['oracle']['path']) == oracle_freeze['oracle']['sha256']
    oracle = read(oracle_freeze['oracle']['path'])
    assert digest(manifest['code']) == oracle_freeze['all_runtime_code_bindings_hash']
    for row in oracle_freeze['candidate_primary_bindings']:
        assert sha(row['path']) == row['sha256']
    captured = read(ROOT / 'preflight-wire.json')
    old_inbox = read(manifest['first_wire']['path'])
    assert sha(manifest['first_wire']['path']) == manifest['first_wire']['sha256']
    old_user = json.loads(next(m['content'] for m in old_inbox['messages'] if m['role'] == 'user'))
    assert captured['actual_user'] == captured['expected_user'] == old_user
    temp = read(BASE / 'driver/temp-native-preflight/preflight-wire.json')
    assert captured['actual_user'] == temp['actual_user']
    requests = list((ROOT / 'preflight/requests').glob('*.json'))
    assert len(requests) == 1
    journal = read(requests[0]); wire = journal['request']
    assert digest(wire) == journal['request_hash'] == requests[0].stem
    actual = json.loads(next(m['content'] for m in wire['messages'] if m['role'] == 'user'))
    assert actual == old_user
    system = next(m['content'] for m in wire['messages'] if m['role'] == 'system')
    native, assignment = system.split('\nThis independent child module ', 1)
    assert native == next(m['content'] for m in old_inbox['messages'] if m['role'] == 'system').split('\nThis frozen diagnostic module ', 1)[0]
    assert 'reflection-7d08d205fe330564' in assignment
    assert 'repair_dependency' not in assignment and 'validation failures' not in assignment
    factory = read(SOURCE / 'factory-input.json')
    assert len(factory['backlog_needs']) == 265
    assert digest(factory['backlog_needs']) == oracle_freeze['native_backlog_hash'] == actual['backlog_disclosure']['backlog_hash']
    assert actual['need_disposition_contract']['staged_count'] == 0 and actual['need_disposition_contract']['pending_count'] == 265
    assert actual['slow_method_memory'] == factory['slow_method_memory']
    assert len(actual['slow_method_memory']['source_entries']) == 6
    assert all('H1' in row['visible_to'] for row in actual['slow_method_memory']['source_entries'])
    assert digest(actual['slow_method_memory']) == oracle['accepted_prefix_and_permissions']['H1_scoped_memory_view_hash']
    assert digest(actual['meta_memory_disclosures']) == oracle['accepted_prefix_and_permissions']['six_disclosures_canonical_hash']
    assert actual['slow_method_memory']['memory_deltas'][0]['memory_hash'] == manifest['accepted_memory_hash'] == oracle_freeze['accepted_memory_hash']
    assert read(ROOT / 'progress.json')['status'] == 'prepared_not_dispatched'
    assert sorted(str(p.relative_to(ROOT / 'exchange')) for p in (ROOT / 'exchange').rglob('*') if p.is_file()) == ['contract.json']
    assert not list((ROOT / 'transport/requests').glob('*.json'))
    reservation = len(json.dumps(wire['messages'], ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()) + wire['max_output_tokens']
    assert reservation == 92533
    report = {'status': 'PASS_formal_prepared_zero_answers_only', 'manifest_hash': manifest['manifest_hash'],
        'verified': {'current_code': 178, 'direct_source_bindings': 3, 'copied_exact_files': 223,
            'unchanged_parent_sealed_files': 272, 'dual_contract_bytes_and_hash_exact': True,
            'formal_user_equals_old_frontier_and_temp': True, 'native_system_prefix_equal': True,
            'only_declared_system_change': 'Native need ref assignment, execution restrictions; no expected route or diagnosis.',
            'full_backlog': 265, 'staged': 0, 'six_complete_originals_scopes_exact': True,
            'oracle_scoped_memory_and_disclosure_hash_exact': True, 'state_completed_pointers': [0, 0],
            'max_calls': 3, 'regular_correction_split': [2, 1], 'per_request_cap': 131072, 'total_cap': 393216,
            'captured_request_reservation': reservation, 'exchange_inbox_raw_receipts': 0},
        'limits': ['Only filesystem JSON/text/streaming hashes read. No Engine/Store construction, prepare, advance, model, Signal, GET or LabelStore invoked.',
            'Mixed approved/input manifest files were only stream-hashed, never deserialized.',
            'Private oracle is reviewer-only; actual transmitted native user remains byte-content-equivalent to the old frontier and carries no new oracle/witness.',
            'This is pre-dispatch integrity and permission evidence, not a future semantic pass. Original v1 target0/1 and incomplete cycle remain unchanged.'],
        'bindings': bindings}
    sha(Path(__file__))
    output = OWN / 'formal-preflight-review.json'
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'sha256': sha(output), 'manifest_hash': manifest['manifest_hash']}))
