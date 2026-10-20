"""Audit persisted native observations with stdlib only; never rerun a helper."""
from pathlib import Path
from datetime import datetime
from decimal import Decimal
import hashlib
import json

ROOT = Path('/Users/l/Project/Recommandation/runs/diagnostics/mining_native_evidence_probe_20261021_v1')
EXECUTION = ROOT / 'execution'
OWN = Path(__file__).resolve().parent
bindings = {}


def sha(path, retain=True):
    path = Path(path)
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1048576), b''):
            h.update(chunk)
    if retain:
        bindings[str(path)] = h.hexdigest()
    return h.hexdigest()


def read(path):
    path = Path(path)
    assert path.name not in {'approved_cases.json', 'input_manifest.json', 'labels.jsonl'}
    sha(path)
    return json.loads(path.read_text())


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def check_projection(output, document):
    records = [r for group in output['context']['concepts'] for r in group['records']]
    assert len(records) == output['context_record_count'] == len(output['record_shapes'])
    spans = set()
    for record in records:
        assert document['content'][record['start']:record['end']] == record['exact_span']
        json.loads(record['exact_span'])
        spans.add(record['exact_span'])
    assert len(output['facts']) == output['fact_count']
    for fact in output['facts']:
        assert fact['exact_span'] in spans
        assert fact['content_hash'] == document['content_hash']
        assert fact['document_ref'] == 'document-' + document['document_id']
        assert fact['value'] == str(json.loads(fact['exact_span'])['val'])
    return records


