"""Fixed v3 seven answered wires plus eighth input only; read-only, no actors."""
from pathlib import Path
import hashlib,json,re
from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.research.stage_contracts import json_bytes
from stock_opportunity_agent.research.mining_controller import strip_document_artifacts
from stock_opportunity_agent.data.raw_info import RawInfoDocument
from stock_opportunity_agent.data.disclosure import raw_span_view
R=Path('/Users/l/Project/Recommandation');B=R/'runs/diagnostics/icfr_native_capability_20261023_v1/stage-v3';O=Path(__file__).resolve().parent
ids=['6d37fd3d13e6da8aabf61030a88ec08ab85b31e18a9f55d54c800b1027fc3b60','d4b9431fdd8f27b0ac11b4c19d5c330a5309330df54619c824739b2d943aadb0','32446a9aefc74777316a3f1cbcf058fc0f586730e3fb0bc6c9597f6d8c00f5f5','0b7d07f3208432da825fff0a8b4d153e674353110d0cd1ab937855c95ddb0cba','fa1029c16c0407a965d3262400b8270e539d47dcb7aaa705fdaa4803afeac727','3925a5cc09bd6c17dba125fdd143404440aff73efdb710a60cb3dd2681c7e0e5','1798558f904fa0e56dbb2ab7bd0b01c3e03b05a54d74c58aa2712cdf7d35762a','96b5bb86fe99e160211de37912921eeea8f7edfc6f7036448d4848f1b030aeb3']
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
manifest=json.loads((B/'manifest.json').read_text());sources=[x for x in manifest['source_bindings'] if x.get('document_id','').endswith(('000149315225011966','000114036125018373'))];assert len(sources)==2
paths=[B/'manifest.json',*[Path(s['path']) for s in sources]]
for i,h in enumerate(ids):
 paths.extend([B/'exchange/inbox'/f'{h}.json',B/'transport/requests'/f'{h}.json',B/'request-scopes'/f'{h}.json'])
 if i<7:paths.extend([B/'exchange/outbox'/f'{h}.txt',B/'exchange/receipts'/f'{h}.json'])
paths.extend(Path(row['path']) for row in manifest['code']);before={str(p):sha(p) for p in paths}
assert before[str(B/'exchange/inbox'/f'{ids[7]}.json')]=='8a24db2236093ea73eb74f72f6c4660e5ce94ac542b80f970466000b38f58bf9'
code=[{'path':x['path'],'manifest_sha256':x['sha256'],'actual_sha256':before[x['path']]} for x in manifest['code']];assert all(x['manifest_sha256']==x['actual_sha256'] for x in code)
views=[];requests=[];answers=[]
for i,h in enumerate(ids,1):
 wire=json.loads((B/'exchange/inbox'/f'{h}.json').read_text());transport=json.loads((B/'transport/requests'/f'{h}.json').read_text());scope=json.loads((B/'request-scopes'/f'{h}.json').read_text());native=transport['request'];assert canonical_json_hash(native)==h
 assert wire['messages']==native['messages'] and wire['max_output_tokens']==native['max_output_tokens'];v=json.loads(next(x['content'] for x in wire['messages'] if x['role']=='user'));views.append(v)
 cost=json_bytes(wire['messages'])+wire['max_output_tokens'];assert cost==int(v['request_budget']['this_request'])==scope['reservation'];assert scope['request']['sha256']==before[str(B/'transport/requests'/f'{h}.json')]
 row={'h':i,'request_hash':h,'native_complete_messages_plus_output':cost,'estimator_this_request':int(v['request_budget']['this_request']),'scope_reservation':scope['reservation'],'request_budget':v['request_budget'],'tool_budget':v['budget'],'answered_in_fixed_set':i<=7,'known_facts':len(v['known_fact_refs']),'known_relations':len(v['known_relation_refs']),'narrative_units':len(v.get('narrative_read_evidence',{}).get('items',[]))}
 if i<=7:
  receipt=json.loads((B/'exchange/receipts'/f'{h}.json').read_text());raw=(B/'exchange/outbox'/f'{h}.txt').read_bytes();assert receipt['agent_id']==f'/root/icfr_v3_h{i:03d}';assert receipt['inbox_sha256']==before[str(B/'exchange/inbox'/f'{h}.json')] and receipt['raw_output_sha256']==hashlib.sha256(raw).hexdigest();a=json.loads(raw);answers.append(a);row.update(answer=a,receipt=receipt)
 requests.append(row)
def cards(v):
 out={x['signal_ref']:x for x in v['signal_catalog']}
 for row in v.get('catalog_observations',{}).get('items',[]):
  if row['scope']=='signals':out.update({x['signal_ref']:x for x in row['result']['items']})
 return out
complete=cards(views[2]);assert len(complete)==18 and all('capability_contract' in x and 'source_hash' in x for x in complete.values());card_evidence=[]
for i,v in enumerate(views,1):
 c=cards(v);card_evidence.append({'h':i,'count':len(c),'complete_18_equal_h003':c==complete,'card_hashes':{ref:canonical_json_hash(card) for ref,card in c.items()}})
 if i>=3:assert c==complete
