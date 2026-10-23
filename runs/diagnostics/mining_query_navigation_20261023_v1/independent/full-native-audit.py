"""Read persisted files only; never import/run the native probe or stage."""
from pathlib import Path
import json
import hashlib

ROOT = Path.cwd()
BASE = ROOT / 'runs/diagnostics/mining_query_navigation_20261023_v1'
STAGE = ROOT / 'runs/diagnostics/icfr_native_capability_20261023_v1/stage-v3'
OUT = BASE / 'independent'
def read(path): return json.loads(path.read_text())
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def compact(value): return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
def cbytes(value): return len(compact(value))
result = read(BASE / 'full-native-result.json')
contract = read(STAGE / 'contract.json')
completion = read(STAGE / 'completion.json')
manifest = read(STAGE / 'manifest.json')
assert contract['scope_limits']['mining'] == [80, 12582912]
old = []
for path in sorted((STAGE / 'exchange/receipts').glob('*.json')):
    receipt = read(path)
    inbox = STAGE / 'exchange/inbox' / (receipt['request_hash'] + '.json')
    raw = STAGE / 'exchange/outbox' / (receipt['request_hash'] + '.txt')
    assert sha(inbox) == receipt['inbox_sha256']
    assert sha(raw) == receipt['raw_output_sha256']
    request = read(inbox)
    assert request['request_hash'] == receipt['request_hash']
    old.append({'agent_id': receipt['agent_id'], 'request_hash': receipt['request_hash'],
                'reservation': cbytes(request['messages']) + request['max_output_tokens']})
old.sort(key=lambda row: int(row['agent_id'].rsplit('h', 1)[1]))
assert len(old) == 10
assert sum(row['reservation'] for row in old) == 2055941
assert len(list((STAGE / 'exchange/inbox').glob('*.json'))) == 10
assert len(list((STAGE / 'exchange/outbox').glob('*.txt'))) == 10
assert [int(row['agent_id'].rsplit('h', 1)[1]) for row in old] == list(range(1, 11))
requests = []
for name in ('after_hypothetical_query-request.json', 'after_hypothetical_read-request.json'):
    path = BASE / name
    request = read(path)
    payload = json.loads(request['messages'][1]['content'])
    budget = payload['request_budget']
    reservation = cbytes(request['messages']) + request['max_output_tokens']
    assert int(budget['this_request']) == reservation
    assert budget['used'] == 2055941 and budget['calls_used'] == 10
    assert budget['single_limit'] == 262144 and budget['total_limit'] == 12582912 and budget['call_limit'] == 80
    assert int(budget['remaining_after']) == 12582912 - 2055941 - reservation
    assert budget['calls_remaining_after'] == 69
    assert reservation <= 262144 and request['max_output_tokens'] == 4000
    # artifacts.canonical_json_hash uses ensure_ascii=True, while cost bytes
    # intentionally use ensure_ascii=False. Verify their distinct encodings.
    hash_bytes = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(',', ':')).encode('utf-8')
    assert request['stage_contract']['payload_hash'] == hashlib.sha256(hash_bytes).hexdigest()
    assert request['stage_contract']['payload_utf8_bytes'] == cbytes(payload)
    assert request['stage_contract']['stage'] == request['stage'] == 'mining_controller_step'
    assert payload['query_navigation']['counts']['available'] == 4
    requests.append({'file': name, 'file_sha256': sha(path),
        'messages_utf8_json_bytes': cbytes(request['messages']), 'output_reserve': request['max_output_tokens'],
        'bytes_plus_output': reservation, 'remaining_if_dispatched': int(budget['remaining_after']),
        'used_preserved': budget['used'], 'calls_used_preserved': budget['calls_used'],
        'tool_budget': payload['budget'], 'navigation_hints': len(payload['query_navigation']['items'])})
assert [row['bytes_plus_output'] for row in requests] == result['costs'] == [232555, 234197]
assert all(sha(STAGE / key) == value for key, value in completion['files'].items())
assert len([path for path in STAGE.rglob('*') if path.is_file()]) == 316
sources = [row for row in manifest['source_bindings'] if 'document_id' in row]
assert len(sources) == 263
assert all(sha(Path(row['path'])) == row['sha256'] for row in sources)
for row in result['query_navigation']['items']:
    matches = [source for source in sources if 'document-' + source['document_id'] == row['document_ref']]
    assert len(matches) == 1
    document = read(Path(matches[0]['path']))
    raw = document['content'][row['raw_start']:row['raw_end']]
    assert hashlib.sha256(raw.encode()).hexdigest() == row['raw_span_sha256']
    assert document['content_hash'] == row['content_hash']
assert result['fresh_answers'] == 0 and result['original_saved_answers_replayed'] == 10
assert result['original_spent_preserved'] == [10, 2055941]
assert result['proof_scope'] == 'offline old-action reconstruction plus explicit hypothetical query/read; not fresh behavior or stage continuation'
assert completion['result']['status'] == 'terminal_resource_or_control_stop'
assert all(sha(Path(row['path'])) == row['sha256'] for row in result['tested_files'])
review = {'scope': 'read-only file/hash/accounting review; probe was not rerun', 'status': 'pass',
    'original_receipts': old, 'original_total_reservation': 2055941, 'original_inboxes': 10, 'original_outboxes': 10,
    'requests': requests, 'sealed_hash_table_entries_verified': len(completion['files']), 'sealed_current_files': 316,
    'source_bindings_verified': 263, 'tested_files_hashes_verified': len(result['tested_files']),
    'original_terminal_status': completion['result']['status'], 'fresh_answers': 0,
    'first_probe_failure_preserved': (BASE / 'full-native-first.log').exists(),
    'first_review_harness_failure_preserved': (OUT / 'full-native-audit-first.log').exists(),
    'interpretation': 'Prospective captures for two hypothetical tool states, each retaining the same original spent prefix. Neither capture was dispatched or consumed. Bytes-plus-output is logical reservation; host tokens and currency cost are not measured. This does not reopen the terminal stage.'}
(OUT / 'full-native-readonly-review.json').write_text(json.dumps(review, indent=2) + '\n')
print(json.dumps(review, indent=2))
