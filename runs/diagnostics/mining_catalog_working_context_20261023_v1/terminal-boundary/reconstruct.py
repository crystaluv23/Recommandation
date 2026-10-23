"""Offline native controller/frozen-answer reconstruction. Never calls stage entry."""
from pathlib import Path
from copy import deepcopy
from datetime import datetime
from tempfile import TemporaryDirectory
from types import MethodType,SimpleNamespace
from unittest.mock import patch
import importlib.util,hashlib,json,shutil,socket,traceback
from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.research.mining_role_model import MiningRequestBudgetExhausted
from stock_opportunity_agent.research.stage_contracts import json_bytes
R=Path('/Users/l/Project/Recommandation');B=R/'runs/diagnostics/icfr_native_capability_20261023_v1/stage-v3';O=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def dump(n,x):(O/(n+'.json')).write_text(json.dumps(x,ensure_ascii=False,indent=2,default=str)+'\n')
def allfiles():return {str(p.relative_to(B)):sha(p) for p in sorted(B.rglob('*')) if p.is_file()}
before=allfiles();dump('stage-before',before);completion=read(B/'completion.json');assert all(before[n]==h for n,h in completion['files'].items());manifest=read(B/'manifest.json');assert all(sha(x['path'])==x['sha256'] for x in manifest['code']);assert len(manifest['code'])==182
spec=importlib.util.spec_from_file_location('independent_terminal_stage_contract',R/'scripts/run_icfr_native_capability_stage.py');d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)
receipts={}
for p in (B/'exchange/receipts').glob('*.json'):
 row=read(p);i=int(row['agent_id'].rsplit('h',1)[1]);assert 1<=i<=10;receipts[i]=row
assert set(receipts)==set(range(1,11));ids=[receipts[i]['request_hash'] for i in range(1,11)]
budget=d.Budget(B);records=budget.records();assert len(records)==10;assert budget.used()==budget.used('mining');wire_rows=[]
for i,h in enumerate(ids,1):
 request=read(B/'transport/requests'/f'{h}.json')['request'];inbox=read(B/'exchange/inbox'/f'{h}.json');assert request['messages']==inbox['messages'];cost=json_bytes(request['messages'])+request['max_output_tokens'];assert cost==records[h]['reservation'];v=json.loads(request['messages'][1]['content']);assert int(v['request_budget']['this_request'])==cost
 wire_rows.append({'h':i,'request_hash':h,'cost':cost,'scope_memberships':records[h]['scopes'],'budget':v['request_budget'],'raw_answer':read(B/'exchange/outbox'/f'{h}.txt')})
assert wire_rows[8]['cost']==258996 and wire_rows[9]['cost']==260104
assert budget.used()==(10,sum(x['cost'] for x in wire_rows));assert len(list((B/'exchange/inbox').glob('*.json')))==10
actual_requests=[read(B/'transport/requests'/f'{h}.json')['request'] for h in ids]
class ReplayCaller(d.Caller):
 def __init__(self,*args,**kwargs):
  super().__init__(*args,**kwargs);self.budget=SimpleNamespace(scope='mining');self.index=0;self.estimates=[];self.aligned=[]
 def estimate_json_request_tokens(self,**kwargs):
  result=super().estimate_json_request_tokens(**kwargs)
  if kwargs.get('payload',{}).get('request_budget',{}).get('calls_used')==10:
   projection=self._request_identity_projection(kwargs.get('anonymous_aliases',()))
   outgoing={'system_prompt':kwargs['system_prompt']+d.ASSIGNMENT,'payload':kwargs['payload']}
   outgoing,_=projection.project(outgoing) if projection is not None else (outgoing,{})
   messages=[{'role':'system','content':'Return exactly one JSON object and no non-JSON text. '+outgoing['system_prompt']},{'role':'user','content':json.dumps(outgoing['payload'],ensure_ascii=False,sort_keys=True,separators=(',',':'))}]
   assert json_bytes(messages)+self._output_limit(kwargs.get('max_output_tokens'))==result
   self.estimates.append({'required':result,'messages':messages,'max_output_tokens':self._output_limit(kwargs.get('max_output_tokens')),'payload':outgoing['payload']})
  return result
 def _complete_json_request(self,**kwargs):
  # This boundary returns ONLY a recorded original answer. No prepare/cache/receive occurs.
  assert self.index<10,'new prepare/answer prohibited'
  actual=actual_requests[self.index];messages=[{'role':'system','content':'Return exactly one JSON object and no non-JSON text. '+kwargs['system_prompt']},{'role':'user','content':json.dumps(kwargs['payload'],ensure_ascii=False,sort_keys=True,separators=(',',':'))}]
  if messages!=actual['messages']:
   expected=json.loads(actual['messages'][1]['content']);given=kwargs['payload'];dump('first-replay-mismatch',{'h':self.index+1,'different_top_fields':[k for k in set(expected)|set(given) if expected.get(k)!=given.get(k)],'expected':expected,'actual':given});raise AssertionError('native projected view/messages differs at h'+str(self.index+1))
  assert kwargs['stage']==actual['stage'] and self._output_limit(kwargs.get('max_output_tokens'))==actual['max_output_tokens']
  h=ids[self.index];assert canonical_json_hash(actual)==h
  self.aligned.append({'h':self.index+1,'actual_request_hash':h,'native_projected_messages_exact':True,'complete_cost':json_bytes(messages)+actual['max_output_tokens']})
  answer=deepcopy(wire_rows[self.index]['raw_answer']);self.index+=1
  return answer,d.AgentUsage(llm_calls=1,tokens=wire_rows[self.index-1]['cost'],cost=0),None
