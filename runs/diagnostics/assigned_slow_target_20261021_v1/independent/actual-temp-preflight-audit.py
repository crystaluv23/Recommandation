"""Parse saved native zero-answer preflight only; never construct or run a stage."""
from pathlib import Path
import hashlib
import json

REPO = Path('/Users/l/Project/Recommandation')
BASE = REPO / 'runs/diagnostics/assigned_slow_target_20261021_v1'
TEMP = BASE / 'driver/temp-native-preflight'
SOURCE = REPO / 'runs/diagnostics/reviewed_slow_feedback_stage_20261021_v1'
OWN = Path(__file__).resolve().parent
bindings = {}


def sha(path):
    path = Path(path)
    value = hashlib.sha256(path.read_bytes()).hexdigest()
    bindings[str(path)] = value
    return value


def read(path):
    path = Path(path)
    assert path.name != 'approved_cases.json'
    sha(path)
    return json.loads(path.read_text())


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


if __name__ == '__main__':
    execution = read(BASE / 'driver/temp-native-preflight-result.json')
    assert execution['before'] == execution['after']
    for path, expected in execution['after'].items():
        assert sha(path) == expected
    assert execution['counts'] == {'exchange_receive': 0}
    assert execution['result']['status'] == 'prepared_not_dispatched'
    manifest = read(TEMP / 'manifest.json')
    assert digest({k: v for k, v in manifest.items() if k != 'manifest_hash'}) == manifest['manifest_hash'] == execution['result']['manifest_hash']
    assert manifest['manifest_hash'] == '0f7035105d0ad2ec9e943961f936f079498a19440a0cc4d479570efa785e93ca'
    saved = read(TEMP / 'preflight-wire.json')
    source_inbox = read(manifest['first_wire']['path'])
    assert sha(manifest['first_wire']['path']) == manifest['first_wire']['sha256']
    original = json.loads(next(m['content'] for m in source_inbox['messages'] if m['role'] == 'user'))
    assert saved['actual_user'] == saved['expected_user'] == original and saved['equal'] is True
    requests = list((TEMP / 'preflight/requests').glob('*.json'))
    assert len(requests) == 1
    journal = read(requests[0])
    request = journal['request']
    assert digest(request) == journal['request_hash'] == requests[0].stem
    actual = json.loads(next(m['content'] for m in request['messages'] if m['role'] == 'user'))
    assert actual == original
    system = next(m['content'] for m in request['messages'] if m['role'] == 'system')
    old_system = next(m['content'] for m in source_inbox['messages'] if m['role'] == 'system')
    native, assignment = system.split('\nThis independent child module ', 1)
    assert native == old_system.split('\nThis frozen diagnostic module ', 1)[0]
    assert 'reflection-7d08d205fe330564' in assignment
    assert 'repair_dependency' not in assignment and 'validation failures' not in assignment
    factory = read(SOURCE / 'factory-input.json')
    assert actual['slow_method_memory'] == factory['slow_method_memory']
    assert actual['meta_memory_disclosures'] == factory['meta_memory_disclosures']
    entries = actual['slow_method_memory']['source_entries']
    assert len(entries) == 6 and all('H1' in row['visible_to'] for row in entries)
    assert actual['slow_method_memory']['memory_deltas'][0]['memory_hash'] == manifest['accepted_memory_hash']
    assert len(factory['backlog_needs']) == 265
    assert actual['backlog_disclosure']['backlog_hash'] == digest(factory['backlog_needs'])
    assert actual['need_disposition_contract']['pending_count'] == 265
    assert actual['need_disposition_contract']['staged_count'] == 0
    assert actual['need_disposition_contract']['base_hash'] == '25c45c0c801f27f5c0aa394752234c38484039befe27548e15465b35ac845319'
    assert actual['last_action_result']['result']['cursor'] == 259
    assert actual['meta_info'] == original['meta_info']
    assert actual['meta_info']['counts'] == {'available': 235, 'deferred': 233, 'included': 2}
    assert not list((TEMP / 'exchange').rglob('*inbox*'))
    assert sorted(str(p.relative_to(TEMP / 'exchange')) for p in (TEMP / 'exchange').rglob('*') if p.is_file()) == ['contract.json']
    assert not (BASE / 'stage').exists()
    reservation = len(json.dumps(request['messages'], ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()) + request['max_output_tokens']
    assert reservation < 131072 and manifest['max_calls'] == 3 and manifest['total_cap'] == 393216
    assert (TEMP / 'run_contract.json').read_bytes() == (TEMP / 'workspace/run_contract.json').read_bytes()
    sha(TEMP / 'run_contract.json')
    sha(TEMP / 'workspace/run_contract.json')
    read(BASE / 'driver/temp-native-preflight.py') if False else sha(BASE / 'driver/temp-native-preflight.py')
    previous = read(OWN / 'candidate-static-review.json')
    assert previous['observed_candidate_bindings'] == execution['after']
    report = {'status': 'PASS_bounded_candidate_preflight; no_actual_fresh_response',
        'temp_manifest_hash': manifest['manifest_hash'], 'actual_native_user_complete_equal_to_original': True,
        'original_controller_native_system_prefix_equal': True,
        'only_declared_system_difference': 'Assigned native target ref plus execution restrictions; no route, diagnosis or expected answer supplied.',
        'materialized_frontier': {'backlog': 265, 'staged': 0, 'base_hash': actual['need_disposition_contract']['base_hash'],
            'six_complete_source_entries_and_exact_scopes': True, 'six_meta_original_disclosures_exact': True,
            'memory_delta_hash': manifest['accepted_memory_hash'], 'index_initial_counts': actual['meta_info']['counts'],
            'comparison_index_block': 'Shared production helper AST exactly retains source comparison originals, H1 scope filter, episodes and source aliases (separate candidate-static-review). Native initial indexed view now actually matches the old view.',
            'controlled_page_cursor': 259},
        'execution_evidence': {'executor_temp_seconds': execution['seconds'], 'executor_receive_calls': 0,
            'exchange_only_contract_no_inbox_receipt_raw': True, 'formal_root_absent': True,
            'one_native_request_journal': journal['request_hash'], 'logical_reservation': reservation,
            'source_code_spec_test_before_after_current_exact': True},
        'native_connection_review': 'The executor test patches only the temporary fixed destination and exchange.receive denial. It does not mock Engine/Workspace/Registry/index/store construction or the factory helpers. The saved native request and complete user equality close the previously missing constructor-to-egress connection for this fixture.',
        'limits': ['Reviewer did not call prepare/advance/Store/Engine/model/Signal/GET/LabelStore; this script only parses retained artifacts and hashes.',
            'The initial native index disclosure is verified. No new memory browsing request was performed, and omitted original branches are supported by extraction equality, not fresh execution of every page.',
            'Temporary destination was explicitly patched for this executor check; formal fixed-root behavior remains the separately reviewed code/control boundary.',
            'No answer, correction, intent, target semantics, publication, completed Slow cycle or benefit is established. Original v1 target0/1 remains unchanged.',
            'Hashes and native wire equivalence are connection evidence, not semantic proof of a future answer.'],
        'bindings': bindings}
    sha(Path(__file__))
    path = OWN / 'candidate-preflight-final-review.json'
    path.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'sha256': sha(path), 'reservation': reservation}))
