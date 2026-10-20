"""Freeze and inspect new native inputs without reentering the source stage."""
from contextlib import ExitStack
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import sys
from time import monotonic
from unittest.mock import patch

import diagnose_reviewed_frozen_case_inputs as frozen
import diagnose_reviewed_frozen_source_snapshot as source
import run_minimal_rounds
from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.cases.label_store import LabelStore
from stock_opportunity_agent.data.raw_info import RawInfoStore
from stock_opportunity_agent.data.resolution import EvidenceResolver, source_types_compatible
from stock_opportunity_agent.data.reviewed_snapshot import ReviewedRawInfoStore, open_raw_info_store
from stock_opportunity_agent.research.evolution_transport import StructuredRoleClient
from stock_opportunity_agent.signal_library import SignalExecutor, _CASH_TAGS, _sec_facts


ROOT = Path('/Users/l/Project/Recommandation')
OUT = Path(__file__).resolve().parent
EXPECTED_OUT = ROOT / 'runs/diagnostics/measurement_input_selection_20261021_v1'
OLD = ROOT / 'runs/diagnostics/reviewed_gpre_capture_snapshot_20261021_v1/stage'
RESULT_SHA = '2c6e706bad8a63742f3f50b812d6e9aca6a4a27b7d557734ce2609c2e6580cfb'
Q1 = 'rawcap:v1:64c9e4f193885e37ae497a75841bec6dec372f9fddf1ef7649710c28c40fc902'


def read(path):
    return json.loads(Path(path).read_bytes())


def write_new(name, value):
    with (OUT / name).open('x') as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write('\n')


