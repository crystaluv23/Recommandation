"""Short file-only audit of three newly prepared five-file native stages."""
from pathlib import Path
from copy import deepcopy
import hashlib,json
from stock_opportunity_agent.artifacts import canonical_json_hash as digest
import run_reviewed_owned_partial_stage as runner
R=Path('/Users/l/Project/Recommandation');OUT=R/'runs/diagnostics/reviewed_owned_temporal_preflight_20261021_v1';B=R/'runs/diagnostics/reviewed_owned_temporal_stage_20261021_v1';A=R/'runs/diagnostics/owned_partial_three_controls_20261021_v1'
def read(p):return json.loads(Path(p).read_text())
def bind(p):return {'path':str(Path(p).resolve()),'sha256':hashlib.sha256(Path(p).read_bytes()).hexdigest()}
assert bind(Path(runner.__file__))['sha256']=='01c058eb996805c86bc12e1e27b4005b82d0ab19e5b8f7c517d5544c59001d16'
expected=read(A/'expectations.json');private=read(A/'oracle-review.json')['contract_feasibility']['private_feasibility_witness'];old=read(R/'runs/diagnostics/reviewed_owned_partial_stage_20261020_v1/inputs.json')['sample']
assert bind(A/'expectations.json')['sha256']=='a5d5d3049ce6efaa1bc2609824d277ed29d55e074160bd4c89d97617097714d8'
source_result=read(R/'runs/diagnostics/reviewed_gpre_capture_snapshot_20261021_v1/stage/result.json');source_plan=read(R/'runs/diagnostics/reviewed_gpre_capture_snapshot_20261021_v1/stage/plan.json')
rows=[];code=None;originals=None;history=None
for sid in ('p01','p02','p03'):
 root=B/sid;assert sorted(p.name for p in root.iterdir())==['contract.json','expectations.json','inputs.json','manifest.json','preflight.json']
 values={n:read(root/(n+'.json')) for n in ('inputs','expectations','contract','manifest','preflight')};i,e,c,m,p=(values[n] for n in ('inputs','expectations','contract','manifest','preflight'))
 assert digest(e)==digest(expected) and digest(i)==c['input_hash'] and digest(e)==c['expectations_hash'] and digest(p)==c['preflight_hash']
 assert digest(c)==m['contract_hash'] and digest({k:v for k,v in m.items() if k!='manifest_hash'})==m['manifest_hash']
 assert m['root']==str(root) and set(i)=={'sample','reviewed_source_snapshot','historical_seed_not_new_F6'} and i['historical_seed_not_new_F6'] is True
 assert set(i['sample'])==set(old) and i['reviewed_source_snapshot']==source_result['reviewed_source_snapshot']
 s=deepcopy(i['sample']);assert s['sample_id']==sid and s['prior_state']['next_information_needs'][4]==runner.CONTROL_NEEDS[sid]==expected['questions'][sid]
 assert s['prior_state']['next_information_needs'][:4]==old['prior_state']['next_information_needs'][:4]
 s['sample_id']=old['sample_id'];s['prior_state']['next_information_needs'][4]=old['prior_state']['next_information_needs'][4]
 assert digest(s)==digest(old),'Sample changed beyond ID/need4'
 assert private not in json.dumps(i,ensure_ascii=False)
 assert p['historical_seed_not_new_F6'] is True and p['source_documents']==1780
 assert p['prior_hash']==digest(i['sample']['prior_state']) and p['plan_hash']==digest(i['sample']['plan']) and p['source_batch_hash']==digest(i['sample']['results'])
 assert len(i['sample']['results'])==2 and [x['signal_ref'] for x in i['sample']['selections']]==['financing_listing_action:v5','operating_cash_flow_margin:v2']
 assert sum(len(x['projections']) for x in i['sample']['basic_info']['requests'])==17
 assert c['fixed_denominator']==3 and c['max_local_calls']==6 and c['max_external_api_calls']==0 and c['actual_model_version'] is None
 assert c['limits']==runner.LIMITS and c['source_profile']==runner.CAPTURE_SOURCE_PROFILE
 control=runner._control_set(e,root,sid,c['source_profile'],m['historical_source_code']['commit']);assert digest(control)==digest(c['control_set'])
 assert m['seed_commit']==runner.CONTROL_SEED_COMMIT and m['historical_source_code']['commit']==runner.CAPTURE_SOURCE_COMMIT
 assert m['historical_source_code']['plan']==bind(R/'runs/diagnostics/reviewed_gpre_capture_snapshot_20261021_v1/stage/plan.json')
 assert m['historical_source_code']['code_files']==source_plan['code_bindings'] and len(m['historical_source_code']['code_files'])==116
 assert len(m['code_files'])==107 and len(m['originals'])==7938
 if code is None:code=m['code_files'];originals=m['originals'];history=m['historical_source_code']
 else:assert m['code_files']==code and m['originals']==originals and m['historical_source_code']==history
 # Historical changed code is not erroneously required to equal current file bytes as data.
 current={x['path']:x['sha256'] for x in code};data={x['path']:x['sha256'] for x in originals}
 for binding in history['code_files']:
  if binding['path'] in current and binding['sha256']!=current[binding['path']]:assert binding['path'] not in data
 rows.append({'sample_id':sid,'manifest_hash':m['manifest_hash'],'contract_hash':digest(c),'input_hash':digest(i),'preflight_hash':digest(p),'five_files':[bind(root/(n+'.json')) for n in ('inputs','expectations','contract','manifest','preflight')],'sample_exact_except_ID_and_owned_need4':True,'prior_needs0_3_occurrences_preserved':True,'source_documents':1780,'bootstrap_cards_for_final_Predictor':17,'historical_batch_not_fresh_F6':True})
out={'verdict':'PASS_three_actual_five_file_freezes_only','fixed_denominator':3,'stages':rows,'current_code_files':107,'historical_code_files':116,'original_bindings_per_stage':7938,'source_commit':runner.CAPTURE_SOURCE_COMMIT,'seed_commit':runner.CONTROL_SEED_COMMIT,'all_three_share_exact_originals_and_current_code':True,'percase_calls_tokens':[6,512000],'aggregate_calls_tokens':[18,1536000],'no_requests_exchange_or_roles':True,'oracle_or_private_witness_absent_from_inputs':True,'limits':['This is a short structural/canonical/sample audit. Root separately performs the one complete unique-source/current-code SHA inventory check; this audit does not duplicate it.','17 canonical bootstrap cards are preserved for finalcontext/Predictor, not claimed all visible to Reflect. Actual pending anonymity/wire remains a later check.','No fresh model behavior or semantic outcome yet; p01/p02 require properpartial, p03 requires full, old0/1 remains failed. No direct role dispatch, Store, prepare, resume, GET, labels or code modification.'],'audit_script':bind(__file__)}
(OUT/'frozen-input-independent-review.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'verdict':out['verdict'],'stages':[{k:v for k,v in x.items() if k in ('sample_id','manifest_hash','contract_hash','input_hash')} for x in rows],'review':bind(OUT/'frozen-input-independent-review.json')},indent=2))