for a,cur in zip(answers[:2],[7,14]):assert a['action']=='inspect_catalog' and a['scope']=='signals' and a['cursor']==cur
assert answers[2]['action']=='fetch_evidence' and answers[2]['max_documents']==32 and answers[2]['query'] is None
assert answers[3]['action']=='inspect_catalog' and answers[3]['scope']=='evidence' and answers[3]['cursor']==0
assert all(x['action']=='read_span' and 'document_ref' in x for x in answers[4:7])
assert [x['offset'] for x in answers[4:7]]==[1148801,1152908,3969625]
original=next(x for x in views[4]['catalog_observations']['items'] if x['scope']=='evidence');assert original['result']['next_cursor']==2
norm=lambda x:re.sub(r'\[ANON_ID_\d+\]','[ANON_ID]',json.dumps(x,ensure_ascii=False,sort_keys=True))
directory=[]
for i in range(4,8):
 row=next(x for x in views[i]['catalog_observations']['items'] if x['scope']=='evidence');assert row['source_snapshot_matches'] and norm(row['result'])==norm(original['result']);assert row['response_hash']==original['response_hash']
 assert all('sections' in x and not x.get('read_windows') for x in row['result']['items'])
 directory.append({'h':i+1,'observation_ref':row['observation_ref'],'response_hash':row['response_hash'],'source_snapshot_hash':row['source_snapshot_hash'],'source_snapshot_matches':row['source_snapshot_matches'],'counts':row['result']['counts'],'next_cursor':row['result']['next_cursor'],'whole_result_hash_normalized_wire_ids':hashlib.sha256(norm(row['result']).encode()).hexdigest()})
assert views[6]['budget']['light_remaining']==views[7]['budget']['light_remaining']==1
source_by_hash={s['content_hash']:s for s in sources};units=[]
for row in views[7]['narrative_read_evidence']['items']:
 source=source_by_hash[row['content_hash']];assert before[source['path']]==source['sha256'];doc=json.loads(Path(source['path']).read_text());assert hashlib.sha256(doc['content'].encode()).hexdigest()==row['content_hash'];raw=doc['content'][row['offset']:row['offset']+row['length']]
 assert row['verbatim_hash']==hashlib.sha256(raw.encode()).hexdigest();assert row['readable_text']==strip_document_artifacts(raw_span_view(RawInfoDocument.from_dict(doc),row['offset'],row['length'])['readable_text'])
 assert row['case_refs']==[source['case_ref']];assert row['read_targets']==[{'target':'document_ref','ref':row['document_ref'],'case_refs':[source['case_ref']]}]
 assert row['available_at']==source['available_at'] and row['published_at']==doc['published_at'] and row['source_type']==source['source_type'];assert row['available_at']<=source['cutoff'];assert row['length']==4000
 source_card=next(x for x in original['result']['items'] if x['document_ref'].split(':')[-1] in source['document_id']);assert source_card['available_at']==source['available_at'] and source_card['case_bindings'][0]['case_ref']==source['case_ref'];assert row['offset'] in [1148801,1152908,3969625]
 units.append({**row,'readable_sha256':hashlib.sha256(row['readable_text'].encode()).hexdigest(),'source_path':source['path'],'source_file_sha256':source['sha256'],'source_document_id':source['document_id']})
assert len(units)==3 and [r['narrative_units'] for r in requests[5:]]==[1,2,3]
assert answers[6]['offset']==3969625 and any(s['raw_start']==3969625 for x in original['result']['items'] if '000114036125018373' in x['document_ref'] for s in x['sections'])
answered=sum(r['native_complete_messages_plus_output'] for r in requests[:7]);assert int(views[7]['request_budget']['used'])==answered
for i in range(1,8):assert int(views[i]['request_budget']['used'])==sum(r['native_complete_messages_plus_output'] for r in requests[:i])
after={str(p):sha(p) for p in paths};assert before==after
out={'scope':'exact h001-h007 inbox/raw answer/receipt; h008 inbox, transport request and request scope ONLY; no h008 answer or receipt read','requests':requests,'answered_complete_cost':answered,'h008_input_only_reservation':requests[7]['native_complete_messages_plus_output'],'source_binding_count':len(manifest['source_bindings']),'source_bindings_used':sources,'complete_card_retention':card_evidence,'evidence_directory_retention':directory,'original_directory':original,'actual_read_units_h008':units,'h007_answer':answers[6],'source_selection_difference':{'v3':{'facts':2879,'relations':1342,'fetch_max_documents':32,'query':None},'v2_prior_fixed_evidence':{'facts':2088,'relations':952,'query':'targeted ICFR'},'causal_efficiency_or_total_cost_claim':False}}
(O/'evidence.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');(O/'bindings.json').write_text(json.dumps({'fixed_artifacts_stable_before_after':True,'files':before,'native_code_manifest_match':True,'code_manifest_verification':code,'scope':'only fixed artifact set; changing stage progress/future actors excluded','network_or_api_calls':0},ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'answered_cost':answered,'h008_reserved':requests[7]['native_complete_messages_plus_output'],'all_costs':[r['native_complete_messages_plus_output'] for r in requests],'cards_h003_to_h008':18,'page_next_cursor':2,'h008_body_units':len(units),'h008_light':views[7]['budget']['light_remaining'],'code_files':len(code),'fixed_files':len(before),'stable':before==after}))
