"""Read-only canonical journal/inbox and frozen binding check; never opens outbox."""
from pathlib import Path
import json,hashlib
from stock_opportunity_agent.artifacts import canonical_json_hash
REPO=Path('/Users/l/Project/Recommandation');OUT=Path(__file__).resolve().parent
root=REPO/'runs/diagnostics/reviewed_posthoc_stage_20261020_v1';old=OUT.parent/'actual-pending-inbox.json';digest='beba78080ab4e2d68a1bfd55ea99550f45c5a02d1be4ad75799952f3ad58049d'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
j=read(root/'requests'/f'{digest}.json');inboxpath=root/'exchange/inbox'/f'{digest}.json';inbox=read(inboxpath);m=read(root/'manifest.json');c=read(root/'contract.json');inputs=read(root/'inputs.json');e=read(root/'expectations.json')
q=j['request'];assert canonical_json_hash(q)==digest==j['request_hash'];assert q['contract_hash']==canonical_json_hash(c);assert q['stage']=='blind_predictor_posthoc_reflect'
expected={'schema_version':'independent-local-role-inbox-v1','request_hash':digest,'backend':'independent-subagent','messages':q['messages'],'max_output_tokens':q['max_output_tokens'],'output_contract':q.get('output_contract',q.get('response_format'))};assert inbox==expected;assert inboxpath.read_bytes()==old.read_bytes()
manifesthash=m.pop('manifest_hash');assert manifesthash==canonical_json_hash(m);assert m['contract_hash']==canonical_json_hash(c);assert c['input_hash']==canonical_json_hash(inputs);assert c['expectations_hash']==canonical_json_hash(e)
for row in m['code_files']+m['originals']+inputs['qualification']['label_files']:assert sha(Path(row['path']))==row['sha256'],row['path']
assert inputs['qualification']['manifest']==read(Path(inputs['label_root'])/'manifest.json')
payload=json.loads(q['messages'][-1]['content']);qualification=inputs['qualification'];baseline=payload['compact_context']['prediction_baseline'];assert payload['revealed_ground_truth']==qualification['truth'];assert qualification['record']['baseline_mean']==baseline['mean_adjusted_close'];assert qualification['record']['baseline_dates']==baseline['trading_dates'];assert qualification['record']['horizon_end']=='2026-03-30'
out={'all_passed':True,'decision':'Formal exact pending may be dispatched under the frozen stage; semantic outcome remains unobserved.','request_hash':digest,'journal_sha256':sha(root/'requests'/f'{digest}.json'),'inbox_sha256':sha(inboxpath),'inbox_exact_preflight_bytes':True,'manifest_hash':manifesthash,'frozen_code_files':len(m['code_files']),'oracle_sha256':sha(root/'expectations.json'),'contract_hash':canonical_json_hash(c),'input_hash':canonical_json_hash(inputs),'label_file_hashes':qualification['label_files'],'archive_binding_not_reread':qualification['archive'],'qualification_truth_baseline_and_horizon_exact_wire':True,'future_outboxes_read':False,'network_or_model_calls':0,'formal_resume_or_submit':False,'scope':'Full journal canonical hash, exact inbox identity, current code/oracle/label small-file bindings only. No repeated large archive qualification.','script_sha256':sha(Path(__file__))}
p=OUT/'formal-pending-identity.json';assert not p.exists();p.write_text(json.dumps(out,indent=2)+'\n');print(p);print(sha(p))
