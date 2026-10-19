import json,tempfile,hashlib,copy,importlib.util
from pathlib import Path
from dataclasses import asdict
from types import SimpleNamespace
from scripts.replay_incremental_reflection_memory import deny_network
from stock_opportunity_agent.llm import get_model
from stock_opportunity_agent.research.evolution_transport import StructuredRoleClient,ExternalAttemptLedger,ExternalRequestPending
from stock_opportunity_agent.research.local_role_exchange import LocalRoleExchange,LocalRoleRequestPending
from stock_opportunity_agent.research.evolution_plan_roles import _DocumentChannelCaller
from stock_opportunity_agent.research.evolution_core import AgentUsage,RuntimeLimits,_consume_model_step,RuntimeBudgetExceeded
from stock_opportunity_agent.research.evolution_output_validation import _complete_parsed_role
from stock_opportunity_agent.models import StructuredValidationError,ValidationIssue
from stock_opportunity_agent.research.evolution_signal_roles import StructuredLLMSignalRunner
from tests.test_signal_correction_reservation import SignalCorrectionReservationTests
from tests.test_same_request_guard import _client as remote_client
repo=Path('/Users/l/Project/Recommandation')
# Reuse the exact fixed pre-repair native DocumentChannel fixture; never overwrite its old result.
old_path=repo/'runs/diagnostics/runtime_termination_boundary_20261019_v1/cache-budget/probe.py'
spec=importlib.util.spec_from_file_location('frozen_original_cache_budget_probe',old_path);old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
def filehashes(root):return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}
class FixtureExchange(LocalRoleExchange):
 def __init__(self,root,answer):super().__init__(root,max_calls=8);self.answer=answer
 def receive(self,request,**kwargs):
  try:return super().receive(request,**kwargs)
  except LocalRoleRequestPending as e:
   # Synthetic unit fixture only. Not a native-role answer or source assertion.
   raw=Path(e.pending['outbox_path']);raw.parent.mkdir(parents=True,exist_ok=True);raw.write_text(json.dumps(self.answer(json.loads(request['messages'][-1]['content']))))
   self.submit(e.pending['request_hash'],agent_id='synthetic-independent-accounting-fixture-not-model')
   return super().receive(request,**kwargs)
def client(root,answer):return StructuredRoleClient(registration=get_model('independent-subagent'),contract=SimpleNamespace(contract_hash='d'*64,limits={'max_local_role_calls':8,'max_structured_corrections':1}),workspace=root,local_role_exchange=FixtureExchange(root/'exchange',answer),ledger=ExternalAttemptLedger(root/'unused.json',max_attempts=1,max_total_cost=.01),allow_external=False,environ={})
def consumption(usage):
 out={}
 for start in (21,22,23):
  try:out[str(start)]={'accepted':True,'usage':asdict(_consume_model_step(AgentUsage(llm_calls=start),usage,RuntimeLimits(max_llm_calls=24)))}
  except RuntimeBudgetExceeded as e:out[str(start)]={'accepted':False,'error':str(e)}
 return out
def replay(name,run):
 with tempfile.TemporaryDirectory(prefix='independent-native-budget-') as td:
  root=Path(td);fresh=run(root);before=filehashes(root);warm=run(root);after=filehashes(root)
  assert fresh==warm,(name,fresh,warm)
  assert before==after
  assert fresh['usage']['llm_calls']==2
  assert len(list((root/'exchange/inbox').glob('*.json')))==2
  assert len(list((root/'exchange/receipts').glob('*.json')))==2
  return {'name':name,'fresh':fresh,'warm':warm,'all_original_artifact_bytes_unchanged':True,'new_inbox':0,'new_receipts':0,'total_fixture_receipts':2}
with deny_network() as network:
 original_fixed=old.main()
 assert original_fixed['first']['usage']==original_fixed['cached']['usage']=={'llm_calls':2,'tokens':1013,'cost':0.0}
 assert not original_fixed['first']['consumption_after_23_calls']['accepted'] and not original_fixed['cached']['consumption_after_23_calls']['accepted']
 original_fixed.pop('observed_limitation')
 def correction(root):
  c=client(root,lambda payload:{'answer':bool(payload.get('validation_feedback'))})
  def parser(value):
   if value.get('answer') is not True:raise StructuredValidationError((ValidationIssue(code='synthetic_wrong_flag',paths=('answer',),message='Synthetic fixture requires true.',allowed_repairs=('replace',)),))
   return value
  value,usage=_complete_parsed_role(c,stage='synthetic_independent_correction',system_prompt='Return fixture JSON.',payload={'fixture':True},parser=parser,allow_outcomes=False,max_output_tokens=200,stable_correction_prefix=True)
  return {'value':value,'usage':asdict(usage),'core_budget':consumption(usage),'request_hashes':c.request_hash_trace}
 correction_result=replay('native_typed_correction',correction)
 fixture=SignalCorrectionReservationTests();fixture.setUp()
 def signal(root):
  def answer(payload):return {'results':[fixture.row({'payload':payload},row,invalid='validation_feedback' not in payload and row['signal_ref']=='pending:v1') for row in payload['signals']]}
  c=client(root,answer);runner=StructuredLLMSignalRunner(c);results,usage=runner.execute_many(fixture.inputs,fixture.as_of)
  assert all(value.execution_status.value=='success' for value in results.values())
  return {'results':{ref:value.to_dict() for ref,value in results.items()},'usage':asdict(usage),'core_budget':consumption(usage),'request_hashes':c.request_hash_trace}
 signal_result=replay('native_signal_batch_typed_correction',signal)
 with tempfile.TemporaryDirectory(prefix='independent-remote-cache-control-') as td:
  root=Path(td);c=remote_client(root);kwargs={'stage':'synthetic_remote_cache_control','system_prompt':'Return fixture JSON.','payload':{'fixture':True},'allow_outcomes':False,'max_output_tokens':200}
  try:c.complete_json(**kwargs);raise AssertionError('remote must await approval')
  except ExternalRequestPending as e:
   request_hash=e.request_hash
  c.cache.store(request_hash,{'json_output':{'fixture_done':True},'usage':{'accounting_tokens':456,'cost':0},'model':'synthetic-remote-cache-fixture'})
  before=filehashes(root);value,usage=c.complete_json(**kwargs);assert usage==AgentUsage(llm_calls=0,tokens=456,cost=0.0);assert value=={'fixture_done':True};assert before==filehashes(root)
  remote={'actual_StructuredRoleClient_cached_usage':asdict(usage),'value':value,'no_attempt_or_network':True,'artifact_bytes_unchanged':True}
paths=[repo/'src/stock_opportunity_agent/research/evolution_transport.py',repo/'spec/src/stock_opportunity_agent/research/evolution_transport.md',old_path,repo/'runs/diagnostics/runtime_termination_boundary_20261019_v1/cache-budget/result.json']
out={'scope':'Synthetic native transport/typed-correction/Signal-batch accounting only; no real independent agent or research answer. Logical calls are not new physical calls, tokens are conservative reservations, actual host cost/tokens unknown.','fixed_original_document_channel':original_fixed,'typed_correction':correction_result,'signal_batch':signal_result,'remote_cache_control':remote,'network_attempts':network['network_attempts'],'actual_independent_roles':0,'host_actual_tokens':None,'host_actual_cost':None,'bindings':{str(p.relative_to(repo)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}
Path('/tmp/independent-native-cache-budget-results.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k not in ('signal_batch','typed_correction')},indent=2));print(correction_result['fresh']['usage'],signal_result['fresh']['usage'])
