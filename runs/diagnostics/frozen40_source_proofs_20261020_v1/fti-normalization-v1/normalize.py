"""One authorized local native normalization of actual FTI daily response."""
from datetime import date, datetime, timezone
import json
from pathlib import Path
import ssl
import http.client
import diagnose_reviewed_frozen_source_snapshot as driver
from stock_opportunity_agent.data.acquisition import HistoricalPriceAdapter
from stock_opportunity_agent.data.resolution import RawInfoRequest
from stock_opportunity_agent.data.sources.massive import _price_bar_from_result
from stock_opportunity_agent.data.reviewed_snapshot import _daily_market_rows
from stock_opportunity_agent.artifacts import canonical_json_hash
from collect_frozen40_supplemental_source_proofs import shared

root = Path(__file__).resolve().parent
assert not (root / 'normalization-start.json').exists()
shared.write(root / 'normalization-start.json', {'started_at_utc': datetime.now(timezone.utc).isoformat()}, initial=True)
proofroot = root.parent
plan_binding, plan = driver._bound_json(proofroot / 'final-plan-v2/request-plan.json')
result_binding, result = driver._bound_json(proofroot / 'final-plan-v2/collection/results.json')
assert result['terminal'] is True and result['status'] == 'completed' and result['plan_hash'] == plan['plan_hash']
disposition = next(row for row in result['dispositions'] if row['name'] == 'proof-092')
assert disposition['status'] == 'received'
cache_binding = disposition['native_cache']; cache = driver._read_bound(cache_binding)[1]
case_binding, case_authority = driver._bound_json(proofroot / 'fti-market-window-local-check.json')
case = case_authority['case']; cutoff = datetime.fromisoformat(case['prediction_time'])
assert case['company_id'] == 'cik_0001681459' and cutoff == datetime(2025,5,30,tzinfo=timezone.utc)
with driver._prepare_only():
    rows, days = _daily_market_rows(cache['body'], 'FTI', True, date(2024,4,25), date(2025,5,29))
    normalized = datetime.now(timezone.utc)
    assert normalized >= datetime.fromisoformat(cache['retrieved_at'])
    bars = [_price_bar_from_result('FTI', row, normalized, adjusted=True) for row in rows]
    acquired = HistoricalPriceAdapter('massive', lambda *_args: bars).acquire(
        RawInfoRequest('fti_actual_daily_origin', 'Normalize actual retained FTI daily input.',
            ('market_data',), lookback_days=400, max_documents=1),
        company_id=case['company_id'], identity={'ticker':'FTI'}, as_of=cutoff)
    assert len(acquired.documents) == 1
    document = acquired.documents[0]
    shared.write(root / 'candidate.json', document.to_dict())
    document_binding = driver.frozen._stream_binding(root / 'candidate.json')
    details, requests = driver._market_origin(case, {'endpoint':cache['endpoint']}, {'binding':cache_binding},
        {'original_record':document_binding})
    origin = {'case':case,'original_record':document_binding,'cache':cache_binding}
    shared.write(root / 'origin.json', origin)
    normalization = {'normalized_at':normalized.isoformat(),'provider_retrieved_at':cache['retrieved_at'],
        'request':{'lookback_days':400,'source_type':'market_data','as_of':cutoff.isoformat()},
        'actual_rows':len(rows),'latest_bar':days[-1].isoformat(),'first_bar':days[0].isoformat(),
        'candidate':document_binding,'canonical_record_hash':canonical_json_hash(document.to_dict()),
        'document_id':document.document_id,'available_at':document.available_at.isoformat(),
        'actual_reconstruction':details,'derived_requests':requests,
        'source_bindings':[plan_binding,result_binding,cache_binding,case_binding],
        'code_binding':driver.frozen._stream_binding(__file__),'global_appends':0,'new_GETs':0,
        'labels_loaded':False,'Signal_apply':False,'source_admitted':False}
    shared.write(root / 'normalization.json', normalization)
    driver._check(normalization['source_bindings'])
print(json.dumps({'candidate':document_binding,'normalization':driver.frozen._stream_binding(root / 'normalization.json'),
    'rows':len(rows),'latest_bar':days[-1].isoformat(),'normalized_at':normalized.isoformat(),
    'provider_retrieved_at':cache['retrieved_at'],'available_at':document.available_at.isoformat()}))
