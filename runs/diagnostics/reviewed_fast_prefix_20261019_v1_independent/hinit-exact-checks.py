import json,hashlib
from pathlib import Path
from datetime import datetime
from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.research.evolution_core import _normalized_projection_text
repo=Path('/Users/l/Project/Recommandation');r=repo/'runs/diagnostics/reviewed_fast_prefix_20261019_v1';h='89a34b9d9ffe11a5c749e25787ddb84af249d4a66bf35d1dff0886ea4f92ee45'
paths={name:r/name for name in ['expectations.json','inputs.json','contract.json','preflight.json','manifest.json','observations/initialize_00.json',f'requests/{h}.json',f'exchange/inbox/{h}.json',f'exchange/outbox/{h}.txt',f'exchange/receipts/{h}.json',f'cache/responses/{h}.json']}
d={name:json.loads(p.read_text()) for name,p in paths.items() if p.suffix=='.json'};raw=json.loads(paths[f'exchange/outbox/{h}.txt'].read_text());accepted=d['observations/initialize_00.json']['value'];preflight=d['preflight.json'];contract=d['contract.json'];inputs=d['inputs.json'];wire=d[f'requests/{h}.json']['request'];inbox=d[f'exchange/inbox/{h}.json'];receipt=d[f'exchange/receipts/{h}.json'];cache=d[f'cache/responses/{h}.json'];payload=json.loads(wire['messages'][-1]['content'])
assert canonical_json_hash(wire)==h and wire['messages']==inbox['messages']
assert receipt['request_hash']==h and receipt['inbox_sha256']==hashlib.sha256(paths[f'exchange/inbox/{h}.json'].read_bytes()).hexdigest() and receipt['raw_output_sha256']==hashlib.sha256(paths[f'exchange/outbox/{h}.txt'].read_bytes()).hexdigest()
assert cache['json_output']==raw and cache['raw_output']==paths[f'exchange/outbox/{h}.txt'].read_text()
for field in raw:
 if field!='supporting_evidence':assert raw[field]==accepted[field]
assert len(raw['supporting_evidence'])==len(accepted['supporting_evidence'])==5
assert canonical_json_hash(inputs)==contract['input_hash'] and canonical_json_hash(d['expectations.json'])==contract['expectations_hash'] and canonical_json_hash(preflight)==contract['preflight_hash']
assert d['observations/initialize_00.json']['request_hashes']==[h]
assert all(alias not in json.dumps(wire['messages']) for alias in ('BMBL','Bumble','cik_0001830043'))
assert 'expectations' not in payload and 'oracle' not in json.dumps(payload).lower() and 'ground_truth' not in json.dumps(payload)
entries={e['projection_id']:e for e in preflight['lineage']['entries']};visible={q['projection_id']:q for req in payload['basic_info']['requests'] for q in req['projections']}
canonical=repo/'runs/cold_start/data/global-raw-info-oracle-v1/filing/cik_0001830043/sec:cik_0001830043:000162828025038861.json';doc=json.loads(canonical.read_text());content=doc['content'];assert hashlib.sha256(content.encode()).hexdigest()==doc['content_hash']
normalized=_normalized_projection_text(content)[0];checks=[]
for initial,claim in zip(raw['supporting_evidence'],accepted['supporting_evidence'],strict=True):
 pid=claim['projection_id'];e=entries[pid];quote=claim['exact_text'];sent=initial['exact_text'];assert sent in visible[pid]['exact_text'] and quote in e['projection_text'] and quote in normalized
 assert claim['claim']==initial['claim'] and e['document_id']==doc['document_id'] and e['content_hash']==doc['content_hash']
 a=e['projection_text'].index(quote);b=a+len(quote);runs=[run for run in e['raw_offset_runs'] if run[0]<b and run[1]>a];raw_start=min(run[2] for run in runs);raw_end=max(run[3] for run in runs)
 assert 0<=raw_start<raw_end<=len(content)
 checks.append({'projection_id':pid,'claim':claim['claim'],'quote_sha256':hashlib.sha256(quote.encode()).hexdigest(),'quote_present_in_actual_wire':True,'quote_present_in_frozen_lineage_and_normalized_canonical':True,'canonical_raw_bounding_start':raw_start,'canonical_raw_bounding_end':raw_end,'available_at':visible[pid]['available_at']})
assert all(datetime.fromisoformat(q['available_at'])<=datetime.fromisoformat(inputs['sample']['prediction_time']) for q in visible.values())
assert payload['evaluation_anchor']['mean_adjusted_close']==6.494 and payload['evaluation_anchor']['doubling_threshold']==12.988 and payload['evaluation_anchor']['recent_close']==6.3
allvisible='\n'.join(q['exact_text'] for q in visible.values());assert 'Net cash provided by operating activities' not in allvisible
out={'scope':'Only actual accepted H_init role36; no routing answer accessed or production resume executed.','request_hash':h,'receipt_agent':receipt['agent_id'],'raw_and_cache_and_wire_bound':True,'non_evidence_state_fields_identical_to_raw':True,'facts_and_source_quote_checks':checks,'canonical_source':{'path':str(canonical.relative_to(repo)),'document_id':doc['document_id'],'file_sha256':hashlib.sha256(canonical.read_bytes()).hexdigest(),'content_hash':doc['content_hash'],'available_at':doc['available_at']},'actual_visibility':[{**{k:v for k,v in row.items() if k in ('available_projection_count','visible_projection_count','omitted_projection_count','source_context_truncated','projection_context_truncated','effective_context_truncated','projection_status')},'request_id':row['request']['request_id']} for row in payload['basic_info']['requests']],'PIT_all_visible_cards_at_or_before_cutoff':True,'anonymous_request':True,'oracle_or_label_content_not_in_request':True,'runtime_anchor_unaltered':True,'bindings':{name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in paths.items()},'expectations_canonical_hash':contract['expectations_hash']}
Path('/tmp/formal-prefix-hinit-exact-checks.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k not in ('bindings','actual_visibility','facts_and_source_quote_checks')},indent=2));print('5 quote raw bounds',[(x['projection_id'],x['canonical_raw_bounding_start'],x['canonical_raw_bounding_end']) for x in checks])
