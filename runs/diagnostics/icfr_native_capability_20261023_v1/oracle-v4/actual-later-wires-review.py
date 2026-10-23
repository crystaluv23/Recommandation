"""Read-only fixed-prefix h008-h023 review, using h024 only as h023 consumer input."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path('/Users/l/Project/Recommandation')
sys.path.insert(0, str(ROOT))
from scripts import run_icfr_native_capability_stage as stage
from stock_opportunity_agent.research.mining_controller import _action_arguments

OUT = Path(__file__).resolve().parent
STAGE = stage.STAGE_ROOT


def visible_fragment(document, offset, length):
    """Independently strip this actual window's markup, respecting a partial first tag."""
    raw = document[offset:offset + length]
    if document.rfind('<', 0, offset) > document.rfind('>', 0, offset):
        raw = raw[raw.find('>') + 1:]
    return ' '.join(re.sub(r'<[^>]*$', '', re.sub(r'<[^>]*>', ' ', raw)).split())


def identity_only(original, masked):
    """Permit only explicit identity placeholders; return substitutions for review."""
    if original == masked:
        return []
    pattern = re.escape(masked)
    pattern = pattern.replace(re.escape('[MASKED_COMPANY]'), '(.+?)')
    match = re.fullmatch(pattern, original)
    assert match is not None, 'masked readable text changed outside explicit identity markers'
    return list(match.groups())


