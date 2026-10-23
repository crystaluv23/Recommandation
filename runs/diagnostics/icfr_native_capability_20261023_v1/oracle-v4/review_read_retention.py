"""Read-only original-source check of actual h004/h005 reads through h007 input."""
from copy import deepcopy
from datetime import datetime
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
HASHES = [
    '10a60089f960db5367e85f0bb31d2b348e3b8ff73ec6279975ebc3b3c97b2acc',
    'dd6cc39b3515776fc0ad10c04ab650eb9bd96681a058055c361582c7b6e9f431',
    '781a6746f5faff6c83fc4b2292b71689852c31f0070e4332547024f9ff0ad456',
    'd8a8e5e099435c83388e7dedb68b702d5cbe034abb0b5f135d39f3401f168ffc']


def main():
    root = stage.STAGE_ROOT
    stage.verify(root)
    code = stage._code()
    views, actions, bindings = [], [], []
    records = stage.Budget(root).records()
    for index, h in enumerate(HASHES):
        path = root / 'exchange/inbox' / (h + '.json')
        inbox = stage.read(path)
        views.append(json.loads(next(m['content'] for m in inbox['messages'] if m['role'] == 'user')))
        bindings.append(stage.binding(path))
        if index < 3:
            raw = root / 'exchange/outbox' / (h + '.txt')
            cache_path = root / 'transport/cache/responses' / (h + '.json')
            cache = stage.read(cache_path)
            assert cache['raw_output'] == raw.read_text()
            action = json.loads(raw.read_text())
            assert cache['json_output'] == action
            assert cache['usage']['agent_id'] == '/root/icfr_v4_h%03d' % (index + 4)
            assert cache['usage']['accounting_tokens'] == records[h]['reservation']
            actions.append(action)
            bindings.extend([stage.binding(raw), stage.binding(cache_path),
                             stage.binding(root / 'exchange/receipts' / (h + '.json'))])
    latest = views[3]
    material = stage.read(stage.MATERIAL / 'material-obligations-frozen.json')
    stage._check(material['source_document_bindings'])
    sources = {row['content_hash']: row for row in material['source_document_bindings']}
    retained = latest['narrative_read_evidence']
    assert retained['counts']['available'] == retained['counts']['included'] == 2
    assert retained['counts']['omitted_after'] == 0 and retained['counts']['oversized'] == 0
    assert retained['selection_is_exhaustive'] and retained['next_cursor'] is None
    snapshots = []
    for path in (root / 'seeds/hypothesis/observations').glob('*.json'):
        observation = stage.read(path)
        if len(observation['ledger']['entries']) == 6:
            snapshots.append((path, observation))
    assert len(snapshots) == 1
    observation_path, observation = snapshots[0]
    entries = observation['ledger']['entries']
    checked_reads = []
    for index, action in enumerate(actions[:2]):
        result = views[index + 1]['last_action_result']
        assert action['action'] == result['action'] == 'read_span'
        assert result['offset'] == action['offset'] and result['length'] == action['length']
        read = next(row for row in retained['items']
                    if row['offset'] == action['offset'] and row['length'] == action['length'])
        source = sources[read['content_hash']]
        document = stage.read(source['path'])
        raw = document['content'][action['offset']:action['offset'] + action['length']]
        assert len(raw) == action['length'] == result['raw_window_chars']
        digest = hashlib.sha256(raw.encode()).hexdigest()
        assert digest == result['verbatim_hash'] == read['verbatim_hash']
        # These two actual fragments contain no scripts/hidden spans. Independent
        # tag removal and whitespace folding preserve their complete visible text;
        # an unfinished terminal HTML tag is markup, not source prose.
        visible = ' '.join(re.sub(r'<[^>]*$', '', re.sub(r'<[^>]*>', ' ', raw)).split())
        assert visible == result['masked'] == read['readable_text']
        assert result['case_refs'] == read['case_refs'] == [source['case_ref']]
        assert result['readable_chars'] == read['readable_chars'] == len(visible)
        assert read['published_at'] == document['published_at']
        assert read['available_at'] == document['available_at']
        assert datetime.fromisoformat(read['published_at']) <= datetime.fromisoformat(source['cutoff'])
        assert datetime.fromisoformat(read['available_at']) <= datetime.fromisoformat(source['cutoff'])
        canonical_ref = 'document-' + document['document_id']
        original_action = {**action, 'document_ref': canonical_ref}
        ledger = entries[index + 3]
        assert ledger['input_hash'] == stage.digest({'action': 'read_span', 'args': _action_arguments(original_action)})
        assert ledger['case_refs'] == [source['case_ref']] and ledger['evidence_refs'] == [canonical_ref]
        prior_units = views[2]['narrative_read_evidence']['items']
        prior = next(row for row in prior_units if row['content_hash'] == read['content_hash'])
        for key in ('content_hash', 'verbatim_hash', 'readable_text', 'offset', 'length', 'case_refs',
                    'source_type', 'published_at', 'available_at', 'next_readable_start'):
            assert prior[key] == read[key]
        checked_reads.append({'source': stage.binding(source['path']), 'case_ref': source['case_ref'],
                              'offset': action['offset'], 'length': action['length'],
                              'readable_chars': len(visible), 'raw_sha256': digest,
                              'h006_to_h007_read_fields_equal': True})
    # The refining query changes the most recent action, not the prior read units.
    query = actions[2]
    assert query['query'] == 'material weakness'
    assert entries[5]['input_hash'] == stage.digest({'action': 'fetch_evidence', 'args': _action_arguments(query)})
    navigation_counts = {}
    for entry in (entries[2], entries[5]):
        navs = entry['coverage']['query_navigation']
        for nav in navs:
            doc = stage.read(sources[nav['content_hash']]['path'])
            raw = doc['content'][nav['raw_start']:nav['raw_end']]
            assert hashlib.sha256(raw.encode()).hexdigest() == nav['raw_span_sha256']
            assert nav['discovery_only'] and not nav['source_read_completed'] and not nav['candidate_citable']
        navigation_counts[navs[0]['query']] = len(navs)
    assert navigation_counts == {'internal control over financial reporting': 34, 'material weakness': 31}
    assert latest['query_navigation']['counts'] == {
        'available': 65, 'included': 8, 'omitted_after': 57, 'omitted_before': 0, 'oversized': 0}
    assert {nav['query'] for nav in latest['query_navigation']['items']} == {'material weakness'}
    cards = list(latest['signal_catalog'])
    for catalog in latest['catalog_observations']['items']:
        assert catalog['source_snapshot_matches']
        cards.extend(catalog['result']['items'])
    baseline = stage.read(root / 'inputs/baseline.json')
    specs = {row['signal_id'] + ':v' + str(row['version']): row for row in baseline['specs']}
    assert len(cards) == 18 and {row['signal_ref'] for row in cards} == set(specs)
    for card in cards:
        for key, value in card['capability_contract'].items():
            assert specs[card['signal_ref']][key] == value
    stage._check(bindings + code + [stage.binding(observation_path)])
    stage._check(stage.read(OUT / 'equivalence-evidence.json')['original_oracles'])
    result = {'reviewer': '/root/budget_counterreview', 'scope': 'h004_h005_reads_through_h007_input_only',
              'findings': [], 'static_artifact_bindings': bindings,
              'native_six_action_observation': stage.binding(observation_path),
              'source_reads': checked_reads, 'catalog_exact_versions_retained': 18,
              'query_navigation_verified_counts': navigation_counts,
              'h007_navigation_counts': latest['query_navigation']['counts'],
              'h006_source_scope_rationale': query['rationale'],
              'independent_semantic_judgment': {
                  'case001': 'Cover-page auditor-attestation checkbox question; no management ICFR finding in this window.',
                  'case002': 'Effective disclosure controls at the quarter end and no materially affecting/reasonably likely materially affecting ICFR change during the three months ended 2025-03-31; not an annual ICFR-effectiveness or material-weakness conclusion.',
                  'h006_scope_summary': 'Faithful to both exact read windows; no absence, current-cutoff ICFR truth or directional benefit inferred.'},
              'runtime_original_oracle_and_source_bindings_unchanged': True,
              'stage_product_or_oracle_writes': 0, 'network_or_new_answers': 0,
              'not_claimed': ['h007_answer', 'candidate_semantics', 'full_F5', 'MVP']}
    (OUT / 'actual-read-retention-review.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'findings': [], 'actual_read_units_verified': 2,
                      'complete_catalog_retained': 18, 'query_origins_verified': 65}))


if __name__ == '__main__':
    main()
