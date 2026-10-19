#!/usr/bin/env python3
"""Reconsume frozen local inputs at equivalent instants and preserve visibility."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import socket
from types import SimpleNamespace

from diagnose_reviewed_source_snapshot import _binding, restore_inputs
from stock_opportunity_agent.artifacts import atomic_write_json, canonical_json_hash
from stock_opportunity_agent.data.acquisition import HistoricalPriceAdapter
from stock_opportunity_agent.data.resolution import BasicInfoBundle, EvidenceResolver, RawInfoRequest
from stock_opportunity_agent.data.sources.massive import _price_bar_from_result
from stock_opportunity_agent.research.compute_tools import compute_metric
from stock_opportunity_agent.research.evolution_core import (
    ResearchState, RuntimeStopReason, default_information_plan, project_basic_info_bundle,
    _assemble_final_context, _prediction_baseline_from_market_documents,
)
from stock_opportunity_agent.research.evolution_output_validation import _compact_posthoc_context
from stock_opportunity_agent.research.evolution_plan_roles import _plan_critic_trajectory

REPO = Path(__file__).resolve().parents[1]
OLD = REPO / 'runs/diagnostics/reviewed_market_snapshot_20261019_v2'
OLD_DAY = REPO / 'runs/diagnostics/market_baseline_timezone_boundary_20261019_v1'
OLD_VISIBILITY = REPO / 'runs/diagnostics/basic_info_visibility_boundary_20261019_v1'


def diagnose(output: Path):
    """Save new deterministic evidence without changing original runs or dispatching."""
    if output.exists():
        raise ValueError('new diagnostic directory required')
    inputs = json.loads((OLD/'input_manifest.json').read_bytes())
    store = restore_inputs(OLD/'input_manifest.json', canonical_json_hash(inputs))
    market = next(doc for doc in store.documents if doc.source_type == 'market_data')
    chain = json.loads((OLD_DAY/'consumer-chain.json').read_bytes())
    cache_path = Path(chain['raw_cache']['path'])
    source_paths = [OLD/'input_manifest.json', OLD/'basic_info.json', OLD/'result.json', cache_path,
                    *(OLD_DAY/name for name in ('result.json','consumer-chain.json')),
                    *(OLD_VISIBILITY/name for name in ('result.json','final_context.json')),
                    *(Path(row['path']) for row in json.loads((OLD/'result.json').read_bytes())['original_bindings'])]
    source_bindings = [_binding(path) for path in source_paths]
    cache = json.loads(cache_path.read_bytes())
    clock = datetime.fromisoformat(json.loads(market.content)[0]['retrieved_at'])
    bars = tuple(_price_bar_from_result(market.metadata['symbol'], row, clock, adjusted=True)
                 for row in cache['body']['results'])
    cutoff = datetime.fromisoformat(inputs['scope']['as_of'])
    request = RawInfoRequest('recent_market_backbone', 'Recent daily observations', ('market_data',), lookback_days=45)
    outputs = []
    for instant in (cutoff, cutoff.astimezone(timezone(timedelta(hours=-4))), cutoff.astimezone(timezone(timedelta(hours=14)))):
        calls = []
        def cached_fetch(symbol, start, end):
            calls.append({'symbol':symbol,'start':start.isoformat(),'end':end.isoformat()})
            return [bar for bar in bars if start <= bar.as_of_date <= end]
        acquired = HistoricalPriceAdapter('massive', cached_fetch).acquire(request, company_id=market.company_id,
            identity={'ticker':market.metadata['symbol']}, as_of=instant)
        resolver = EvidenceResolver(store.snapshot())
        bundle = resolver.resolve_basic_info((request,), company_id=market.company_id, identity={}, as_of=instant)
        model, _ = project_basic_info_bundle(bundle)
        metric = compute_metric('price_shape', {'window_days':30}, documents=(market,), as_of=instant)
        outputs.append({'prediction_time':instant.isoformat(), 'cached_fetch_requests':calls,
            'acquired_whole_document':acquired.documents[0].to_dict(), 'model_context':model,
            'metric':metric, 'baseline':_prediction_baseline_from_market_documents((market,),instant)})
    comparable = [{key:row[key] for key in ('cached_fetch_requests','acquired_whole_document','model_context','baseline')}
                  | {'metric':{key:row['metric'][key] for key in ('values','labels','literal_refs')}} for row in outputs]
    saved = json.loads((OLD/'basic_info.json').read_bytes())
    model, lineage = project_basic_info_bundle(BasicInfoBundle.from_dict(saved['bundle']))
    # Fact-free legal state is only an assembler setup; no fresh research answer.
    state = ResearchState(next_information_needs=('What operating evidence remained unavailable?',))
    final = _assemble_final_context(plan=default_information_plan(), company_id=market.company_id,
        additional_identity_aliases=(market.metadata['symbol'],), basic_info=model,
        state=state, rounds=(), prediction_time=cutoff, market_documents=(market,))
    item = SimpleNamespace(prediction_time=cutoff, signal_rounds=(), state_deltas=(),
        stop_reason=RuntimeStopReason.NO_SIGNAL_MATCH, termination_trigger=None,
        to_dict=lambda:{'basic_info_bundle':saved['bundle'],'final_context':final,'signal_rounds':[]})
    contexts = {'final':final, 'posthoc_final':_compact_posthoc_context(final),
        'posthoc_direct':_compact_posthoc_context({'prediction_time':cutoff.isoformat(),'basic_info':model}),
        'critic':_plan_critic_trajectory(item,case_index=0)}
    indexes = [final['basic_info']['source_index'], *(contexts[name]['basic_info_source_index']
               for name in ('posthoc_final','posthoc_direct','critic'))]
    expected = next(row for row in model['requests'] if row['request']['request_id']==request.request_id)
    fields = ('source_context_truncated','projection_context_truncated','effective_context_truncated',
              'omitted_context_markers','projection_status','available_projection_count',
              'visible_projection_count','omitted_projection_count')
    visibility_equal = all(all(row[field]==expected[field] for field in fields)
        for index in indexes for row in index if row['request_id']==request.request_id)
    code_paths = [*sorted((REPO/'src').rglob('*.py')), Path(__file__),
                  REPO/'scripts/diagnose_reviewed_source_snapshot.py',
                  REPO/'tests/test_daily_visibility_boundary.py']
    result = {'schema_version':'daily-visibility-boundary-diagnostic-v1',
        'source_bindings':source_bindings,'code_bindings':[_binding(path) for path in code_paths],
        'equivalent_instants_equal':all(row==comparable[0] for row in comparable[1:]),
        'visibility_equal_across_four_consumer_views':visibility_equal,
        'critic_view_layer':'trajectory helper; actual caller pending wire is a separate independent check',
        'actual_caller_wire_captured_by_this_diagnostic':False,
        'actual_market_visibility':{field:expected[field] for field in fields},
        'source_inputs_unchanged':source_bindings==[_binding(path) for path in source_paths],
        'new_model_responses':0,'external_llm_calls':0,'readonly_data_requests':0,
        'fresh_model_behavior_proven':False,'full_factory_preflight_proven':False,'engineering_mvp_closed':False,
        'scope':'Deterministic UTC daily windows and two-stage visibility; no new prediction or completed case.'}
    atomic_write_json(output/'daily_outputs.json',outputs)
    atomic_write_json(output/'model_basic_info.json',{'model_context':model,'lineage':lineage})
    atomic_write_json(output/'consumer_contexts.json',contexts)
    atomic_write_json(output/'result.json',result)
    return result


def main():
    """Run one new bounded offline consumer diagnostic."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    def forbidden(*_args, **_kwargs):
        raise AssertionError('network forbidden')
    socket.socket = forbidden
    result = diagnose(args.output.resolve())
    print(json.dumps({key:value for key,value in result.items() if key not in ('code_bindings','source_bindings')}, indent=2))


if __name__ == '__main__':
    main()