def bind(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def check(bindings):
    for row in bindings:
        if bind(row['path']) != row:
            raise RuntimeError('Frozen diagnostic input/code drift: ' + row['path'])


def freeze():
    if OUT != EXPECTED_OUT or any((OUT / name).exists() for name in ('plan.json', 'started.json', 'result.json', 'failure.json', 'default_v6.json', 'latest_v12.json')):
        raise RuntimeError('Fresh fixed diagnostic destination required before any Registry construction')
    if bind(OLD / 'result.json')['sha256'] != RESULT_SHA:
        raise RuntimeError('Completed source authority differs')
    old_result, old_plan = read(OLD / 'result.json'), read(OLD / 'plan.json')
    assert old_result['status'] == 'completed'
    assert old_plan['plan_hash'] == old_result['plan_hash']
    assert canonical_json_hash({k: v for k, v in old_plan.items() if k != 'plan_hash'}) == old_plan['plan_hash']
    assert bind(OLD / 'source-review.json') == old_result['source_review']
    review = read(OLD / 'source-review.json')
    paths = [Path(__file__), OLD / 'plan.json', OLD / 'result.json', OLD / 'source-review.json',
             OLD / 'default_v6.json', OLD / 'latest_v12.json',
             ROOT / 'scripts/diagnose_reviewed_frozen_case_inputs.py',
             ROOT / 'scripts/diagnose_reviewed_frozen_source_snapshot.py',
             ROOT / 'spec/src/stock_opportunity_agent/signal_library.md',
             ROOT / 'spec/src/stock_opportunity_agent/data/resolution.md']
    paths += list((ROOT / 'src').rglob('*.py'))
    paths += list((ROOT / 'scripts').rglob('*.py'))
    paths += [p for p in Path(old_result['reviewed_source_snapshot']['root']).rglob('*') if p.is_file()]
    bindings = [bind(p) for p in paths]
    bindings += source._find_bindings(review)
    for group in old_plan['groups']:
        _, rows = frozen._snapshot(group, OUT)
        bindings += rows
    bindings = source._bindings(bindings)
    check(bindings)
    plan = {'output_root': str(OUT), 'case': old_plan['case'], 'identity': old_plan['identity'], 'groups': old_plan['groups'],
            'reviewed_source_snapshot': old_result['reviewed_source_snapshot'], 'bindings': bindings,
            'expected': {'groups': 2, 'refs_per_group': 18, 'resolved_per_group': 17,
                         'financial_source_requests_per_group': 9,
                         'deterministic_financial': {'default_v6': 6, 'latest_v12': 9},
                         'typed_q1_financial_sources': {'default_v6': 8, 'latest_v12': 9},
                         'latest_selected_cash_period': '2025-03-31', 'max_documents': 10},
            'limits': 'Input preparation only. No Signal execution, model, label, acquisition, append, fullprepare or old-stage reentry.'}
    plan['plan_hash'] = canonical_json_hash(plan)
    write_new('plan.json', plan)
    print(json.dumps({'plan_hash': plan['plan_hash'], 'bindings': len(bindings)}))


def run(expected_hash):
    if OUT != EXPECTED_OUT or any((OUT / name).exists() for name in ('started.json', 'result.json', 'failure.json', 'default_v6.json', 'latest_v12.json')):
        raise RuntimeError('Fixed unstarted diagnostic required; completed or attempted run cannot reenter')
    plan = read(OUT / 'plan.json')
    if plan['output_root'] != str(OUT) or plan['plan_hash'] != expected_hash or canonical_json_hash({k: v for k, v in plan.items() if k != 'plan_hash'}) != expected_hash:
        raise RuntimeError('Exact frozen plan required')
    check(plan['bindings'])
    started = monotonic()
    write_new('started.json', {'plan_hash': expected_hash, 'pid': os.getpid()})
    forbidden_calls = []
    def forbidden(*args, **kwargs):
        forbidden_calls.append('forbidden_operation')
        raise RuntimeError('Input-only diagnostic boundary')
    try:
        with ExitStack() as guards:
            for obj, attr in [(RawInfoStore, 'append'), (ReviewedRawInfoStore, 'append'),
                              (SignalExecutor, 'execute_batch'), (LabelStore, '__init__'),
                              *[(LabelStore, name) for name in ('load', 'record', 'ground_truth', 'keys', 'label_contract')],
                              (run_minimal_rounds, 'prepare'),
                              *[(StructuredRoleClient, name) for name in ('complete_json',
                                'complete_json_with_token_scores', 'complete_binary_token_with_scores')]]:
                guards.enter_context(patch.object(obj, attr, forbidden))
            guards.enter_context(patch('socket.socket', forbidden))
            store = open_raw_info_store(plan['reviewed_source_snapshot']['root'],
                                        reviewed_snapshot=plan['reviewed_source_snapshot'])
            assert len(store.documents) == 1780
            before = canonical_json_hash([d.to_dict() for d in store.documents])
            cutoff = datetime.fromisoformat(plan['case']['prediction_time'])
            result = {}
            for group in plan['groups']:
                registry = frozen._snapshot(group, OUT)[0]
                executor = SignalExecutor(registry, store, resolver=EvidenceResolver(store))
                resolutions = executor.prepare_inputs(tuple(group['refs']), company_id=plan['case']['company_id'],
                                                      as_of=cutoff, identity=plan['identity'])
                rows = []
                for ref, resolution in zip(group['refs'], resolutions, strict=True):
                    spec = registry.load_spec(ref)
                    selected = tuple(store.load(r.document_id, as_of=cutoff) for r in resolution.documents)
                    facts = _sec_facts(selected, cutoff) if spec.function and spec.function.startswith('financial.') else ()
                    selected_ids = [d.document_id for d in selected]
                    old = next(row['resolution'] for row in read(OLD / (group['name'] + '.json'))['resolutions'] if row['signal_ref'] == ref)
                    rows.append({'signal_ref': ref, 'function': spec.function, 'resolution': resolution.to_dict(),
                                 'financial_source_request': source_types_compatible(('sec_company_facts',), spec.source_types),
                                 'typed_q1_selected': Q1 in selected_ids,
                                 'latest_native_fact_period': max((f.end for f in facts), default=None),
                                 'selected_set_changed': set(selected_ids) != {d['document_id'] for d in old['documents']},
                                 'latest_cash_period': max((f.end for f in facts if f.tag in _CASH_TAGS and f.start is None), default=None)})
                    if not spec.function or not spec.function.startswith('financial.'):
                        assert selected_ids == [d['document_id'] for d in old['documents']]
                financial = [r for r in rows if r['function'] and r['function'].startswith('financial.')]
                financial_sources = [r for r in rows if r['financial_source_request']]
                summary = {'resolved': sum(r.status == 'resolved' for r in resolutions), 'refs': len(rows),
                           'deterministic_financial': len(financial),
                           'deterministic_typed_q1_selected': sum(r['typed_q1_selected'] for r in financial),
                           'financial_source_requests': len(financial_sources),
                           'financial_source_typed_q1_selected': sum(r['typed_q1_selected'] for r in financial_sources),
                           'changed_sets': sum(r['selected_set_changed'] for r in rows)}
                write_new(group['name'] + '.json', {'summary': summary, 'rows': rows})
                assert summary['refs'] == 18 and summary['resolved'] == 17
                expected = plan['expected']
                assert summary['financial_source_requests'] == 9
                assert summary['deterministic_financial'] == summary['deterministic_typed_q1_selected'] == expected['deterministic_financial'][group['name']]
                assert summary['financial_source_typed_q1_selected'] == expected['typed_q1_financial_sources'][group['name']]
                assert all(len(r['resolution']['documents']) <= 10 for r in rows)
                assert next(r['latest_cash_period'] for r in rows if r['function'] == 'financial.cash_reserves') == '2025-03-31'
                result[group['name']] = summary
            assert before == canonical_json_hash([d.to_dict() for d in store.documents])
            assert not forbidden_calls
        check(plan['bindings'])
        write_new('result.json', {'status': 'completed', 'plan_hash': expected_hash, 'groups': result,
                                'reviewed_view_records_unchanged': True, 'bindings_unchanged': True,
                                'elapsed_seconds': monotonic() - started,
                                'forbidden_calls': forbidden_calls, 'limits': plan['limits']})
        print(json.dumps(result))
    except BaseException as exc:
        write_new('failure.json', {'type': type(exc).__name__, 'message': str(exc), 'forbidden_calls': forbidden_calls})
        raise


if __name__ == '__main__':
    if sys.argv[1:] == ['freeze']:
        freeze()
    elif len(sys.argv) == 3 and sys.argv[1] == 'run':
        run(sys.argv[2])
    else:
        raise SystemExit('Use freeze or run EXACT_PLAN_HASH')