def main():
    code = stage._code()
    stage.verify(STAGE)
    records = stage.Budget(STAGE).records()
    prefix = stage.read(STAGE / 'contract.json')['historical_resource_prefix']
    assert prefix['answered_usage'] == [10, 2055941]
    stage._terminal_resource_prefix(prefix)
    wire_by_number = {}
    for path in (STAGE / 'exchange/inbox').glob('*.json'):
        inbox = stage.read(path)
        view = json.loads(next(m['content'] for m in inbox['messages'] if m['role'] == 'user'))
        number = view['request_budget']['calls_used'] - 9
        if 1 <= number <= 24:
            assert number not in wire_by_number
            wire_by_number[number] = (path, inbox, view)
    assert set(wire_by_number) == set(range(1, 25)), 'need complete immutable first24 inbox prefix'
    observations = []
    for path in (STAGE / 'seeds/hypothesis/observations').glob('*.json'):
        observation = stage.read(path)
        if len(observation['ledger']['entries']) == 23:
            observations.append((path, observation))
    assert len(observations) == 1
    observation_path, observation = observations[0]
    ledger = observation['ledger']['entries']
    source_rows = stage.read(stage.MATERIAL / 'material-obligations-frozen.json')['source_document_bindings']
    stage._check(source_rows)
    by_content = {row['content_hash']: row for row in source_rows}
    source_cache = {}
    read_windows = {}
    for evidence in observation['evidence'].values():
        for read in evidence.get('read_windows', []):
            key = (read['content_hash'], read['offset'], read['length'])
            if key in read_windows:
                assert read_windows[key] == read
            read_windows[key] = read
    assert len(read_windows) == sum(row['action'] == 'read_span' for row in ledger) == 15
    bindings = [stage.binding(observation_path)]
    static = []
    reservations = []
    actions = []
    for number in range(1, 25):
        path, inbox, view = wire_by_number[number]
        h = path.stem
        wire_path = STAGE / 'transport/requests' / (h + '.json')
        wire = stage.read(wire_path)
        assert h == inbox['request_hash'] == stage.digest(wire['request'])
        assert wire['request']['messages'] == inbox['messages']
        cost = len(json.dumps(inbox['messages'], ensure_ascii=False, sort_keys=True,
                              separators=(',', ':')).encode()) + inbox['max_output_tokens']
        budget = view['request_budget']
        assert budget['calls_used'] == number + 9
        assert budget['used'] == 2055941 + sum(reservations)
        assert int(budget['this_request']) == cost
        assert int(budget['remaining_after']) == 12582912 - budget['used'] - cost
        assert budget['calls_remaining_after'] == 80 - 10 - number
        assert budget['single_limit'] == 262144 and cost <= 262144
        item = {'ordinal': number, 'request_hash': h, 'reservation': cost,
                'budget_used_before': budget['used'], 'inbox': stage.binding(path)}
        bindings.extend([stage.binding(path), stage.binding(wire_path)])
        if number <= 23:
            raw_path = STAGE / 'exchange/outbox' / (h + '.txt')
            cache_path = STAGE / 'transport/cache/responses' / (h + '.json')
            receipt_path = STAGE / 'exchange/receipts' / (h + '.json')
            receipt, cache = stage.read(receipt_path), stage.read(cache_path)
            action = json.loads(raw_path.read_text())
            assert cache['raw_output'] == raw_path.read_text() and cache['json_output'] == action
            assert receipt['agent_id'] == cache['usage']['agent_id'] == '/root/icfr_v4_h%03d' % number
            assert receipt['raw_output_sha256'] == stage.binding(raw_path)['sha256']
            assert receipt['inbox_sha256'] == stage.binding(path)['sha256']
            assert cache['usage']['accounting_tokens'] == records[h]['reservation'] == cost
            assert ledger[number - 1]['action'] == action['action']
            actions.append(action)
            item['action'] = action
            item['actor'] = receipt['agent_id']
            bindings.extend([stage.binding(raw_path), stage.binding(cache_path), stage.binding(receipt_path)])
        static.append(item)
        reservations.append(cost)

    baseline = stage.read(STAGE / 'inputs/baseline.json')
    baseline_by_ref = {row['signal_id'] + ':v' + str(row['version']): row for row in baseline['specs']}
    factory = stage.read(STAGE / 'inputs/factory.json')
    assert len(factory['backlog_needs']) == 265
    backlog = wire_by_number[8][2]['backlog_needs']
    backlog_disclosure = wire_by_number[8][2]['backlog_disclosure']
    catalog_checks, navigation_checks, retained_checks = [], [], []
    actual_navigation = {}
    for entry in ledger:
        for nav in entry['coverage'].get('query_navigation', []):
            actual_navigation[stage.digest(nav)] = nav
    for original in actual_navigation.values():
        content_hash = original['content_hash']
        row = by_content[content_hash]
        doc = source_cache.setdefault(content_hash, stage.read(row['path']))
        raw = doc['content'][original['raw_start']:original['raw_end']]
        assert hashlib.sha256(raw.encode()).hexdigest() == original['raw_span_sha256']
        assert row['case_ref'] == original['case_ref']
        assert datetime.fromisoformat(doc['published_at']) <= datetime.fromisoformat(row['cutoff'])
        assert datetime.fromisoformat(doc['available_at']) <= datetime.fromisoformat(row['cutoff'])
    for number in range(8, 25):
        _, _, view = wire_by_number[number]
        assert view['backlog_needs'] == backlog and view['backlog_disclosure'] == backlog_disclosure
        assert len(backlog) == 12 and backlog_disclosure['counts']['available'] == 265
        assert backlog_disclosure['counts']['omitted_after'] == 253
        cards = list(view['signal_catalog'])
        for retained in view['catalog_observations']['items']:
            if retained['scope'] == 'signals':
                assert retained['source_snapshot_matches']
                assert retained['response_hash'] == stage.digest(retained['result'])
                cards.extend(retained['result']['items'])
        assert len(cards) == 18 and {card['signal_ref'] for card in cards} == set(baseline_by_ref)
        for card in cards:
            for key, value in card['capability_contract'].items():
                assert baseline_by_ref[card['signal_ref']][key] == value
        catalog_checks.append(number)
        navigation = view['query_navigation']
        for nav in navigation['items']:
            original = actual_navigation[nav['navigation_ref']]
            assert nav['source_snapshot_matches']
            for key, value in original.items():
                if key != 'document_ref':
                    assert nav[key] == value
            assert nav['discovery_only'] and not nav['source_read_completed'] and not nav['candidate_citable']
        navigation_checks.append({'inbox': number, 'counts': navigation['counts']})
        page = view['narrative_read_evidence']
        progress = view['narrative_read_progress']
        assert page['counts']['included'] == len(page['items'])
        assert page['counts']['omitted_after'] == len(page['omitted_entries'])
        assert page['counts']['available'] == len(page['items']) + len(page['omitted_entries'])
        assert progress['counts']['available'] == page['counts']['available']
        expected_keys = set()
        for read in list(page['items']) + list(page['omitted_entries']):
            key = (read['content_hash'], read['offset'], read['length'])
            assert key in read_windows
            expected_keys.add(key)
        assert len(expected_keys) == page['counts']['available']
        for read in page['items']:
            original = read_windows[(read['content_hash'], read['offset'], read['length'])]
            for key in ('content_hash', 'verbatim_hash', 'offset', 'length', 'case_refs',
                        'source_type', 'published_at', 'available_at', 'next_readable_start'):
                assert read[key] == original[key]
            identity_only(original['readable_text'], read['readable_text'])
        retained_checks.append({'inbox': number, 'page_counts': page['counts'],
                                'progress_counts': progress['counts'], 'omitted_units': page['omitted_entries']})
    source_checks = []
    for number, action in enumerate(actions, 1):
        if action['action'] != 'read_span':
            continue
        response = wire_by_number[number + 1][2]['last_action_result']
        assert response['action'] == 'read_span'
        key = next(key for key, value in read_windows.items()
                   if value['offset'] == action['offset'] and value['length'] == action['length']
                   and value['case_refs'] == response['case_refs'])
        original = read_windows[key]
        row = by_content[key[0]]
        doc = source_cache.setdefault(key[0], stage.read(row['path']))
        raw = doc['content'][key[1]:key[1] + key[2]]
        assert hashlib.sha256(raw.encode()).hexdigest() == original['verbatim_hash'] == response['verbatim_hash']
        assert len(raw) == action['length'] == response['raw_window_chars']
        assert visible_fragment(doc['content'], key[1], key[2]) == original['readable_text']
        replacements = identity_only(original['readable_text'], response['masked'])
        canonical_action = {**action, 'document_ref': 'document-' + doc['document_id']}
        assert ledger[number - 1]['input_hash'] == stage.digest({
            'action': 'read_span', 'args': _action_arguments(canonical_action)})
        source_checks.append({'answer': number, 'case_refs': original['case_refs'],
                              'source': stage.binding(row['path']), 'offset': key[1], 'length': key[2],
                              'raw_sha256': original['verbatim_hash'], 'readable_chars': len(original['readable_text']),
                              'explicit_identity_substitutions': replacements})
    stage._check(bindings + code + source_rows)
    stage._check(stage.read(OUT / 'equivalence-evidence.json')['original_oracles'])
    answered = sum(reservations[:23])
    action_counts = {name: sum(row['action'] == name for row in ledger)
                     for name in sorted({row['action'] for row in ledger})}
    assert action_counts == {'fetch_evidence': 4, 'inspect_catalog': 4, 'read_span': 15}
    result = {'reviewer': '/root/budget_counterreview', 'at_utc': datetime.now(timezone.utc).isoformat(),
              'scope': 'answers_h008_h023_and_actual_following_inputs_through_h024; h024 answer excluded',
              'findings': [], 'immutable_artifact_bindings': bindings,
              'actual_answered_prefix': static[:23], 'h024_input_only': static[23],
              'answered_prefix_new_usage': [23, answered], 'answered_prefix_combined_usage': [33, 2055941 + answered],
              'historical_usage': [10, 2055941], 'old_limits_unchanged': True,
              'source_read_checks': source_checks, 'unique_read_units': len(read_windows),
              'retained_catalog_checks': catalog_checks, 'retained_read_checks': retained_checks,
              'backlog': {'available': 265, 'included': 12, 'omitted_after': 253,
                          'unchanged_hash': backlog_disclosure['backlog_hash'], 'changed_or_consumed_needs': 0},
              'unique_actual_query_origins_verified': len(actual_navigation), 'query_navigation_checks': navigation_checks,
              'source_product_original_oracle_hashes_unchanged': True,
              'actual_native_action_counts': action_counts,
              'new_candidates_in_23_action_ledger': sum(row['action'] == 'propose_candidate' for row in ledger),
              'review_script': stage.binding(Path(__file__)),
              'network_or_author_actions_or_stage_writes': 0,
              'not_claimed': ['full source semantic admission', 'candidate generation', 'technical admission',
                              'four consumers', 'full F5', 'MVP', 'A implementation']}
    (OUT / 'actual-later-wires-evidence.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'findings': [], 'new_answered_usage': [23, answered],
                      'combined_usage': [33, 2055941 + answered], 'actual_read_units': len(read_windows),
                      'unique_query_origins': len(actual_navigation), 'catalog_refs': 18,
                      'backlog_visible': 12, 'backlog_total': 265}))


if __name__ == '__main__':
    main()
