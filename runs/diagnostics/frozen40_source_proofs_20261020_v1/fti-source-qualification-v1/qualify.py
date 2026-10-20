"""Qualify the actual FTI source once locally, without admission or acquisition."""
from datetime import datetime, timezone
import json
from pathlib import Path
import ssl
import http.client
import diagnose_reviewed_frozen_source_snapshot as driver
from collect_frozen40_supplemental_source_proofs import shared
from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.data.raw_info import RawInfoDocument
from stock_opportunity_agent.data.reviewed_snapshot import _verify_market_document
import stock_opportunity_agent.data.reviewed_snapshot as native

output = Path(__file__).resolve().parent
root = output.parent
shared.write(output / 'qualification-start.json', {'started_at_utc':datetime.now(timezone.utc).isoformat()}, initial=True)
normal = shared.read_bound(shared.bound(root / 'fti-normalization-v1/normalization.json'))
origin = shared.read_bound(shared.bound(root / 'fti-normalization-v1/origin.json'))
document = RawInfoDocument.from_dict(shared.read_bound(origin['original_record']))
collection = root / 'supplemental-v1/collection'
receipt_binding = shared.bound(collection / 'results.json')
receipt = shared.read_bound(receipt_binding)
assert receipt['terminal'] is True and receipt['status'] == 'completed'
records_binding = shared.bound(collection / 'market-request-records.json')
records = shared.read_bound(records_binding)
by_name = {record['name']:record for record in records}
issuer_binding = shared.bound(collection / by_name['supplement-001']['raw_response'])
split_binding = shared.bound(collection / by_name['supplement-002']['raw_response'])
issuer = shared.read_bound(issuer_binding)['results']
expected_identity = {'ticker':'FTI','cik':'0001681459','market':'stocks','locale':'us',
    'primary_exchange':issuer.get('primary_exchange'),'type':'CS','currency_name':'usd'}
proofs = [
    {'kind':'massive_daily_origin','artifact':origin['cache'],
        'provider_retrieved_at':normal['provider_retrieved_at'],'normalization_retrieved_at':normal['normalized_at']},
    {'kind':'massive_historical_issuer','artifact':issuer_binding,'request_record':records_binding,
        'entry_name':'supplement-001','expected_identity':expected_identity},
    {'kind':'massive_no_post_cutoff_splits','artifact':split_binding,'request_record':records_binding,
        'entry_name':'supplement-002'}]
candidate = {'document':origin['original_record'], 'target_keys':['market|cik_0001681459:20250530|*'],
    'proof_profile':'massive_daily_no_post_cutoff_split_v1','proofs':proofs,
    'reason':'Actual complete native daily reconstruction with historical issuer and all-type split proof; no research effect claim.'}
old_inventories = [root / 'collection-terminal-bindings.json',root / 'supplemental-v1/terminal-file-bindings.json']
terminal_files = []
for path in old_inventories:
    terminal_files.extend(shared.read_bound(shared.bound(path))['files'])
shared.check(terminal_files)
reader_before = shared.bound(native.__file__)
status = 'unknown'; failure = None
with driver._prepare_only():
    try:
        _verify_market_document(document, {'reviewed_available_at':document.available_at.isoformat()},
            {p['kind']:(p,shared.read_bound(p['artifact'])) for p in proofs},
            datetime.fromisoformat(origin['case']['prediction_time']))
        driver._market_origin(origin['case'],{'endpoint':shared.read_bound(origin['cache'])['endpoint']},
            {'binding':origin['cache']},{'original_record':origin['original_record']})
    except Exception as error:
        failure = {'error_type':type(error).__name__,'message':str(error)}
        candidate['reason'] = 'Unknown: native market qualification rejected: ' + str(error)
    else:
        status = 'native_profile_passed_not_admitted'
shared.check(terminal_files)
assert shared.bound(native.__file__) == reader_before
raw_evidence = []
for receipt_path in [root / 'final-plan-v2/collection/results.json',collection / 'results.json']:
    saved = shared.read_bound(shared.bound(receipt_path))
    for entry in saved['requests']:
        if entry['name'] in ('proof-092','supplement-001','supplement-002'):
            binding = {'path':entry['raw_response'],'sha256':entry['raw_sha256']}
            shared.check([binding]); raw_evidence.append(binding)
evidence = [shared.bound(root/'fti-normalization-v1/normalization.json'),shared.bound(root/'fti-normalization-v1/origin.json'),
    shared.bound(root/'fti-normalization-v1/normalize.py'),origin['original_record'],origin['cache'],receipt_binding,
    records_binding,issuer_binding,split_binding,shared.bound(root/'final-plan-v2/collection/results.json'),
    *[shared.bound(path) for path in old_inventories],*raw_evidence,shared.bound(__file__)]
fragment = {'candidates':[candidate],'additional_market_products':[origin['original_record']],
    'qualification':{'status':status,'failure':failure,'actual_native_verifier':reader_before,
        'canonical_record_hash':canonical_json_hash(document.to_dict()),'rows':normal['actual_rows'],
        'latest_bar':normal['latest_bar'],'reviewed_available_at':document.available_at.isoformat(),
        'expected_identity':expected_identity},'evidence_bindings':evidence,
    'terminal_original_files_rehashed_unchanged':len(terminal_files),
    'new_GETs':0,'global_appends':0,'source_admissions':0,'models':0,'labels_loaded':False,
    'stage_prepare':False,'source_bundle_assembled':False}
shared.write(output / 'candidate-fragment.json',fragment,initial=True)
print(json.dumps({'status':status,'failure':failure,'fragment':shared.bound(output/'candidate-fragment.json'),
    'terminal_files_unchanged':len(terminal_files),'candidate':origin['original_record']}))
