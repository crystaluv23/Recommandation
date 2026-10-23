"""Read-only snapshot review of the first four actual v4 native inboxes."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path('/Users/l/Project/Recommandation')
sys.path.insert(0, str(ROOT))
from scripts import run_icfr_native_capability_stage as stage
from stock_opportunity_agent.research.mining_controller import _action_arguments

OUT = Path(__file__).resolve().parent
HASHES = [
    'ea4652362fe82a728ddd63914d3bc591e3813f819fac8c3602deed8a5d976df3',
    '7950cc4da9f3c16971710ca8e501b019d6b2441f7ef0b45ab2fe74e817475ef0',
    '09bbc6852bdd654cfe47222a810bbf3dbba5b304b1636732f944eb9afe8566f7',
    '10a60089f960db5367e85f0bb31d2b348e3b8ff73ec6279975ebc3b3c97b2acc']


def main():
    root = stage.STAGE_ROOT
    code = stage._code()
    stage.verify(root)
    records = stage.Budget(root).records()
    prefix = stage.read(root / 'contract.json')['historical_resource_prefix']
    assert stage._terminal_resource_prefix(prefix) == prefix['answered_records']
    assert prefix['answered_usage'] == [10, 2055941]
    first = []
    retained = []
    costs = []
    views = []
    for index, h in enumerate(HASHES):
        path = root / 'exchange/inbox' / (h + '.json')
        inbox = stage.read(path)
        envelope = stage.read(root / 'transport/requests' / (h + '.json'))
        assert inbox['request_hash'] == h == stage.digest(envelope['request'])
        assert inbox['messages'] == envelope['request']['messages']
        cost = len(json.dumps(inbox['messages'], ensure_ascii=False, sort_keys=True,
                              separators=(',', ':')).encode()) + inbox['max_output_tokens']
        view = json.loads(next(m['content'] for m in inbox['messages'] if m['role'] == 'user'))
        views.append(view)
        budget = view['request_budget']
        assert budget['calls_used'] == 10 + index and budget['used'] == 2055941 + sum(costs)
        assert int(budget['this_request']) == cost
        assert int(budget['remaining_after']) == 12582912 - budget['used'] - cost
        assert budget['calls_remaining_after'] == 80 - 10 - index - 1
        assert budget['single_limit'] == 262144 and cost <= 262144
        assert budget['call_limit'] == 80 and budget['total_limit'] == 12582912
        retained.append(stage.binding(path))
        item = {'ordinal': index + 1, 'request_hash': h, 'cost': cost,
                'request_budget': budget, 'inbox': stage.binding(path),
                'wire': stage.binding(root / 'transport/requests' / (h + '.json'))}
        if index < 3:
            raw = root / 'exchange/outbox' / (h + '.txt')
            receipt_path = root / 'exchange/receipts' / (h + '.json')
            cache_path = root / 'transport/cache/responses' / (h + '.json')
            receipt, cache = stage.read(receipt_path), stage.read(cache_path)
            assert receipt['agent_id'] == '/root/icfr_v4_h%03d' % (index + 1)
            assert cache['raw_output'] == raw.read_text()
            assert cache['json_output'] == json.loads(raw.read_text())
            assert cache['usage']['agent_id'] == receipt['agent_id']
            assert cache['usage']['accounting_tokens'] == cost == records[h]['reservation']
            assert receipt['inbox_sha256'] == stage.binding(path)['sha256']
            assert receipt['raw_output_sha256'] == stage.binding(raw)['sha256']
            item.update(agent_id=receipt['agent_id'], action=cache['json_output'],
                        raw=stage.binding(raw), receipt=stage.binding(receipt_path), cache=stage.binding(cache_path))
            retained.extend([stage.binding(raw), stage.binding(receipt_path), stage.binding(cache_path)])
        first.append(item)
        costs.append(cost)

    latest = views[-1]
    cards = list(latest['signal_catalog'])
    for observation in latest['catalog_observations']['items']:
        assert observation['source_snapshot_matches']
        assert observation['response_hash'] == stage.digest(observation['result'])
        cards.extend(observation['result']['items'])
    baseline = stage.read(root / 'inputs/baseline.json')
    specs = {spec['signal_id'] + ':v' + str(spec['version']): spec for spec in baseline['specs']}
    assert len(cards) == 18 and {card['signal_ref'] for card in cards} == set(specs)
    for card in cards:
        spec = specs[card['signal_ref']]
        for key, value in card['capability_contract'].items():
            assert spec[key] == value
    observations = []
    for path in (root / 'seeds/hypothesis/observations').glob('*.json'):
        observation = stage.read(path)
        entries = observation['ledger']['entries']
        if len(entries) == 3:
            observations.append((path, entries))
    assert len(observations) == 1
    path, entries = observations[0]
    fetch = first[2]['action']
    entry = entries[2]
    assert entry['action'] == fetch['action'] == 'fetch_evidence'
    assert entry['input_hash'] == stage.digest({'action': 'fetch_evidence', 'args': _action_arguments(fetch)})
    navigations = entry['coverage']['query_navigation']
    assert len(navigations) == latest['query_navigation']['counts']['available'] == 34
    source = stage.read(stage.MATERIAL / 'material-obligations-frozen.json')
    by_hash = {row['content_hash']: row for row in source['source_document_bindings']}
    checked_spans = []
    for nav in navigations:
        assert nav['query'] == fetch['query'] == 'internal control over financial reporting'
        assert nav['discovery_only'] and not nav['candidate_citable'] and not nav['source_read_completed']
        row = by_hash[nav['content_hash']]
        document = stage.read(row['path'])
        span = document['content'][nav['raw_start']:nav['raw_end']]
        assert hashlib.sha256(span.encode()).hexdigest() == nav['raw_span_sha256']
        assert row['case_ref'] == nav['case_ref'] and nav['raw_end'] - nav['raw_start'] == nav['read_length']
        assert datetime.fromisoformat(document['published_at']) <= datetime.fromisoformat(row['cutoff'])
        assert datetime.fromisoformat(document['available_at']) <= datetime.fromisoformat(row['cutoff'])
        checked_spans.append({'case_ref': nav['case_ref'], 'document_binding': stage.binding(row['path']),
                              'raw_start': nav['raw_start'], 'raw_end': nav['raw_end'],
                              'raw_span_sha256': nav['raw_span_sha256']})
    assert latest['query_navigation']['counts']['included'] == 8
    assert latest['query_navigation']['counts']['omitted_after'] == 26
    assert latest['query_navigation']['next_cursor'] == 8
    original_nav = {stage.digest(nav): nav for nav in navigations}
    for nav in latest['query_navigation']['items']:
        assert nav['source_snapshot_matches'] and nav['navigation_ref'] in original_nav
        original = original_nav[nav['navigation_ref']]
        for key, value in original.items():
            # Model-facing identity masking changes only document_ref here.
            if key != 'document_ref':
                assert nav[key] == value
    stage._check(retained + code)
    stage._check(stage.read(OUT / 'equivalence-evidence.json')['original_oracles'])
    result = {'reviewer': '/root/budget_counterreview', 'at_utc': datetime.now(timezone.utc).isoformat(),
              'scope': 'first_four_inboxes_and_first_three_answers_only', 'findings': [],
              'wires': first, 'retained_catalog_refs': sorted(specs),
              'retained_catalog_capability_contracts_equal_baseline': True,
              'fetch_ledger_observation': stage.binding(path), 'query_navigation_original_count': 34,
              'query_navigation_visible_count': 8, 'query_navigation_visible_omitted_after': 26,
              'query_navigation_span_checks': checked_spans,
              'first_three_new_reservations': sum(costs[:3]), 'first_three_combined_reservations': 2055941 + sum(costs[:3]),
              'historical_prefix': stage.binding(root / 'contract.json'), 'source_bindings_verified': True,
              'original_oracles_unchanged': True, 'runtime_bindings_equal_frozen': True,
              'no_stage_writes': True, 'no_model_authorship_or_network': True,
              'not_claimed': ['h004 answer correctness', 'source_read_or_measurement_completed', 'Mining candidate',
                              'technical admission', 'four consumers', 'MVP closure']}
    (OUT / 'actual-first-wires-review.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'findings': [], 'first_three_new_reservations': sum(costs[:3]),
                      'complete_catalog_refs_retained': 18, 'raw_navigation_spans_verified': len(checked_spans)}))


if __name__ == '__main__':
    main()
