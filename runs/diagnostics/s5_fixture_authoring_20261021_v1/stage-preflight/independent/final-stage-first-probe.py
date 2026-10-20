"""Temporary native tests-author stage counterreview; no formal stage or model."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from copy import deepcopy
import hashlib,json
from scripts import run_reviewed_fixture_author_stage as s
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.artifacts import canonical_json_hash as digest
R=Path('/Users/l/Project/Recommandation');D=R/'runs/diagnostics/s5_fixture_authoring_20261021_v1/stage-preflight/independent';sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();bind=lambda p:{'path':str(Path(p).resolve()),'sha256':sha(p)}
expected={'scripts/run_reviewed_fixture_author_stage.py':'fa11b07629c588435a31703d5fffc5d26407f30c41fa2abb43cbaf0f684f325e','spec/scripts/run_reviewed_fixture_author_stage.md':'e85f4c1cd48c2c868b1a0d3caaf2c1eb085f169d5de96112ac19d0b6ea0ed7ca','tests/test_reviewed_fixture_author_stage.py':'cdf0e810923731730d14da868bd7ae299a02119f7a7e6e5dccb30a9b7019bf53'}
for p,h in expected.items():assert sha(R/p)==h
oldsource=D.parent/'original-stage/run_reviewed_fixture_author_stage.py';assert sha(oldsource)=='770715c059840387eb334e95a97bd11b69910f113e4edee3369eb9e4f7943878'
original=json.loads((D/'literal-carrier-results.json').read_text());answer=deepcopy(original['rows'][0]['authored_answer']);decoy=deepcopy(original['rows'][1]['authored_answer']);rows=[]
def tree(root):return {str(p.relative_to(root)):sha(p) for p in root.rglob('*') if p.is_file()}
def reject(action,word=None):
 try:action()
 except ValidationError as error:
  if word:assert word in str(error),(word,str(error))
  return str(error)
 raise AssertionError('Expected rejection')
def run(name,answer_text,success):
 with TemporaryDirectory(prefix='independent-S5-stage-final-') as t:
  root=Path(t)/'stage'
  with patch.object(s,'STAGE_ROOT',root):
   s.prepare(root);before=tree(root);assert len(before)==4 and not (root/'exchange').exists()
   pending=s.resume(root);again=s.resume(root);assert pending==again and pending['status']=='pending_independent_role'
   h=pending['pending']['request_hash'];journal=s.read(root/'requests'/f'{h}.json');req=journal['request'];inbox=s.read(root/'exchange/inbox'/f'{h}.json');payload=json.loads(inbox['messages'][1]['content'])
   assert h==digest(req)==journal['request_hash']==inbox['request_hash'] and req['messages']==inbox['messages'] and req['max_output_tokens']==4000
   assert 'tests_schema' in payload and 'execution_semantics' in payload and 'expectations' not in payload and 'positive_measurement' not in payload
   assert len(list((root/'exchange/inbox').glob('*.json')))==1 and not list((root/'exchange/receipts').glob('*.json'))
   out=root/'exchange/outbox'/f'{h}.txt';out.write_text(answer_text);s.submit(root,h,'offline-independent-stage-review');receipt=s.read(root/'exchange/receipts'/f'{h}.json');assert receipt['raw_output_sha256']==sha(out) and receipt['inbox_sha256']==sha(root/'exchange/inbox'/f'{h}.json')
   result=s.resume(root);assert (result['status']=='module_completed_requires_independent_review')==success,result
   assert len(list((root/'exchange/inbox').glob('*.json')))==len(list((root/'exchange/receipts').glob('*.json')))==1
   units=len(json.dumps(req['messages'],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode())+4000;assert result['logical_reservation']==units<=131072 and out.read_text()==answer_text
   before=tree(root)
   with patch.object(s,'_engine',side_effect=AssertionError('Restore must not execute')):
    restored=s.resume(root)
   assert restored['restored_without_execution'] and tree(root)==before
   record={'control':name,'status':result['status'],'logical_reservation':units,'physical_fixture_receipts':1,'restore_all_files_equal':True,'restored_files':len(before),'raw_sha256':sha(out),'request_hash':h}
   if success:
    loaded=s.read(root/'loaded-candidate.json');assert loaded['loaded_tests']==json.loads(answer_text)['tests'] and loaded['schemas']==['legacy','typed'];assert all(x['measurement']['value']==.25 and x['measurement']['period_start']=='2024-01-01' and x['measurement']['period_end']=='2024-12-31' for x in loaded['results']);record['actual_loaded_candidate']=loaded
    cache=s.read(root/'cache/responses'/f'{h}.json');assert cache['raw_output']==answer_text and cache['json_output']==json.loads(answer_text) and cache['usage']['accounting_tokens']==units
    receiptpath=root/'exchange/receipts'/f'{h}.json';old=receiptpath.read_bytes();changed=s.read(receiptpath);changed['raw_output_sha256']='0'*64;s.atomic_write_json(receiptpath,changed)
    with patch.object(s,'_engine',side_effect=AssertionError('Drift must not execute')):record['drift_restore_rejected']=reject(lambda:s.resume(root),'terminal artifact drift')
    receiptpath.write_bytes(old);assert tree(root)==before
   else:record['error']=result['error']
   rows.append(record)
run('native_pending_original_receipt_stage_load_restore',json.dumps(answer),True)
assert original['rows'][1]['result']['status']=='module_completed_requires_independent_review'
run('same_original_dead_literal_carrier_new_reject',json.dumps(decoy),False)
alt=deepcopy(answer);body=json.loads(alt['tests'][1]['documents'][0]['content']);changed=deepcopy(body['facts'])
for fact in changed:fact['value']*=10
body['facts']=changed+body['facts'];alt['tests'][1]['documents'][0]['content']=json.dumps(body,sort_keys=True,separators=(',',':'));run('same_ratio_alternative_executed_basis_not_supplied',json.dumps(alt),False)
mixed=deepcopy(answer);mixed['tests'][0]['documents']+=mixed['tests'][1]['documents'];mixed['tests'].pop();run('one_mixed_schema_fixture_cannot_supply_two',json.dumps(mixed),False)
wrong=deepcopy(answer);wrong['tests'][1]['documents'][0]['metadata']['cik']=2;run('issuer_mismatch_cannot_be_positive',json.dumps(wrong),False)
run('invalid_first_json_terminal_no_retry',json.dumps(answer)[:-1],False)
with TemporaryDirectory(prefix='independent-S5-stage-boundary-') as t:
 root=Path(t)/'stage'
 with patch.object(s,'STAGE_ROOT',root):
  reject(lambda:s.prepare(root.parent/'renamed'),'destination');assert not root.exists();rows.append({'control':'fixed_root_rename_before_creation','rejected':True})
  s.prepare(root);mp=root/'manifest.json';originalmp=mp.read_bytes()
  for name,alter in [('contract',lambda v:v.update(max_calls=True)),('inputs',lambda v:v['accepted']['spec'].update(version=True)),('code',lambda v:v[0].update(sha256='0'*64))]:
   manifest=s.read(mp);manifest.pop('manifest_hash');saved=None
   if name!='code':saved=(root/f'{name}.json').read_bytes()
   alter(manifest[name])
   if name!='code':s.atomic_write_json(root/f'{name}.json',manifest[name])
   manifest['manifest_hash']=digest(manifest);s.atomic_write_json(mp,manifest)
   with patch.object(s,'_engine',side_effect=AssertionError('Drift reached engine')):message=reject(lambda:s.resume(root),'changed')
   assert not (root/'exchange').exists();rows.append({'control':name+'_coherent_rehash_drift_pre_dispatch','rejected':message})
   mp.write_bytes(originalmp)
   if saved is not None:(root/f'{name}.json').write_bytes(saved)
  q=root/'synthetic-budget.json';base={'stage':s.STAGE,'max_output_tokens':4000,'messages':[{'role':'user','content':'small'}]}
  for name,change in [('correction_stage',{'stage':s.STAGE+'_correction'}),('oversize',{'messages':[{'role':'user','content':'x'*131072}]}),('output4001',{'max_output_tokens':4001})]:
   s.atomic_write_json(q,{'request':{**base,**change}});message=reject(lambda:s._Budget()({'event_type':'request_ready','request_path':str(q),'request_hash':'a'*64}));rows.append({'control':name,'rejected':message})
  s.atomic_write_json(q,{'request':base});budget=s._Budget();event={'event_type':'request_ready','request_path':str(q),'request_hash':'a'*64};budget(event);message=reject(lambda:budget(event));rows.append({'control':'second_request_no_borrowed_budget','rejected':message})
for p,h in expected.items():assert sha(R/p)==h
report={'verdict':'PASS_bounded_stage_preflight_after_literal_carrier_fix','controls':len(rows),'rows':rows,'sources':{p:bind(R/p) for p in expected},'probe':bind(__file__),'original_stage_source':bind(oldsource),'old_counterexample':bind(D/'literal-carrier-results.json'),'scope':['Temporary patched fixed root is an explicitly offline test fixture; no formal root prepare/dispatch/submit/resume occurred.','All answers are independently scripted probes, not model behavior; no real GET/labels/published Registry/global source write.','Original dead-carrier failure preserved; native ratio itself was valid0.25, the fixed issue was exact supplied operand-row qualification.','Fresh S5 remains untested until formally frozen exact-inbox role; this stage is not full Mining/publication/independent gain.']}
p=D/'final-stage-review.json';p.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print('PASS',len(rows),'controls',sha(p))