if __name__ == '__main__':
    result, observation = read(EXECUTION / 'result.json'), read(EXECUTION / 'observations.json')
    assert sha(EXECUTION / 'observations.json') == result['observations_sha256'] == '0472edbe90bc4b0a6876aedde9328ba0ea281efe3328c9c15db0fa814380c228'
    assert result['status'] == 'completed_native_diagnostic_not_capability_pass'
    seal = read(EXECUTION / 'completed-files.json')
    for relative, expected in seal.items():
        assert sha(EXECUTION / relative) == expected
    assert set(p.name for p in EXECUTION.iterdir() if p.is_file()) == set(seal) | {'completed-files.json'}
    plan = read(ROOT / 'plan.json')
    expected_bindings = {r['path']: r['sha256'] for r in plan['bindings']}
    assert len(expected_bindings) == len(plan['bindings']) == 4135
    assert observation['source_bindings_before'] == observation['source_bindings_after'] == expected_bindings
    current = {path: sha(path, retain=False) for path in expected_bindings}
    assert current == expected_bindings
    assert observation['all_frozen_bytes_unchanged'] is True and observation['forbidden_calls'] == {}
    inputs = read(plan['exact_inputs']['path']); expectations = read(plan['expectations']['path'])
    assert [r['id'] for r in expectations['controls']] == plan['controls']
    assert all(key in observation for key in plan['controls'])
    assert observation['frozen_expectations'] == expectations
    snapshot_root = Path(plan['reviewed_binding']['root'])
    snapshot = read(snapshot_root / 'reviewed_snapshot.json')
    assert len(snapshot['documents']) == observation['actual_snapshot_count'] == 1780
    by_id = {r['document_id']: r for r in snapshot['documents']}
    original = read(snapshot_root / by_id[inputs['original']['document_id']]['path'])
    assert hashlib.sha256(original['content'].encode()).hexdigest() == inputs['original']['content_hash']
    for witness in inputs['original']['rows']:
        assert original['content'][witness['offset_start']:witness['offset_end']] == witness['exact_span']
    selection = observation['O1-original-selection']
    candidates = selection['candidate_order_before_query']
    ids = [r['document']['document_id'] for r in candidates]
    assert len(ids) == 56 and ids == sorted(ids)
    assert set(ids) == {r['document_id'] for r in snapshot['documents'] if r['document_id'].startswith('secfacts:0000800457:')}
    for item in candidates:
        saved = read(snapshot_root / by_id[item['document']['document_id']]['path'])
        assert saved['company_id'] == inputs['case_original']['company_id']
        assert datetime.fromisoformat(saved['available_at']) <= datetime.fromisoformat(inputs['case_original']['prediction_time'])
        assert item['document']['canonical_record_hash'] == digest(saved)
    assert selection['selected_documents'][0]['document_id'] == ids[0] == original['document_id']
    assert selection['excluded_by_limits'] == ids[1:] and selection['unread_same_source'] is True
    o2 = observation['O2-original-context-and-projection']
    assert o2['matches_actual_selected'] is True
    records = check_projection(o2['output'], original)
    assert len(records) == 19 and o2['output']['fact_count'] == 0
    assert all('value' in json.loads(r['exact_span']) and 'val' not in json.loads(r['exact_span']) for r in records)
    ocf = [json.loads(r['exact_span']) for r in records if json.loads(r['exact_span'])['tag'] == 'NetCashProvidedByUsedInOperatingActivities']
    assert [(r['start'], r['end'], r['value']) for r in ocf] == [('2011-01-01', '2011-06-30', 9506313), ('2010-01-01', '2010-06-30', 4342261)]
    assert o2['output']['context']['partial'] is True and o2['output']['context']['omitted_concept_count'] == 91
    synthetic = {r['document']['document_id']: r['document'] for r in inputs['synthetic_controls']}
    for control, document_id in [('T1-small-typed-value', 'probe-typed-value'), ('P2-row-PIT', 'probe-typed-pit')]:
        out = observation[control]
        rows = [json.loads(r['exact_span']) for r in check_projection(out, synthetic[document_id])]
        assert len(rows) == 2 and out['fact_count'] == 0
        assert {r['value'] for r in rows} == {120, 100}
    for name in ('no_query', 'query_tie'):
        fetch = observation['P1-document-selection-and-PIT'][name]
        assert [d['document_id'] for d in fetch['selected_documents']] == ['probe-a-older']
        assert fetch['excluded_by_limits'] == ['probe-b-newer']
        assert [d['document_id'] for d in fetch['excluded_by_pit']] == ['probe-c-future']
    for control, document_id, fact_count in [('L1-legacy-val-positive', 'probe-a-older', 2), ('R1-role-unit-conflict', 'probe-typed-dual', 7)]:
        data = observation[control]
        check_projection(data['projection'], synthetic[document_id])
        assert data['projection']['fact_count'] == fact_count
        relation = data['relations_and_arithmetic']
        assert relation['facts'] == data['projection']['facts']
        facts = {r['fact_ref']: r for r in relation['facts']}
        pairs = {r['relation_ref']: [facts[ref] for ref in r['fact_refs']] for r in relation['relations']}
        assert relation['operand_details'] == list(pairs.values())
        for calculation in relation['arithmetic']:
            left, right = pairs[calculation['relation_ref']]
            assert calculation['output']['fact_refs'] == [left['fact_ref'], right['fact_ref']]
            a, b = Decimal(left['value']), Decimal(right['value'])
            value = a / b if calculation['rule'] == 'latest_over_comparable_prior' else a - b
            assert Decimal(calculation['output']['value']) == value
    r1 = observation['R1-role-unit-conflict']['relations_and_arithmetic']
    usd = next(pair for pair in r1['operand_details'] if pair[0]['unit'] == 'USD')
    eur = next(pair for pair in r1['operand_details'] if pair[0]['unit'] == 'EUR')
    assert [(r['value'], r['period']['start'], r['period']['end']) for r in usd] == [('120', '2024-01-01', '2024-06-30'), ('50', '2023-04-01', '2023-06-30')]
    assert [r['value'] for r in eur] == ['900', '800']
    usd_current = [r for r in r1['facts'] if r['unit'] == 'USD' and r['period']['end'] == '2024-06-30']
    assert [(r['value'], r['record_selection']) for r in usd_current] == [('120', 'latest'), ('60', 'comparable_prior'), ('121', 'comparable_prior')]
    test_source = ROOT.parents[2] / 'tests/test_mining_agent_tools.py'
    test_text = test_source.read_text(); sha(test_source)
    assert '"val": 1000' in test_text and '"val": 800' in test_text and 'sec-company-facts-document-v1' not in test_text
    report = {'status': 'CONFIRMED_three_distinct_frontiers; no_capability_pass',
        'actual_controls': {'O1': {'candidate_count': 56, 'selected_document': original['document_id'], 'available_at': original['available_at'], 'cap_excluded': 55,
            'finding': 'No-query native ID order selected an old2011 original, not latest. This is independent of fact adaptation.'},
            'O2': {'context_records': 19, 'facts': 0, 'context_partial': True, 'omitted_concepts': 91,
                'actual_OCF_literals_survived': True, 'finding': 'Unchanged typed value-only source reached a nonempty native context, but the val-only projector emitted no EvidenceFacts. Confirmed producer-consumer field adaptation defect, not evidence absence.'},
            'L1': {'context_records': 2, 'facts': 2, 'ratio': '1.200000', 'difference': '20.000000', 'meaning': 'Legacy val branch works on a unique synthetic same-duration pair.'},
            'T1': {'context_records': 2, 'facts': 0, 'meaning': 'Small isolated typed value-only control reproduces the adaptation gap without context budget pressure.'},
            'R1': {'synthetic_only': True, 'context_records': 7, 'facts': 7, 'relations': 2,
                'USD_operands': [{'value': r['value'], 'unit': r['unit'], 'period': r['period']} for r in usd],
                'USD_ratio': '2.400000', 'USD_difference': '70.000000', 'EUR_ratio': '1.125000', 'EUR_difference': '100.000000',
                'finding': 'Index-derived roles mark current same-end quarter60/conflicting halfyear121 as prior; last-write builder picks prior quarter50 against current halfyear120. This is not a valid comparable-period pair under the existing pair-builder contract. USD120vs121 remains an unresolved same-period conflict.',
                'arithmetic_limit': 'The numbers are mathematically correct for supplied refs. Generic arithmetic is not newly required to reject every differing unit/duration; valid economic basis must be established separately.'},
            'P1': {'older_selected_both_no_query_and_equal_query_tie': True, 'newer_cap_excluded': True, 'future_availability_excluded': True},
            'P2': {'context_valid_rows': 2, 'future_end_and_future_filed_rows_excluded': True, 'facts': 0}},
        'why_old_focused_tests_missed': 'tests/test_mining_agent_tools.py FACTS_CONTENT uses nested units.val and one unique current/prior pair per concept/unit. Its same-concept and arithmetic tests do not traverse typed facts[].value or multiple same-end duration/conflict alternatives. Passing them therefore did not cover the actual typed producer→Mining projection→relation connection.',
        'integrity': {'frozen_source_code_bindings_before_after_current_exact': 4135, 'observation_sha256': result['observations_sha256'],
            'sealed_execution_files_current_exact': len(seal), 'total_files_including_seal': len(seal) + 1, 'forbidden_call_counters': observation['forbidden_calls']},
        'unknown_and_limits': ['No native helper or probe was rerun; only persisted artifacts, source literals, stdlib arithmetic and streaming hashes were inspected.',
            'Real0671 produced no facts, so it did not itself produce the wrong pair. R1 is explicitly synthetic dual-key isolation, not a rewritten real document.',
            'Full context remains partial; material not selected/projected is unknown. ID order is observed, but no new source-selection policy is adopted.',
            'Cross-document last-write behavior remains a static concern, not exercised by these seven controls.',
            'No repair, new comparison policy, actual model behavior, Signal execution, full Mining, admission, future reuse or research benefit is established.'],
        'bindings': bindings}
    sha(Path(__file__))
    output = OWN / 'actual-review.json'
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'sha256': sha(output), 'verified_current_bindings': len(current)}))
