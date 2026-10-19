import json,hashlib,tempfile
from pathlib import Path
from scripts.replay_incremental_reflection_memory import deny_network
import run_reviewed_fast_prefix as h
repo=Path('/Users/l/Project/Recommandation')
with tempfile.TemporaryDirectory(prefix='independent-fast-prefix-') as td,deny_network() as network:
 root=Path(td)/'stage'
 prep=h.prepare(root,repo/'reports/reviewed-fast-prefix-expectations-20261019.json')
 first=h.resume(root); assert first['status']=='pending_independent_role',first
 wirepath=Path(first['pending'][0]['inbox_path']);raw=wirepath.read_bytes();record=json.loads(raw);payload=json.loads(record['messages'][-1]['content'])
 second=h.resume(root)
 assert second['status']=='pending_independent_role' and second['pending'][0]['request_hash']==first['pending'][0]['request_hash']
 assert wirepath.read_bytes()==raw
 assert len(list((root/'exchange/inbox').glob('*.json')))==1 and not list((root/'exchange/receipts').glob('*.json'))
 wire=json.dumps(record['messages']);assert all(alias not in wire for alias in ('BMBL','Bumble','cik_0001830043'))
 assert not (root/'prediction.json').exists() and not (root/'completion.json').exists()
 assert 'expectations' not in payload and 'oracle' not in wire.lower()
 manifest=json.load(open(root/'manifest.json'));inputs=json.load(open(root/'inputs.json'));contract=json.load(open(root/'contract.json'))
 registry_before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(inputs['registry_root']).rglob('*') if p.is_file()}
 assert inputs['registry_hash'] and inputs['learning_hash']
 # Mutation checks are isolated in this temporary, unresponded preparation.
 original_inputs=(root/'inputs.json').read_bytes();obj=json.loads(original_inputs);obj['learning_hash']='0'*64;(root/'inputs.json').write_text(json.dumps(obj))
 try:h.resume(root);raise AssertionError('input mutation accepted')
 except h.ValidationError:pass
 (root/'inputs.json').write_bytes(original_inputs)
 original_contract=(root/'contract.json').read_bytes();obj=json.loads(original_contract);obj['max_local_calls']=33;(root/'contract.json').write_text(json.dumps(obj))
 try:h.resume(root);raise AssertionError('ceiling mutation accepted')
 except h.ValidationError:pass
 (root/'contract.json').write_bytes(original_contract)
 assert registry_before=={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(inputs['registry_root']).rglob('*') if p.is_file()}
 out={'scope':'Only actual frozen native first H_init input and duplicate pending resume; no role answers, no warm-cache multi-call traversal or completed restore exercised.','prepare':prep,'first_status':first['status'],'second_status':second['status'],'stage':first['pending'][0]['stage'],'request_hash':first['pending'][0]['request_hash'],'inbox_sha256':hashlib.sha256(raw).hexdigest(),'request_messages_sha256':hashlib.sha256(json.dumps(record['messages'],ensure_ascii=False,sort_keys=True).encode()).hexdigest(),'anonymous':True,'inbox_count':1,'receipts':0,'answers':0,'network_attempts':network['network_attempts'],'no_prediction_or_completion':True,'frozen_input_and_call_ceiling_mutations_rejected':True,'registry_originals_unchanged':True,'registry_hash':inputs['registry_hash'],'learning_hash':inputs['learning_hash'],'registry_refs':len(inputs['registry_refs']),'code_files':len(manifest['code_files']),'registry_files':len(manifest['registry_files']),'code_bindings':{str(p.relative_to(repo)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [repo/'scripts/run_reviewed_fast_prefix.py',repo/'spec/scripts/run_reviewed_fast_prefix.md']},'runtime_limits':contract['runtime_limits'],'local_calls':contract['max_local_calls'],'payload_top_keys':list(payload),'payload':payload}
 Path('/tmp/independent-fast-prefix-preflight-results.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({k:v for k,v in out.items() if k!='payload'},indent=2))
