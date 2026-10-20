"""Hash-only frozen source audit plus explicit input allowlist; no store/role/run."""
from datetime import datetime
from pathlib import Path
import hashlib,json,time
from stock_opportunity_agent.artifacts import canonical_json_hash as digest
ROOT=Path('/Users/l/Project/Recommandation')
P=ROOT/'runs/diagnostics/reviewed_owned_partial_stage_20261020_v1'
OUT=ROOT/'runs/diagnostics/reviewed_owned_partial_preflight_20261020_v1/independent'
def read(p):return json.loads(Path(p).read_text())
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
 return h.hexdigest()
def binding(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
start=time.monotonic()
assert {p.name for p in P.iterdir()}=={'manifest.json','contract.json','expectations.json','inputs.json','preflight.json'}
m=read(P/'manifest.json');c=read(P/'contract.json');i=read(P/'inputs.json');o=read(P/'expectations.json');f=read(P/'preflight.json')
assert sha(P/'manifest.json')=='c0f0a3bf3e50058df3a45d7113ce0b61278aad58ada93a92d44e1cebf35867b1'
assert m['manifest_hash']=='f1f9316ae2a1de5d21559fee7d04eddb9b28d6176fd1ba63205cdf343d41c7d3'
assert digest({k:v for k,v in m.items() if k!='manifest_hash'})==m['manifest_hash']
assert m['root']==str(P) and digest(c)==m['contract_hash']
for name,x in [('input',i),('expectations',o),('preflight',f)]:assert digest(x)==c[name+'_hash']
assert len(m['originals'])==6257 and len(m['code_files'])==102
by_path={}
for b in m['originals']+m['code_files']:
 assert set(b)=={'path','sha256'} and str(Path(b['path']).resolve())==b['path']
 assert b['path'] not in by_path or by_path[b['path']]==b['sha256']
 by_path[b['path']]=b['sha256']
assert len(by_path)==6264
for path,h in by_path.items():assert sha(path)==h,path
limits={'max_request_tokens':131072,'max_case_tokens':512000,'max_case_llm_calls':6,'max_structured_corrections':1,'structured_reasoning_token_reserve':0,'finalization_reserve':64000}
assert c['limits']==limits and c['max_local_calls']==6 and c['max_external_api_calls']==0 and c['fixed_denominator']==1 and c['backend']=='independent-subagent' and c['actual_model_version'] is None
oracle=ROOT/'reports/reviewed-owned-partial-expectations-20261020.json'
assert sha(oracle)=='e5569e23a250ac0ac7e792459b9a0856b086f4d841e8842abc44e433235eae2f' and read(oracle)==o
assert set(i)=={'historical_seed_not_new_F6','reviewed_source_snapshot','sample'} and i['historical_seed_not_new_F6'] is True
s=i['sample'];assert set(s)=={'sample_id','company_id','identity','prediction_time','plan','prior_state','selections','results','basic_info','prediction_baseline','computed_metrics','evaluation_anchor','signal_research_status'}
assert s['sample_id']=='p01'
seed=ROOT/'runs/diagnostics/reviewed_fast_prefix_20261020_v1'
old=read(seed/'inputs.json')['sample']
for key in ('company_id','identity','prediction_time','plan'):assert s[key]==old[key]
assert s['prior_state']==read(seed/'observations/initialize_00.json')['value']
assert s['selections']==read(seed/'observations/routing_00.json')['value']
by_ref={r['signal_id']+':v'+str(r['version']):r for n in ('signal_group_00.json','signal_group_01.json') for r in read(seed/'observations'/n)['results']}
assert s['results']==[by_ref[r['signal_ref']] for r in s['selections']]
assert [(r['signal_id'],r['version']) for r in s['results']]==[('financing_listing_action',5),('operating_cash_flow_margin',2)]
assert s['basic_info']==read(seed/'preflight.json')['model_context']
assert len(s['basic_info']['requests'])==2 and sum(len(r['projections']) for r in s['basic_info']['requests'])==17
assert '[ANON_ID_' not in json.dumps(s['basic_info']) and '[MASKED_COMPANY]' not in json.dumps(s['basic_info'])
context=read(seed/'prediction.json')['final_context']
for key in ('prediction_baseline','computed_metrics'):assert s[key]==context[key]
old_request=read(seed/'requests'/(read(seed/'observations/reflect_00.json')['request_hashes'][0]+'.json'))['request']
wire=json.loads(old_request['messages'][1]['content'])
for key in ('evaluation_anchor','signal_research_status'):assert s[key]==wire[key]
assert f=={'historical_seed_not_new_F6':True,'source_documents':1776,'plan_hash':digest(s['plan']),'prior_hash':digest(s['prior_state']),'source_batch_hash':digest(s['results'])}
source=read(o['bindings']['completed_source_result']['path']);assert source['reviewed_source_snapshot']==i['reviewed_source_snapshot']
v=i['reviewed_source_snapshot'];vp=Path(v['root'])/'reviewed_snapshot.json';vm=read(vp)
assert sha(vp)==v['manifest_sha256'] and len(vm['documents'])==1776
assert by_path[str(vp)]==sha(vp)
doc=read(o['bindings']['actual_cited_body']['path']);quotes=0
for r in s['results']:
 for e in r['evidence']['supporting']+r['evidence']['counter']:
  assert e['document_id']==doc['document_id'] and e['exact_span'] in doc['content']
  t=datetime.fromisoformat(e['timestamp']);cut=datetime.fromisoformat(s['prediction_time'])
  assert t.utcoffset() is not None and t<=cut
  quotes+=1
assert quotes==4
assert not (P/'requests').exists() and not (P/'exchange').exists()
out={'verdict':'PASS_frozen_inputs_only','manifest':binding(P/'manifest.json'),'manifest_canonical_hash':m['manifest_hash'],
 'formal_files':5,'source_original_bindings':6257,'code_bindings':102,'unique_current_SHA_verified':6264,
 'contract_limits':c['limits'],'max_local_calls':6,'external_api_calls':0,'fixed_denominator':1,
 'oracle_report':binding(oracle),'oracle_only_expectations_not_model_inputs':True,
 'historical_exact_allowlist':'Plan/identity/cutoff, accepted initial prior, routing selections, exact financing:v5 and OCF:v2 first batch, canonical preflight BasicInfo, old computed/baseline metadata only. No old prediction/finalstate/49/50 operations exported.',
 'canonical_BasicInfo_requests':2,'canonical_BasicInfo_projections':17,'view_documents':1776,'exact_current_body_quotes':4,
 'baseline_and_evaluation_anchor_exact_historical':True,'history_seed_commit':m['seed_commit'],'no_requests_or_exchange':True,
 'scope':'Read-only files/stream SHA. Did not instantiate Store or execute stage helpers/prepare/resume/GET/models/labels. Old prediction envelope parsed only to compare explicitly allowlisted baseline/computed metadata; its prediction/final state were not used.',
 'limits':['Legal native preflight is the frozen producer result checked against exact inputs and1776-member view; no independent Store reload in this audit.',
 'Fresh Reflect/Predictor behavior, typed correction exercise, persistence and completed restore are not yet executed here. Does not close F7/F9/MVP or establish research benefit.'],
 'elapsed_seconds':round(time.monotonic()-start,6)}
(OUT/'frozen-plan-independent-review.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(out,ensure_ascii=False,indent=2))