class ReplayEngine(d.SignalEvolutionEngine):
 def _new_mining_controller(self,**kwargs):
  kwargs['model'].request_limits.update(total_limit=12*d.MIB,call_limit=80)
  controller=super()._new_mining_controller(**kwargs);self.offline_controller=controller;return controller
result={'offline_frozen_answer_replay_only':True,'stage_entry_called':False,'new_prepare_calls':0,'receive_calls':0,'wire_accounting':wire_rows,'unique_answered':budget.used(),'mining_remaining':budget.remaining(),'terminal_result':completion['result']}
try:
 with TemporaryDirectory(prefix='offline-copy-',dir=O) as temporary,patch.object(socket.socket,'connect',side_effect=AssertionError('network prohibited')),patch.object(d.LocalRoleExchange,'receive',side_effect=AssertionError('receive prohibited')):
  temp=Path(temporary);work=temp/'workspace';shutil.copytree(B/'workspace',work)
  dev_data=read(B/'inputs/dev.json');identities=tuple(SimpleNamespace(**{**row,'prediction_time':datetime.fromisoformat(row['prediction_time'])}) for row in read(B/'inputs/identities.json')['identities']);by_id={c.case_id:c for c in identities}
  dev=tuple(SimpleNamespace(**{**vars(by_id[row['case_id']]),'ground_truth':SimpleNamespace(is_surge=dev_data['groups'][row['case_ref']]=='positive')}) for row in dev_data['cases'])
  sources=[x for x in manifest['source_bindings'] if 'document_id' in x];assert len(sources)==263
  store=d.RawInfoStore(documents=[d.RawInfoDocument.from_dict(read(x['path'])) for x in sources]);registry=d.SignalRegistry(work/'signals',candidate_root=work/'signals_candidates');history=read(work/'slow_history/manifest.json')['manifest'];meta=d.PlanMetaMemory(entries=d._rebased_history_meta_entries(d.RoundMetaEntry.from_dict(row) for row in history['fast_context']['meta_entries']))
  client=ReplayCaller(registration=d.get_model('independent-subagent'),contract=d.StageContract(read(B/'contract.json')),workspace=temp/'native-preview',ledger=d.ExternalAttemptLedger(temp/'unused.json',max_attempts=1,max_total_cost=.01),allow_external=False,environ={})
  engine=ReplayEngine(registry=registry,raw_info_store=store,discovery_cases=dev,identity_cases=identities,workspace=d.EvolutionWorkspace(work),meta_memory=meta,mining_model=d.LLMSignalMiningModel(client),update_model=d.LLMSignalUpdateModel(client),llm_signal_runner=d.StructuredLLMSignalRunner(client))
  engine.mining_model.set_request_token_budget(262144);engine._active_slow_input=read(B/'inputs/slow_input.json');engine._active_slow_memory=read(B/'inputs/slow_memory.json');engine._active_sampling_manifest=engine._active_slow_input['sampling_manifest'];engine._mining_memory_index=engine._controller_memory_index()
  baseline=read(B/'inputs/baseline.json');factory=read(B/'inputs/factory.json');context={'stable_signal_cards':[{'signal_ref':s['signal_id']+':v'+str(s['version']),'description':s['definition']['description']} for s in baseline['specs']],'capability_backlog':{'signal_need_items':factory['backlog_needs']},'prior_modality_footprints':factory['prior_modality_footprints'],'meta_info':factory['meta_memory_briefs'],'slow_method_memory':factory['slow_method_memory'],'meta_memory_disclosures':factory['meta_memory_disclosures']};engine._mining_context=MethodType(lambda self,**kw:deepcopy(context),engine)
  try:engine._run_controller_mining_axis(cycle_id=1,axis_id='surge_direction',research_axis=factory['research_axis'],dev_cases=dev,check_cases=(),labels_by_case_id={r['case_id']:dev_data['groups'][r['case_ref']] for r in dev_data['cases']})
  except MiningRequestBudgetExhausted as exc:result['replayed_stop']={'type':type(exc).__name__,'message':str(exc)}
  else:raise AssertionError('expected same pre-prepare Mining budget stop')
  result['aligned_actual_requests']=client.aligned;assert client.index==10
  blocked=client.estimates[-1];assert int(blocked['payload']['request_budget']['this_request'])==blocked['required'];assert blocked['required']>262144;assert blocked['required']<budget.remaining()
  dump('blocked-offline-native-estimate',blocked)
  # Additive exact cost on actual escaped messages, including outer quoting/escaping.
  payload=blocked['payload'];contrib={}
  for key,value in payload.items():
   component=json.dumps(key,ensure_ascii=False)+':'+json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))
   contrib[key]=len(json.dumps(component,ensure_ascii=False)[1:-1].encode())
  user_encoded=len(json.dumps(blocked['messages'][1]['content'],ensure_ascii=False)[1:-1].encode());system_encoded=len(json.dumps(blocked['messages'][0]['content'],ensure_ascii=False)[1:-1].encode());punctuation=2+max(0,len(payload)-1);assert sum(contrib.values())+punctuation==user_encoded
  outer=json_bytes(blocked['messages'])-user_encoded-system_encoded;parts={'payload_field_contributions_escaped_wire_bytes':dict(sorted(contrib.items(),key=lambda x:x[1],reverse=True)),'payload_braces_and_commas':punctuation,'system_content_escaped_bytes':system_encoded,'message_envelope_bytes':outer,'output_reservation':blocked['max_output_tokens']};assert sum(contrib.values())+punctuation+system_encoded+outer+blocked['max_output_tokens']==blocked['required'];dump('blocked-cost-decomposition',parts)
  result.update(exact_blocked_required=blocked['required'],single_limit=262144,over_single_by=blocked['required']-262144,aggregate_or_calls_exhausted=False,native_first_ten_all_messages_aligned=True,model_reserved_tokens=engine.offline_controller.model.reserved_tokens,model_reserved_calls=engine.offline_controller.model.reserved_calls,blocked_payload_top_fields=len(payload))
except BaseException as exc:result['reconstruction_failure']={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()}
finally:
 after=allfiles();assert before==after,'sealed stage changed';assert len(list((B/'exchange/inbox').glob('*.json')))==10;assert all(after[n]==h for n,h in completion['files'].items());dump('stage-after',after);result.update(stage_full_files_stable=before==after,stage_file_count=len(before),sealed_file_count=len(completion['files']),completion_sha256=before['completion.json'],business_state_sha256=before['workspace/state.json'],business_cycle_state_sha256=before['workspace/cycle_state.json']);dump('result',result)
print(json.dumps({k:v for k,v in result.items() if k not in ['wire_accounting','aligned_actual_requests']},default=str))
