"""Read-only evidence for a parent stop decision; never submit the pending answer."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path('/Users/l/Project/Recommandation')
sys.path.insert(0, str(ROOT))
from scripts import run_icfr_native_capability_stage as stage

OUT = Path(__file__).resolve().parent


def key(row):
    return row['content_hash'], row['offset'], row['length']


def window_map(observation):
    result = {}
    for evidence in observation['evidence'].values():
        for row in evidence.get('read_windows', []):
            result[key(row)] = row
    return result


def main():
    root = stage.STAGE_ROOT
    code = stage._code()
    stage.verify(root)
    views = {}
    bindings = []
    for path in (root / 'exchange/inbox').glob('*.json'):
        inbox = stage.read(path)
        view = json.loads(next(m['content'] for m in inbox['messages'] if m['role'] == 'user'))
        number = view['request_budget']['calls_used'] - 9
        if number in (8, 9, 10, 11, 12, 25, 26, 27):
            views[number] = (path, view)
            bindings.append(stage.binding(path))
    assert set(views) == {8, 9, 10, 11, 12, 25, 26, 27}
    observations = {}
    for path in (root / 'seeds/hypothesis/observations').glob('*.json'):
        value = stage.read(path)
        count = len(value['ledger']['entries'])
        if count in (24, 25, 26):
            observations[count] = value
            bindings.append(stage.binding(path))
    assert set(observations) == {24, 25, 26}
    units = {n: window_map(value) for n, value in observations.items()}
    assert len(units[24]) == len(units[25]) == len(units[26]) == 16
    assert units[24] == units[25] == units[26], 'a substantive source window changed'
    source_rows = stage.read(stage.MATERIAL / 'material-obligations-frozen.json')['source_document_bindings']
    by_hash = {row['content_hash']: row for row in source_rows}
    checked = []
    costs = []
    for number, original in ((25, 8), (26, 10), (27, 11)):
        inbox_path, view = views[number]
        old_path, old_view = views[original]
        h, old_h = inbox_path.stem, old_path.stem
        raw_path = root / 'exchange/outbox' / (h + '.txt')
        old_raw_path = root / 'exchange/outbox' / (old_h + '.txt')
        action, old_action = json.loads(raw_path.read_text()), json.loads(old_raw_path.read_text())
        assert action['action'] == old_action['action'] == 'read_span'
        assert (action['offset'], action['length']) == (old_action['offset'], old_action['length'])
        known = next(row for row in view['narrative_read_progress']['items']
                     if row['offset'] == action['offset'] and row['length'] == action['length'])
        original_unit = units[24][key(known)]
        source = by_hash[known['content_hash']]
        document = stage.read(source['path'])
        raw_slice = document['content'][action['offset']:action['offset'] + action['length']]
        assert hashlib.sha256(raw_slice.encode()).hexdigest() == original_unit['verbatim_hash']
        assert known['verbatim_hash'] == original_unit['verbatim_hash']
        assert key(known) in {key(row) for row in view['narrative_read_evidence']['omitted_entries']}
        item = {'new_answer': number, 'original_answer': original,
                'raw_action': action, 'new_raw': stage.binding(raw_path),
                'old_raw': stage.binding(old_raw_path), 'source': stage.binding(source['path']),
                'content_hash': known['content_hash'], 'raw_span_sha256': original_unit['verbatim_hash'],
                'prior_read_count': known['read_count'], 'is_currently_omitted': True,
                'submitted': number < 27}
        bindings.extend([stage.binding(raw_path), stage.binding(old_raw_path), stage.binding(source['path'])])
        if number < 27:
            later = views[number + 1][1]
            result = later['last_action_result']
            old_result = views[original + 1][1]['last_action_result']
            assert result['verbatim_hash'] == old_result['verbatim_hash'] == original_unit['verbatim_hash']
            assert result['offset'] == old_result['offset'] == action['offset']
            assert result['length'] == old_result['length'] == action['length']
            assert result['masked'] == old_result['masked'], 'reread changed actual visible text'
            refreshed = next(row for row in later['narrative_read_evidence']['items'] if key(row) == key(known))
            assert refreshed['read_count'] == 2 and known['read_count'] == 1
            assert refreshed['readable_text'] == result['masked']
            before = {key(row) for row in view['narrative_read_evidence']['items']}
            after = {key(row) for row in later['narrative_read_evidence']['items']}
            restored, evicted = after - before, before - after
            assert restored == {key(known)} and len(evicted) == 1
            next_path = views[number + 1][0]
            next_action = json.loads((root / 'exchange/outbox' / (next_path.stem + '.txt')).read_text())
            evicted_key = next(iter(evicted))
            assert (next_action['offset'], next_action['length']) == evicted_key[1:]
            for field in ('evidence_digest', 'known_fact_refs', 'known_relation_refs', 'known_event_refs',
                          'backlog_needs', 'backlog_disclosure', 'signal_catalog'):
                assert view[field] == later[field], field
            # Request-local identity aliases can change when read units reorder;
            # compare immutable actual observations rather than their alias spelling.
            old_catalog, new_catalog = view['catalog_observations'], later['catalog_observations']
            assert all(old_catalog[name] == new_catalog[name] for name in old_catalog if name != 'items')
            assert len(old_catalog['items']) == len(new_catalog['items'])
            for before_catalog, after_catalog in zip(old_catalog['items'], new_catalog['items']):
                for name in ('observation_ref', 'response_hash', 'source_snapshot_hash', 'source_snapshot_matches'):
                    assert before_catalog[name] == after_catalog[name]
            receipt_path = root / 'exchange/receipts' / (h + '.json')
            cache_path = root / 'transport/cache/responses' / (h + '.json')
            receipt, cache = stage.read(receipt_path), stage.read(cache_path)
            assert cache['raw_output'] == raw_path.read_text() and cache['json_output'] == action
            assert receipt['raw_output_sha256'] == stage.binding(raw_path)['sha256']
            assert receipt['agent_id'] == cache['usage']['agent_id'] == '/root/icfr_v4_h%03d' % number
            cost = cache['usage']['accounting_tokens']
            assert later['request_budget']['used'] - view['request_budget']['used'] == cost
            costs.append(cost)
            item.update(restored=list(restored), evicted=list(evicted),
                        next_authored_read_selects_evicted_unit=True,
                        visible_text_and_source_fields_equal=True, reservation=cost)
            bindings.extend([stage.binding(receipt_path), stage.binding(cache_path)])
        checked.append(item)
    progress_path = root / 'progress.json'
    progress = stage.read(progress_path)
    pending_hash = views[27][0].stem
    assert progress['status'] == 'pending_independent_role'
    assert progress['pending']['request_hash'] == pending_hash
    assert not (root / 'completion.json').exists() and not (root / 'failure.json').exists()
    assert not (root / 'exchange/receipts' / (pending_hash + '.json')).exists()
    assert not (root / 'transport/cache/responses' / (pending_hash + '.json')).exists()
    consumption = stage.Budget(root).consumption()
    assert consumption == {'historical': [10, 2055941], 'newly_answered': [26, 5367457],
                           'combined': [36, 7423398]}
    latest = observations[26]['ledger']['entries']
    assert not any(row['action'] in ('propose_candidate', 'record_no_pattern', 'record_deferred',
                                     'record_need_dispositions') for row in latest)
    assert latest[24]['action'] == latest[25]['action'] == 'read_span'
    state = stage.read(root / 'workspace/state.json')
    cycle = stage.read(root / 'workspace/cycle_state.json')
    assert state['last_completed_round'] == cycle['last_completed_cycle'] == 0
    assert not (root / 'mining-output.json').exists()
    bindings.append(stage.binding(progress_path))
    stage._check(bindings + code)
    stage._check(stage.read(OUT / 'equivalence-evidence.json')['original_oracles'])
    result = {'reviewer': '/root/budget_counterreview', 'at_utc': datetime.now(timezone.utc).isoformat(),
              'question': 'Recent reread information increment and rolling working-page omissions',
              'actual_two_rereads': checked[:2], 'prepared_unsubmitted_third_reread': checked[2],
              'static_bindings': bindings, 'consumption': consumption,
              'two_reread_reservations': sum(costs), 'unique_read_units_before_after': [16, 16, 16],
              'source_read_document_count': len({row['document_ref'] for row in units[24].values()}),
              'fact_count': views[27][1]['evidence_digest']['fact_count'],
              'relation_count': views[27][1]['evidence_digest']['relation_count'],
              'event_count': views[27][1]['evidence_digest']['event_count'],
              'facts_relations_events_backlog_catalog_and_source_units_unchanged': True,
              'new_candidate_count': 0, 'new_independent_sources_from_two_rereads': 0,
              'new_source_facts_from_two_rereads': 0, 'current_working_page_restored': True,
              'parent_stop_evidence_supported': True,
              'stop_meaning': 'Discretionary low-information-increment stop for this repeated-read strategy; retain exact native pending status and original fixed denominators.',
              'not_established': ['infinite loop', 'a code defect', 'unavoidable failure',
                                  'author mental state', 'third read cannot enable synthesis',
                                  'no pattern exists', 'budget exhaustion', 'candidate capability passed'],
              'native_state': progress, 'completed_business_pointers': [0, 0],
              'stage_product_or_oracle_writes': 0, 'answer_submissions_network_or_research_actions': 0}
    (OUT / 'reread-frontier-evidence.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'two_same_source_rereads': 2, 'rolling_omissions_followed': 2,
                      'reread_cost': sum(costs), 'new_source_units': 0,
                      'new_independent_sources': 0, 'new_candidates': 0,
                      'native_pending': pending_hash, 'third_answer_submitted': False,
                      'consumption': consumption}))


if __name__ == '__main__':
    main()
