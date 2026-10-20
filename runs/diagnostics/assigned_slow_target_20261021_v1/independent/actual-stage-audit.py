"""Read actual assigned Controller requests and first sink; no product calls."""
from pathlib import Path
import hashlib
import json

REPO = Path('/Users/l/Project/Recommandation')
BASE = REPO / 'runs/diagnostics/assigned_slow_target_20261021_v1'
ROOT = BASE / 'stage'
PARENT = REPO / 'runs/diagnostics/reviewed_slow_feedback_stage_20261021_v1'
OWN = Path(__file__).resolve().parent
FIRST = '515b1e5b48b0c1ffbe036da03e93a3a0d6e96c4664fc6bb0fb538ee99b0a674e'
CORRECTION = 'd36d4277ad83f95e2aeb4867ffba206b3c6c175666f85fe8c627950c3ad172c0'
TARGET = 'reflection-7d08d205fe330564'
bindings = {}


def sha(path):
    path = Path(path)
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for part in iter(lambda: stream.read(1048576), b''):
            h.update(part)
    bindings[str(path)] = h.hexdigest()
    return h.hexdigest()


def read(path):
    path = Path(path)
    assert path.name not in {'approved_cases.json', 'input_manifest.json'}
    sha(path)
    return json.loads(path.read_text())


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def request(key, agent):
    journal = read(ROOT / 'transport/requests' / (key + '.json'))
    wire = journal['request']
    inbox = read(ROOT / 'exchange/inbox' / (key + '.json'))
    receipt = read(ROOT / 'exchange/receipts' / (key + '.json'))
    rawpath = ROOT / 'exchange/outbox' / (key + '.txt')
    raw = rawpath.read_text()
    cache = read(ROOT / 'transport/cache/responses' / (key + '.json'))
    assert digest(wire) == journal['request_hash'] == inbox['request_hash'] == receipt['request_hash'] == key
    assert wire['messages'] == inbox['messages']
    assert receipt['agent_id'] == agent
    assert sha(rawpath) == receipt['raw_output_sha256']
    assert sha(ROOT / 'exchange/inbox' / (key + '.json')) == receipt['inbox_sha256']
    assert raw == cache['raw_output'] and json.loads(raw) == cache['json_output']
    assert wire['stage'] == 'mining_controller_step' and wire['max_output_tokens'] == 4000
    payload = json.loads(next(m['content'] for m in wire['messages'] if m['role'] == 'user'))
    reserve = len(json.dumps(wire['messages'], ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()) + 4000
    assert reserve <= 131072
    return payload, json.loads(raw), reserve


if __name__ == '__main__':
    manifest = read(ROOT / 'manifest.json')
    assert digest({k: v for k, v in manifest.items() if k != 'manifest_hash'}) == manifest['manifest_hash'] == '7f39f03f28dfa9e2c276fccf57793f53f7b8e62a1b01e51ecc0fc9326d4aa267'
    for row in manifest['code'] + manifest['source_bindings']:
        assert sha(row['path']) == row['sha256']
    for relative, expected in manifest['copied_files'].items():
        assert sha(ROOT / 'workspace' / relative) == expected
    parent_seal = read(PARENT / 'completion.json')
    assert len(parent_seal['files']) == 272
    for relative, expected in parent_seal['files'].items():
        assert sha(PARENT / relative) == expected
    completion = read(ROOT / 'completion.json')
    for relative, expected in completion['files'].items():
        assert sha(ROOT / relative) == expected
    first, a1, reserve1 = request(FIRST, '/root/exact_role_85')
    second, a2, reserve2 = request(CORRECTION, '/root/exact_role_86')
    source = read(manifest['first_wire']['path'])
    source_user = json.loads(next(m['content'] for m in source['messages'] if m['role'] == 'user'))
    assert first == source_user
    invalid = second['last_invalid_action']
    assert set(invalid) == {'action', 'issue'} and 'rationale must be non-empty strings' in invalid['issue']
    assert {k: v for k, v in second.items() if k not in {'last_invalid_action', 'budget'}} == {k: v for k, v in first.items() if k != 'budget'}
    assert isinstance(a1['need_dispositions'][0]['rationale'], str)
    assert isinstance(a2['need_dispositions'][0]['rationale'], list)
    for answer in (a1, a2):
        assert answer['action'] == 'record_need_dispositions' and len(answer['need_dispositions']) == 1
        row = answer['need_dispositions'][0]
        assert row['need_refs'] == [TARGET] and row['disposition'] == 'repair_dependency' and row['signal_refs'] == []
    factory = read(PARENT / 'factory-input.json')
    full = {row['need_ref'] for row in factory['backlog_needs']}
    assert len(full) == 265
    for payload in (first, second):
        assert payload['slow_method_memory'] == factory['slow_method_memory']
        assert payload['meta_memory_disclosures'] == factory['meta_memory_disclosures']
        assert len(payload['slow_method_memory']['source_entries']) == 6
        assert all('H1' in row['visible_to'] for row in payload['slow_method_memory']['source_entries'])
        assert payload['need_disposition_contract']['staged_count'] == 0
        assert payload['need_disposition_contract']['pending_count'] == 265
        assert len(payload['case_refs']) == len(payload['label_map']) == 8
        assert sorted(payload['label_map'].values()) == ['control'] * 4 + ['positive'] * 4
    boundary = read(ROOT / 'controller-boundary.json')
    assert boundary['full_backlog_count'] == 265 and len(boundary['unit_files']) == 1
    assert boundary['pending_need_refs'] == [row['need_ref'] for row in factory['backlog_needs'] if row['need_ref'] != TARGET]
    unit_binding = boundary['unit_files'][0]
    assert sha(unit_binding['path']) == unit_binding['sha256']
    unit = read(unit_binding['path'])
    assert unit['accepted_rows'] == a2['need_dispositions'] and unit['invalid_rows'] == []
    assert unit['pending_count'] == 264 and unit['backlog_hash'] == digest(factory['backlog_needs'])
    assert unit['base_hash'] == a1['base_hash'] == a2['base_hash']
    assert digest({'backlog_hash': unit['backlog_hash'], 'axis': factory['research_axis'], 'seed': 'hypothesis', 'staged_rows': []}) == unit['base_hash']
    assert digest({'backlog_hash': unit['backlog_hash'], 'axis': factory['research_axis'], 'seed': 'hypothesis', 'staged_rows': unit['accepted_rows']}) == unit['result_hash']
    ledger = boundary['ledger']
    assert len(ledger) == 3 and 'invalid_action:' in ledger[1]['note'] and ledger[2]['note'] is None
    for action, entry in [(a1, ledger[1]), (a2, ledger[2])]:
        assert digest({'action': action['action'], 'args': {k: v for k, v in action.items() if k != 'rationale'}}) == entry['input_hash']
    assert digest(unit) == ledger[2]['output_hash']
    oracle = read(BASE / 'oracle/final-source-oracle.json')
    expected = oracle['independent_expected']
    assert expected['native_need_ref'] == TARGET and expected['expected_disposition'] == 'repair_dependency' and expected['expected_signal_refs'] == []
    target = next(r for r in first['last_action_result']['result']['items'] if r['need_ref'] == TARGET)
    assert target['source_hash'] == '5da3598de291c0409be18fb73ba0489101aea126073b63a6c9fbbd712ec3e228'
    assert set(p.stem for p in (ROOT / 'exchange/receipts').glob('*.json')) == {FIRST, CORRECTION}
    assert set(p.stem for p in (ROOT / 'transport/requests').glob('*.json')) == {FIRST, CORRECTION}
    assert reserve1 + reserve2 <= 393216
    result = completion['result']
    assert result['status'] == 'native_need_unit_saved_semantics_unreviewed' and result['complete_S1_S2'] is False
    state, cycle = read(ROOT / 'workspace/state.json'), read(ROOT / 'workspace/cycle_state.json')
    assert state['last_completed_round'] == cycle['last_completed_cycle'] == result['completed_cycle'] == result['completed_round'] == 0
    assert read(ROOT / 'unused_external_attempts.json')['attempts'] == []
    report = {'status': 'PASS_corrected_assigned_target_semantics_and_original_sink_1_of_1',
        'acceptance': {'fixed_target_denominator': 1, 'corrected_target_passes': 1,
            'native_first_passes': 0, 'first_answer_semantic_route_supported': True,
            'first_native_rejection': invalid['issue'], 'native_corrections': 1,
            'continuation_not_field_preserving_patch': True, 'other_pending_exact': 264,
            'old_v1_target_result': '0/1 not exercised permanently retained'},
        'semantic_review': {'route': 'repair_dependency', 'signal_refs': [],
            'supported': 'The exact visible target reports three versioned validation failures removing validated evidence while all cases remained scored without technical exclusion. Both responses route technical dependency diagnosis, separate case inclusion from successful Signal execution, and preserve unknown root cause/recovery.',
            'corrected_answer': 'Role86 explicitly asks to inspect versioned requests/raw answers/validation/correction/persistence/downstream consumption before repairing, retains uncertainty and claims only a route intent.',
            'negative_checks': ['No assertion that unavailable evidence is an absent/negative economic condition.',
                'No new measured concept, semantic Signal change, case exclusion, score change, causal attribution, return or improvement claim.',
                'No invented precise projection/phrase error diagnosis that was not visible in the request.',
                'No unassigned accepted sibling or dropped pending need.'],
            'visible_source': target, 'oracle_visibility_boundary_respected': True},
        'actual_consumption': {'first_request': FIRST, 'continuation_request': CORRECTION,
            'agents': ['/root/exact_role_85', '/root/exact_role_86'], 'six_full_originals_and_scopes_exact': True,
            'full_user_first_equals_accepted_frontier': True, 'dev_opaque_labels_only': '8=4positive+4control',
            'raw_cache_receipt_inbox_exact': True, 'raw86_rows_equal_persisted_unit': True,
            'unit': unit_binding, 'full_backlog': 265, 'staged_before_answers': 0,
            'completed_business_pointers': [0, 0], 'logical_reservations': [reserve1, reserve2],
            'logical_total': reserve1 + reserve2, 'no_extra_request_after_sink': True},
        'integrity': {'current_code': len(manifest['code']), 'direct_source_bindings': len(manifest['source_bindings']),
            'copied_originals': len(manifest['copied_files']), 'parent_seal_files_current_exact': 272,
            'child_completion_map_files_current_exact': len(completion['files'])},
        'limits': ['Only readonly artifact parsing/hash checks were run; no advance/reopen, constructor, product validator, Store, model, Signal, GET or LabelStore.',
            'Approved40 and input manifests were only stream-hashed, never deserialized. Only native opaque dev8 labels were inspected.',
            'One native no-patch invalid-action continuation changed authored wording; this is not a verified field-level patch preserving the prior answer.',
            'This control demonstrates assigned target routing and original intent persistence from a reused accepted frontier, not autonomous target selection, a new source/Reflect prefix, executed repair, repaired dependency, new Signal, full Slow/S1/S2/MVP or independent benefit.',
            'Actual root terminal-reopen verification is separate; this reviewer did not perform it. Host tokens/cost remain unmeasured.'],
        'bindings': bindings}
    sha(Path(__file__))
    output = OWN / 'actual-stage-review.json'
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'sha256': sha(output), 'logical_total': reserve1 + reserve2, 'child_sealed_files': len(completion['files'])}))
