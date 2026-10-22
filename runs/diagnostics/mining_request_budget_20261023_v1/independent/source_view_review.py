"""Rebuild two historical native source views and cost a scripted input-only traversal.

This never receives answers and never advances an old stage. Resource counters
are simulated explicitly for a deterministic cost preflight, not LLM evidence.
"""
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import patch
import hashlib,json,socket,sys,traceback
R=Path(__file__).resolve().parents[4];sys.path[:0]=[str(R/'src'),str(R/'scripts')]
import run_mining_locator_generalization_stage as driver
from stock_opportunity_agent.research.mining_role_model import MiningAgentRoleModel
O=Path(__file__).resolve().parent;OUT=O/sys.argv[1];OUT.mkdir(exist_ok=False)
paths=[R/'src/stock_opportunity_agent/research/mining_role_model.py',R/'src/stock_opportunity_agent/research/evolution_transport.py',R/'scripts/run_mining_taxonomy_consumer_stage.py',R/'scripts/run_mining_locator_generalization_stage.py']
def bindings():return [{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths]
before=bindings(); inputs=json.loads((R/'runs/diagnostics/mining_locator_generalization_20261023_v1/stage/inputs.json').read_text());results=[]
with driver.module.guards():
 for key in ('a','b'):
  sample=inputs[key];root=OUT/key
  try:
   c=driver.module.make_client(root,sample,{'limits':driver.module.LIMITS},input_only=True)
   controller=driver.build_controller(root,sample,c)
   model=MiningAgentRoleModel(c,identity_aliases=(sample['case_id'],sample['company_id']),max_output_tokens=2000,max_request_tokens=32768,max_total_tokens=98304,max_calls=6)
   rows=[]
   for step in range(4):
    seen=set((root/'requests').glob('*.json'))
    try:model.next_action(controller._model_view())
    except driver.module.InputCaptured:pass
    else:raise AssertionError('crossed receive boundary')
    added=set((root/'requests').glob('*.json'))-seen;assert len(added)==1
    p=added.pop();q=json.loads(p.read_text())['request'];payload=json.loads(q['messages'][1]['content']);res=driver.module.request_reservation(p);b=payload['request_budget'];assert int(b['this_request'])==res;assert b['used']==sum(x['reservation'] for x in rows)
    if step==0:action={'action':'compare_groups','concepts':[sample['concept']]}
    elif step<3:action={'action':'read_span','fact_ref':driver.visible_operand(payload,sample['concept'],'latest' if step==1 else 'comparable_prior')}
    else:action={'action':'record_deferred'}
    action['rationale']=['Deterministic source-view cost preflight, no model answer.']
    rows.append({'step':step+1,'reservation':res,'budget':b,'scripted_action':action,'source_receipts':len(payload.get('structured_read_progress',{}).get('items',[]))})
    # Simulate prior consumed logical reservations; no response/cache/receipt is fabricated.
    model.reserved_tokens+=res;model.reserved_calls+=1
    if step<3:controller._validate_action_shape(action);controller._execute(action['action'],action)
   assert rows[-1]['source_receipts']==2
   assert not list(root.rglob('inbox/*.json'))
   results.append({'sample':key,'pass':True,'requests':rows,'total':sum(x['reservation'] for x in rows),'inboxes':0})
  except BaseException as e:results.append({'sample':key,'pass':False,'type':type(e).__name__,'error':str(e),'traceback':traceback.format_exc()})
after=bindings();assert before==after
(OUT/'result.json').open('x').write(json.dumps({'at':datetime.now(timezone.utc).isoformat(),'scope':'source-only rebuilt real views with explicitly simulated logical resource counters, no receive/answers/fresh model evidence','source_bindings':before,'results':results,'external_API':0,'fresh_answers':0},indent=2,sort_keys=True)+'\n')
print(json.dumps(results,sort_keys=True))
