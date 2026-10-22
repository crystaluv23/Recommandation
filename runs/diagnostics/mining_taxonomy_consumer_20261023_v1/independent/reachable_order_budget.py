"""Capture the real compare-first path at unchanged native budget, without inbox/answer."""
import hashlib,json,sys
from pathlib import Path
sys.path.insert(0,'/Users/l/Project/Recommandation/scripts')
import run_mining_taxonomy_consumer_stage as stage
BASE=Path('/Users/l/Project/Recommandation/runs/diagnostics/mining_taxonomy_consumer_20261023_v1')
DEST=BASE/'independent/reachable-order-capture';assert not DEST.exists();DEST.mkdir()
ref=json.loads((BASE/'reference/source-reference.json').read_text())['positive_source_control']
inv=json.loads(stage.INVENTORY.read_text())
sample={'case_id':'cik_0000800457:20250731','case_ref':'case-008','company_id':'cik_0000800457','cutoff':ref['case_cutoff'],'label':ref['opaque_group'],'concept':ref['allowed_measurement_scope']['concept'],'snapshot':inv['sources']['reviewed_snapshot']}
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
before=sha(stage.__file__);results=[]
with stage.guards():
 for order in ('current-then-prior','prior-then-current'):
  root=DEST/order;root.mkdir();client=stage.make_client(root,sample,{'limits':stage.LIMITS},input_only=True)
  c=stage.build_controller(root,sample,client)
  facts=sorted((f for f in c._facts.values() if f.concept==sample['concept']),key=lambda f:f.period['end'],reverse=order=='current-then-prior')
  assert len(facts)==2 and all(f.content_hash==ref['content_sha256'] for f in facts)
  actions=[{'action':'compare_groups','concepts':[sample['concept']],'rationale':['Controlled compare-first reachability, not a model answer.']}]
  actions += [{'action':'read_span','fact_ref':f.fact_ref,'rationale':['Controlled read of comparison-selected source operand.']} for f in facts]
  actions += [{'action':'record_deferred','rationale':['Controlled module boundary only.']}]
  steps=[];blocked=False
  for index,action in enumerate(actions,1):
   view=c._model_view();stage.save(root,f'canonical-view-{index}',view)
   try:c.model.next_action(view)
   except stage.InputCaptured:status='captured_before_receive'
   except stage.LocalRoleBudgetExhausted as e:status='budget_blocked';blocked=True;error=str(e)
   else:raise AssertionError('Crossed model receive')
   current=list((root/'requests').glob('*.json'));total=sum(stage.request_reservation(p) for p in current)
   steps.append({'position':index,'requested_next_action':action['action'],'status':status,'journals':len(current),'aggregate':total,'remaining':stage.LIMITS['max_case_tokens']-total,**({'error':error} if blocked else {})})
   if blocked:break
   if index<len(actions):c._validate_action_shape(action);c._execute(action['action'],action)
  records=[]
  for p in sorted((root/'requests').glob('*.json')):
   request=json.loads(p.read_text())['request'];wire='\n'.join(m['content'] for m in request['messages'])
   assert '0000800457' not in wire
   records.append({'path':str(p),'sha256':sha(p),'reservation':stage.request_reservation(p)})
  page=c._model_view().get('structured_read_progress',{})
  results.append({'read_order':order,'blocked':blocked,'steps':steps,'requests':records,'aggregate':sum(r['reservation'] for r in records),'headroom':stage.LIMITS['max_case_tokens']-sum(r['reservation'] for r in records),'whole_receipts_at_stop':len(page.get('items',())),'selected_source_hash':facts[0].content_hash,'inboxes':len(list(root.rglob('inbox/*.json'))),'fresh_model_answers':0})
report={'schema':'independent-reachable-order-native-budget-v1','scope':'Two zero-inbox controlled path variants on the actual1780 source store; no fresh model response, source append or budget expansion.','stage_sha_before':before,'stage_sha_after':sha(stage.__file__),'limits':stage.LIMITS,'variants':results,'all_fit':all(not r['blocked'] and r['whole_receipts_at_stop']==2 for r in results),'qualification':'This proves the selected compare→two reads→stop request envelopes fit. It does not guarantee arbitrary extra actions/corrections fit, or prove autonomous source/semantic behavior. Root original controlled read→read→compare path is separate evidence.'}
p=BASE/'independent/reachable-order-budget-addendum.json'
with p.open('x') as f:f.write(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'all_fit':report['all_fit'],'variants':[{'order':r['read_order'],'aggregate':r['aggregate'],'headroom':r['headroom'],'blocked':r['blocked'],'inboxes':r['inboxes']} for r in results],'source_drift':report['stage_sha_before']!=report['stage_sha_after']},indent=2))
