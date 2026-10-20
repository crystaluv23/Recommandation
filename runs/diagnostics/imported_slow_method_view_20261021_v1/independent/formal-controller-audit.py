"""Read completed Controller artifacts; never invoke the stage or product code."""
from pathlib import Path
import hashlib
import json

ROOT = Path('/Users/l/Project/Recommandation/runs/diagnostics/reviewed_slow_feedback_stage_20261021_v1')
OWN = Path(__file__).resolve().parent
FIRST = '41b684543a85c2accdcbfccc64df1a80983d7b3ea7f57c147808a14d57e2c1af'
NEXT = 'cd19a93e367e6e3b9037dc97a78788cfcf69d85802982726cd41df3c84d886ff'
TARGET = 'reflection-7d08d205fe330564'
CHOSEN = 'reflection-68eeb8eb36ca95db'
bindings = {}


def sha(p):
    p = Path(p)
    h = hashlib.sha256()
    with p.open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    bindings[str(p)] = h.hexdigest()
    return h.hexdigest()


def read(p):
    p = Path(p)
    assert p.name != 'approved_cases.json', 'Mixed case envelope may only be stream-hashed.'
    sha(p)
    return json.loads(p.read_text())


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def request(key):
    journal = read(ROOT / 'transport/requests' / (key + '.json'))
    wire = journal['request']
    inbox = read(ROOT / 'exchange/inbox' / (key + '.json'))
    receipt = read(ROOT / 'exchange/receipts' / (key + '.json'))
    rawpath = ROOT / 'exchange/outbox' / (key + '.txt')
    raw = rawpath.read_text()
    cache = read(ROOT / 'transport/cache/responses' / (key + '.json'))
    assert canonical(wire) == journal['request_hash'] == inbox['request_hash'] == receipt['request_hash'] == key
    assert inbox['messages'] == wire['messages']
    assert sha(ROOT / 'exchange/inbox' / (key + '.json')) == receipt['inbox_sha256']
    assert sha(rawpath) == receipt['raw_output_sha256']
    assert raw == cache['raw_output'] and json.loads(raw) == cache['json_output']
    reservation = len(json.dumps(wire['messages'], ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()) + wire['max_output_tokens']
    assert reservation <= 131072
    payload = json.loads(next(m['content'] for m in wire['messages'] if m['role'] == 'user'))
    return wire, payload, json.loads(raw), reservation, receipt


if __name__ == '__main__':
    manifest = read(ROOT / 'manifest.json')
    for row in manifest['code'] + manifest['source_bindings']:
        assert sha(row['path']) == row['sha256']
    for relative, expected in manifest['copied_files'].items():
        assert sha(ROOT / 'workspace' / relative) == expected
    completion = read(ROOT / 'completion.json')
    for relative, expected in completion['files'].items():
        assert sha(ROOT / relative) == expected
    first, p1, a1, reserve1, receipt1 = request(FIRST)
    second, p2, a2, reserve2, receipt2 = request(NEXT)
    assert receipt1['agent_id'] == '/root/slow_feedback_role83'
    assert receipt2['agent_id'] == '/root/slow_feedback_role84'
    assert 'output_patch_contract' not in p2['last_invalid_action']
    assert set(p2['last_invalid_action']) == {'action', 'issue'}
    assert 'rationale must be non-empty strings' in p2['last_invalid_action']['issue']
    assert 'choosing one admissible action' in second['messages'][0]['content']
    assert isinstance(a1['need_dispositions'][0]['rationale'], str)
    assert isinstance(a2['need_dispositions'][0]['rationale'], list)
    for action in (a1, a2):
        assert action['action'] == 'record_need_dispositions'
        assert action['need_dispositions'][0]['need_refs'] == [CHOSEN]
        assert action['need_dispositions'][0]['disposition'] == 'fast_plan_action'
        assert action['need_dispositions'][0]['signal_refs'] == []
    memory = read(ROOT / 'workspace/experiments/cycles/cycle-0001/slow_memory.json')
    slow = p1['slow_method_memory']
    delta = slow['memory_deltas'][0]
    assert delta['memory_hash'] == canonical(memory)
    originals = {f"slow-memory:1:{kind}:{row[field]}": row
                 for kind, rows, field in [('episode', memory['episode_reflections'], 'episode_ref'),
                                          ('lesson', memory['lesson_additions'], 'lesson_id')]
                 for row in rows}
    entries = {row['ref']: row['content'] for row in slow['source_entries']}
    assert entries == originals and len(entries) == 6
    for brief in delta['episode_reflections'] + delta['lesson_additions']:
        original = originals[brief['original_ref']]
        assert brief['original_hash'] == canonical(original)
        assert brief['brief'] == original['brief']
    factory = read(ROOT / 'factory-input.json')
    assert factory['slow_method_memory']['memory_deltas'] == slow['memory_deltas']
    assert p1['prior_modality_footprints'] == []
    page = read(ROOT / 'controlled-page-read.json')['tool_result']
    actual_page = p1['last_action_result']['result']
    assert p1['last_action_result'] == page
    rows = {row['need_ref']: row for row in actual_page['items']}
    assert len(rows) == 6 and TARGET in rows and CHOSEN in rows
    assert rows[TARGET]['source_hash'] == manifest['native_prepared']['target_action_hash']
    assert rows[TARGET]['source_hash'] == '5da3598de291c0409be18fb73ba0489101aea126073b63a6c9fbbd712ec3e228'
    assert actual_page['cursor'] == 259 and actual_page['total_backlog_count'] == 265
    boundary = read(ROOT / 'controller-boundary.json')
    assert boundary['stop'] == 'after_original_need_progress_sink'
    assert len(boundary['unit_files']) == 1
    unit_binding = boundary['unit_files'][0]
    assert sha(unit_binding['path']) == unit_binding['sha256']
    unit = read(unit_binding['path'])
    assert unit['accepted_rows'] == a2['need_dispositions']
    assert unit['invalid_rows'] == [] and unit['pending_count'] == 264
    assert TARGET in boundary['pending_need_refs'] and CHOSEN not in boundary['pending_need_refs']
    assert len(boundary['pending_need_refs']) == 264
    ledger = boundary['ledger']
    assert len(ledger) == 3 and 'invalid_action:' in ledger[1]['note'] and ledger[2]['note'] is None
    for action, entry in [(a1, ledger[1]), (a2, ledger[2])]:
        assert canonical({'action': action['action'], 'args': {k: v for k, v in action.items() if k != 'rationale'}}) == entry['input_hash']
    assert len(list((ROOT / 'exchange/receipts').glob('*.json'))) == 6
    assert completion['result']['complete_S1_S2'] is False
    all_requests = []
    for qp in (ROOT / 'transport/requests').glob('*.json'):
        wire = read(qp)['request']
        units = len(json.dumps(wire['messages'], ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()) + wire['max_output_tokens']
        assert units <= manifest['stage_contract']['per_request_logical_cap']
        all_requests.append((qp.stem, wire['stage'], units))
    assert len(all_requests) == 6
    total = sum(row[2] for row in all_requests)
    assert total == 301117 and total <= manifest['stage_contract']['total_logical_cap']
    verification = read(OWN.parent / 'root/formal-completed-verification.json')
    assert verification['all_bytes_members_unchanged_after_sole_terminal_reopen'] is True
    assert verification['construction_model_Signal_labels_network_tripwires'] == dict.fromkeys(['construction', 'model', 'Signal', 'labels', 'network'], 0)
    assert verification['completed_sealed_files'] == len(completion['files']) == 272
    assert verification['total_files_with_completion'] == 273
    assert verification['logical_reservation'] == total
    assert verification['first_original_need_unit']['sha256'] == unit_binding['sha256']
    assert sha(ROOT / 'completion.json')

    report = {
        'status': 'PASS_other_route_semantics_and_native_sink; TARGET_NOT_EXERCISED_0_of_1',
        'target': {'need_ref': TARGET, 'required_route': 'repair_dependency', 'selected': False,
                   'pending': True, 'fixed_denominator': 1, 'passes': 0,
                   'interpretation': 'The transmitted envelope permits any disclosed admissible need; the target page does not require this particular target. This is a selection/measurability gap, not evidence of a wrong chosen-need route.'},
        'actual_route': {'need_ref': CHOSEN, 'disposition': 'fast_plan_action', 'signal_refs': [],
                         'semantic_result': 'Supported by the explicit magnitude-band Plan-review need. Both answers condition upper classes on source-backed support; role84 explicitly permits unsupported upper bands and disclaims implementation, Plan consumption and independent improvement.',
                         'new_measurement_or_forced_prediction': False},
        'native': {'first_agent': receipt1['agent_id'], 'continuation_agent': receipt2['agent_id'],
                   'first_shape_rejection': p2['last_invalid_action'],
                   'continuation_kind': 'one native invalid-action correction; no output_patch_contract and no supplied previous body; admissible action may be reselected',
                   'field_preserving_patch_claim': False, 'model_requests': 2, 'corrections': 1,
                   'reservations': [reserve1, reserve2], 'accepted_rows_raw_exact': True,
                   'saved_units': 1, 'pending_needs': 264, 'first_original_sink_stop': True},
        'actual_consumption': {'memory_hash': delta['memory_hash'], 'briefs': 6,
                               'full_original_source_entries': 6, 'full_originals_match_persisted_memory': True,
                               'factory_delta_match': True, 'controlled_page': {'cursor': 259, 'included': 6, 'total': 265},
                               'prior_modality_footprints': [],
                               'prompt_envelope': 'Native prompt plus disclosed diagnostic authorization envelope and native controlled page; not autonomous backlog discovery.'},
        'integrity': {'code_bindings': len(manifest['code']), 'direct_source_bindings': len(manifest['source_bindings']),
                      'copied_original_files': len(manifest['copied_files']), 'completion_map_files': len(completion['files']), 'total_logical_reservation': total, 'all_requests': all_requests,
                      'request_journal_inbox_receipt_raw_cache_exact': True},
        'completed_verification': {'executor_report': str(OWN.parent / 'root/formal-completed-verification.json'),
            'executor_sole_reopen_reported_no_new_native_calls': True, 'current_272_sealed_bytes_independently_match': True,
            'total_with_completion': 273, 'os_crash_recovery_claim': False},
        'corrections_to_review_process': ['Earlier oral inference of only three complete source entries came from truncated display. Direct complete extraction proves six full originals; this report uses six.',
                                          'Audit harness first used lesson_ref instead of actual lesson_id, then compared a tool result body with its wrapper; both initial logs remain. A third assertion initially hashed the entire raw action rather than native action/args ledger form excluding top-level rationale; its failed log also remains. Only audit code was corrected; no product operation was repeated.',
                                          'No prior answer was supplied by this reviewer to role84, and no answer or stage artifact was edited.'],
        'limits': ['No stage/constructor/validator/Store/Signal/model/GET/LabelStore invoked; only JSON, text and streaming hashes read.',
                   'approved_cases.json was only stream-hashed via the completion map, never deserialized.',
                   'Only original native intent persistence is established: no Fast Plan implementation, new candidate, publication, future reuse, causal improvement or benefit.',
                   'Target repair-dependency positive remains unexecuted; complete S1/S2 and MVP are not closed.',
                   'This audit does not execute completed restore or establish OS interruption recovery. Host model cost/tokens remain unmeasured.'],
        'bindings': bindings,
    }
    sha(Path(__file__))
    out = OWN / 'formal-controller-review.json'
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({'status': report['status'], 'review_sha256': sha(out), 'completion_files': len(completion['files']), 'reservations': [reserve1, reserve2]}))
