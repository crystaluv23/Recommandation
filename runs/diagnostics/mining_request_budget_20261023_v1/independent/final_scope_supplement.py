"""Focused final review after narrowing transport change to the observed Mining family."""
from pathlib import Path
exec(Path(__file__).with_name('native_review_v3.py').read_text().split("with patch.object(socket,")[0])
from dataclasses import replace
import subprocess
import run_mining_taxonomy_consumer_stage as driver
from stock_opportunity_agent.research.mining_role_model import MiningRequestBudgetExhausted
from stock_opportunity_agent.research.evolution_core import CandidateExecutionRejected
from stock_opportunity_agent.research.evolution_transport import _WIRE_AUDITED_PROVIDERS
PRODUCT=[R/p for p in ('src/stock_opportunity_agent/research/mining_role_model.py','src/stock_opportunity_agent/research/evolution_transport.py','src/stock_opportunity_agent/research/signal_evolution.py','scripts/run_mining_taxonomy_consumer_stage.py')]
def binds():return [{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in PRODUCT]
before=binds();oldreview=O/'independent-final-review-v2.json';oldreview_hash=hashlib.sha256(oldreview.read_bytes()).hexdigest()
settings=dict(max_request_tokens=32768,max_total_tokens=98304,max_calls=6,max_output_tokens=2000)
def constructor_boundary():
 c=client('constructor');reg=get_model('independent-subagent');assert reg.provider=='local' and reg.provider not in _WIRE_AUDITED_PROVIDERS
 rejected=[]
 for name,fn in (
  ('independent-external',lambda:StructuredRoleClient(registration=reg,contract=c.contract,workspace=OUT/'rejected-external',ledger=c.ledger,allow_external=True)),
  ('remote-local-exchange',lambda:StructuredRoleClient(registration=get_model('deepseek-v4-flash'),contract=c.contract,workspace=OUT/'rejected-remote',ledger=c.ledger,local_role_exchange=c.local_role_exchange)),
  ('independent-remote-provider',lambda:replace(reg,provider='remote'))):
  try:fn()
  except ValidationError:rejected.append(name)
  else:raise AssertionError('forbidden registration admitted: '+name)
 return {'legal_local_provider':reg.provider,'not_wire_audited':True,'rejected':rejected}
def exact_native_equivalence():
 c=client('exact');m=MiningAgentRoleModel(c,**settings);v=view();p=pending(m,v);q=request(c,p);prior=[]
 for f in (O/'native-v2/exact/requests').glob('*.json'):
  candidate=json.loads(f.read_text())['request']
  if budget_fields(candidate)['used']==0:prior.append(candidate)
 assert len(prior)==1 and q==prior[0]
 assert int(budget_fields(q)['this_request'])==reservation(q)
 valid(c,m,v,p);m2=MiningAgentRoleModel(c,**settings);m2.next_action(v)
 assert len(list(c.local_role_exchange.root.glob('receipts/*.json')))==1
 return {'full_native_request_identical_to_pre_removal':True,'reservation':reservation(q),'physical_receipts_after_replay':1}
def wrapper_parity():
 root=OUT/'wrapper';c=driver.make_client(root,{'concept':'Metric'},{'limits':driver.LIMITS},input_only=True);m=MiningAgentRoleModel(c,**settings)
 try:m.next_action(view())
 except driver.InputCaptured:pass
 else:raise AssertionError('crossed wrapper input-only boundary')
 files=list((root/'requests').glob('*.json'));assert len(files)==1
 q=json.loads(files[0].read_text())['request'];b=budget_fields(q);assert int(b['this_request'])==reservation(q);assert driver.ENVELOPE.format(concept='Metric') in q['messages'][0]['content'];assert not list(root.rglob('inbox/*.json'))
 return {'reservation':reservation(q),'exact_budget_envelope_parity':True,'inboxes':0}
def native_no_progress():
 c=client('no-progress');m=MiningAgentRoleModel(c,**settings)
 with c.correction_chain(stage='mining_controller_step'):
  pending(m,view())
  try:m.next_action(view())
  except CandidateExecutionRejected:pass
  else:raise AssertionError('guard did not reject')
 assert m.reserved_calls==0 and m.reserved_tokens==0
 return {'reserved_calls':0,'reserved_tokens':0,'receipts':0}
def stop_controlflow():
 c=client('stop');m=MiningAgentRoleModel(c,max_request_tokens=1)
 try:m.next_action(view())
 except MiningRequestBudgetExhausted as e:assert isinstance(e,EvolutionControlFlow) and not isinstance(e,ValidationError)
 else:raise AssertionError('budget stop missing')
 return {'inboxes':len(list(c.local_role_exchange.root.glob('inbox/*.json'))),'control_flow':True}
with patch.object(socket,'create_connection',side_effect=AssertionError('network forbidden')),patch.object(socket.socket,'connect',side_effect=AssertionError('network forbidden')):
 for name,fn in [('constructor-boundary',constructor_boundary),('native-exact-before-after-equivalent',exact_native_equivalence),('wrapper-envelope-parity',wrapper_parity),('native-no-progress-no-debt',native_no_progress),('hard-stop-controlflow',stop_controlflow)]:record(name,fn)
after=binds();assert before==after
transport=R/'src/stock_opportunity_agent/research/evolution_transport.py';transport_head=subprocess.check_output(['git','show','HEAD:src/stock_opportunity_agent/research/evolution_transport.py'],cwd=R);assert transport.read_bytes()==transport_head
assert hashlib.sha256(oldreview.read_bytes()).hexdigest()==oldreview_hash
final={'source_bindings':before,'results':RESULT,'pass':all(r['pass'] for r in RESULT),'transport_source_matches_HEAD':True,'transport_change_claim':'withdrawn: remote-registration plus local-exchange mismatch is unreachable under valid current registrations; no transport defect closure claimed','retained_fix':'Mining request-budget observability/accounting plus diagnostic wrapper ENVELOPE estimator parity','prior_final_v2_preserved_sha256':oldreview_hash,'prior_scope_evidence':'17 native groups and2 source-only preflights remain historical local evidence. Current native exact request is identical across transport removal; no need repeat extraction.','external_API':0,'fresh_answers':0,'old_stage_advancement':0,'remaining':'Fresh planning and module endpoints remain untested; no new execution authorization.'}
save('final-scope-supplement',final);print(json.dumps({'pass':final['pass'],'results':RESULT,'source_bindings':before},sort_keys=True))
