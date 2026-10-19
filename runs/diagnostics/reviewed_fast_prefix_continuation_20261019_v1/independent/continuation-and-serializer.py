import json,hashlib,copy,tempfile,shutil
from pathlib import Path
from types import SimpleNamespace
from dataclasses import asdict
import run_reviewed_fast_prefix as h
from scripts.replay_incremental_reflection_memory import deny_network
from stock_opportunity_agent.research.evolution_core import AgentStep,AgentUsage,SignalSelectionDecision
from stock_opportunity_agent.data.resolution import RawInfoResolution
from stock_opportunity_agent.signal_library import SignalBatchResult,SignalResult,SignalValue,SignalCoverage
from stock_opportunity_agent.research.local_role_exchange import LocalRoleRequestPending,LocalRoleBudgetExhausted
repo=Path('/Users/l/Project/Recommandation');original=repo/'runs/diagnostics/reviewed_fast_prefix_20261019_v1';commit='1acfd2a4f1cd41c5837206211a911c5f32abc662'
def hashes(root):return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}
def reject(action,label,found):
 try:action();raise AssertionError('unexpected admission:'+label)
 except h.ValidationError as e:found.append({'case':label,'typed_rejected':True,'error':str(e)})
original_before=hashes(original);negative=[]
with tempfile.TemporaryDirectory(prefix='independent-continuation-') as td,deny_network() as network:
 base=Path(td).resolve();parent=base/'parent';shutil.copytree(original,parent)
 inputs=h.read_json(parent/'inputs.json');contract=h.read_json(parent/'contract.json');oracle=h.read_json(parent/'expectations.json');preflight=h.read_json(parent/'preflight.json')
 # Six fields with nonempty canonical resolution and skipped/fingerprint data.
 resolution=RawInfoResolution.from_dict(preflight['bundle']['requests'][0])
 result=SignalResult('synthetic_observer',1,SignalValue.UNAVAILABLE,0.0,'Synthetic observer fixture only.',coverage=SignalCoverage.UNAVAILABLE)
 batch=SignalBatchResult((result,),1,AgentUsage(llm_calls=2,tokens=123,cost=.1),(resolution,),{result.ref:('one','two','two')},('skipped:v7',))
 expected={'results':[result.to_dict()],'signal_calls':1,'usage':asdict(batch.usage),'resolutions':[resolution.to_dict()],'document_fingerprints':{result.ref:['one','two','two']},'skipped_unchanged_refs':['skipped:v7']}
 assert h._observation_record(batch)==expected
 assert 'data_gap' in expected['resolutions'][0] and 'gap' not in expected['resolutions'][0]
 instance=SimpleNamespace(execute_batch=lambda:batch);h._observe(instance,'execute_batch','synthetic_six_fields',base/'observer',SimpleNamespace(request_hash_trace=[]));assert instance.execute_batch() is batch
 saved=h.read_json(base/'observer/observations/synthetic_six_fields_00.json');assert saved=={**expected,'request_hashes':[]}
 empty=SignalBatchResult((),0,skipped_unchanged_refs=('same:v1',));assert set(h._observation_record(empty))==set(expected) and h._observation_record(empty)['skipped_unchanged_refs']==['same:v1']
 selections=tuple(SignalSelectionDecision(**row) for row in h.read_json(parent/'observations/routing_00.json')['value']);step=AgentStep(selections,AgentUsage(llm_calls=2,tokens=100),metadata={'synthetic':'unchanged'});assert h._observation_record(step)['value']==[x.to_dict() for x in selections]
 reject(lambda:h._observation_record({'unsupported':'family'}),'unknown_observer_family',negative)
 # Real original answers verified in a temporary copy, never execute failed v1.
 lineage=h._validate_parent(parent,commit,inputs,contract,oracle,preflight)
 assert lineage['inherited_receipts']==2 and lineage['maximum_new_requests']==30 and lineage['total_request_ceiling']==32
 expected_order=['89a34b9d9ffe11a5c749e25787ddb84af249d4a66bf35d1dff0886ea4f92ee45','d146eb080b82d53a9f6b02d06720b624f5f3da02a3df88d4b62363563b29b835'];assert lineage['inherited_request_hashes']==expected_order
 undispatched='8b5a557b060b93bc1dbd7e4fbfa791fd0986179adc81eb4b81591cb7022a17f9';assert lineage['undispatched_request_hashes']==[undispatched]
 for bad in ('HEAD',commit.upper(),'0'*40):reject(lambda bad=bad:h._validate_parent(parent,bad,inputs,contract,oracle,preflight),'bad_parent_commit:'+bad[:8],negative)
 for directory,name,mutator in [
  ('exchange/receipts',expected_order[0]+'.json',lambda d:{**d,'agent_id':'wrong-agent'}),
  ('cache/responses',expected_order[0]+'.json',lambda d:{**d,'json_output':{'changed':True}}),
  ('requests',expected_order[0]+'.json',lambda d:{**d,'request_hash':'0'*64}),
 ]:
  path=parent/directory/name;raw=path.read_bytes();path.write_text(json.dumps(mutator(json.loads(raw))))
  reject(lambda:h._validate_parent(parent,commit,inputs,contract,oracle,preflight),'parent_'+directory+'_tamper',negative);path.write_bytes(raw)
 path=parent/'exchange/outbox'/f'{expected_order[0]}.txt';raw=path.read_bytes();path.write_bytes(raw+b' ');reject(lambda:h._validate_parent(parent,commit,inputs,contract,oracle,preflight),'parent_raw_tamper',negative);path.write_bytes(raw)
 # Distinguish a journal-only attempt from missing/partial answered originals.
 path=parent/'exchange/outbox'/f'{undispatched}.txt';path.write_text('{}');reject(lambda:h._validate_parent(parent,commit,inputs,contract,oracle,preflight),'journal_only_with_orphan_raw_cannot_be_undispatched',negative);path.unlink()
 for directory,suffix in [('exchange/receipts','json'),('exchange/inbox','json')]:
  path=parent/directory/f'{expected_order[0]}.{suffix}';raw=path.read_bytes();path.unlink();reject(lambda:h._validate_parent(parent,commit,inputs,contract,oracle,preflight),'missing_answered_'+directory,negative);path.write_bytes(raw)
 four=[parent/d/f'{expected_order[0]}.{suffix}' for d,suffix in [('exchange/inbox','json'),('exchange/outbox','txt'),('exchange/receipts','json'),('cache/responses','json')]]
 originals={p:p.read_bytes() for p in four}
 for p in four:p.unlink()
 reject(lambda:h._validate_parent(parent,commit,inputs,contract,oracle,preflight),'answered_observation_cannot_be_downgraded_to_undispatched',negative)
 for p,raw in originals.items():p.write_bytes(raw)
 # Source byte verification against the immutable parent commit.
 path=parent/'manifest.json';raw=path.read_bytes();m=json.loads(raw);m['code_files'][0]['sha256']='0'*64;m.pop('manifest_hash');m['manifest_hash']=h.canonical_json_hash(m);path.write_text(json.dumps(m));reject(lambda:h._validate_parent(parent,commit,inputs,contract,oracle,preflight),'rehashed_wrong_parent_code_hash',negative);path.write_bytes(raw)
 child=base/'child';prepared=h.prepare(child,repo/'reports/reviewed-fast-prefix-expectations-20261019.json',parent_root=parent,parent_commit=commit)
 h._verify(child)
 for row in lineage['copied_files']:assert (child/row['relative_path']).read_bytes()==Path(row['path']).read_bytes()
 assert not any((child/name).exists() for name in ('failure.json','progress.json','.prefix.lock','.dispatch.lock'))
 for label,action,undo in [
  ('parent_inventory_extra',lambda:(parent/'extra-artifact.json').write_text('{}'),lambda:(parent/'extra-artifact.json').unlink()),
  ('parent_inventory_missing',lambda:(parent/'failure.json').rename(parent/'saved-failure.tmp'),lambda:(parent/'saved-failure.tmp').rename(parent/'failure.json')),
 ]:
  action();reject(lambda:h._verify(child),label,negative);undo()
 path=child/'exchange/receipts'/f'{expected_order[0]}.json';raw=path.read_bytes();path.write_bytes(raw+b' ');reject(lambda:h._verify(child),'child_inherited_receipt_byte_tamper',negative);path.write_bytes(raw)
 # Verify inherited first-request order before any new dispatch.
 reqs=[h.read_json(parent/'requests'/f'{q}.json')['request'] for q in expected_order]
 ex=h._ContinuationExchange(child/'exchange',max_calls=32,inherited=expected_order);before=hashes(child)
 reject(lambda:ex.receive(reqs[1],accounting_tokens=0,allow_dispatch=False),'inherited_wrong_order',negative);assert hashes(child)==before
 # Exactly 30 new inbox slots after two verified inherited slots; no answer fixtures for new slots.
 budget=base/'budget';shutil.copytree(child/'exchange',budget/'exchange');ex=h._ContinuationExchange(budget/'exchange',max_calls=32,inherited=expected_order)
 for request in reqs:
  reservation=len(json.dumps(request['messages'],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode())+request['max_output_tokens'];ex.receive(request,accounting_tokens=reservation,allow_dispatch=False)
 for index in range(30):
  request={'stage':'synthetic_budget_slot','messages':[{'role':'user','content':str(index)}],'max_output_tokens':1}
  try:ex.receive(request,accounting_tokens=1);raise AssertionError('new slot without answer should pend')
  except LocalRoleRequestPending:pass
 assert len(list((budget/'exchange/inbox').glob('*.json')))==32
 try:ex.receive({'stage':'synthetic_budget_slot','messages':[{'role':'user','content':'overflow'}],'max_output_tokens':1},accounting_tokens=1);raise AssertionError('33rd slot admitted')
 except LocalRoleBudgetExhausted:pass
 # Actual child native traversal reuses two exact originals then reaches a new unresponded input.
 native=h.resume(child);assert native['status']=='pending_independent_role',native
 assert native['independent_receipts']==2
 group=h.read_json(child/'observations/signal_group_00.json');assert set(group)==set(expected)|{'request_hashes'}
 assert len(group['results'])==2 and all(x['execution']['status']=='budget_blocked' and x['execution']['error_code']=='signal_partition_budget_blocked' for x in group['results'])
 assert not (child/'prediction.json').exists() and not (child/'completion.json').exists()
 assert hashes(parent)==original_before
 current_source_bindings={str(p.relative_to(repo)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [repo/'scripts/run_reviewed_fast_prefix.py',repo/'spec/scripts/run_reviewed_fast_prefix.md']}
 out={'scope':'Independent temporary-copy failed-parent continuation/observer audit only. Exactly two historical original role answers reused; zero fresh model answers. Failed v1 never resumed or edited.','serializer_six_fields_exact':True,'nonempty_canonical_resolution_preserves_data_gap_and_coverage':True,'results_usage_fingerprints_skips_exact':True,'wrapper_returns_identical_object':True,'empty_skipped_and_tuple_step_supported':True,'parent_source_commit':commit,'verified_parent_code_file_count':len(h.read_json(parent/'manifest.json')['code_files']),'inherited_request_order':expected_order,'inherited_receipts':2,'undispatched_journal_only':[undispatched],'maximum_new_requests':30,'total_ceiling':32,'negative_cases':negative,'synthetic_33rd_inbox_rejected':True,'actual_temp_native_child':{'status':native['status'],'next_stage':native['pending'][0]['stage'],'next_request_hash':native['pending'][0]['request_hash'],'receipts':native['independent_receipts'],'six_field_group_recorded':True,'results':[{'signal_ref':str(x['signal_id'])+':v'+str(x['version']),'state':x['state'],'execution':x['execution'],'status':x['status']} for x in group['results']],'group_usage':group['usage'],'inherited_observations_and_files_exact':True,'prediction_or_completion_created':False},'original_parent_all_file_bytes_unchanged':True,'network_attempts':network['network_attempts'],'fresh_role_answers':0,'current_source_bindings':current_source_bindings}
 assert hashes(original)==original_before
 Path('/tmp/independent-prefix-continuation-results.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
