"""Independent native pending/cache and freeze tests in throwaway local folders only."""
import copy,hashlib,json,sys,tempfile,traceback
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,'/Users/l/Project/Recommandation/scripts')
import run_mining_taxonomy_consumer_stage as stage
from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.local_role_exchange import LocalRoleExchange
BASE=Path('/Users/l/Project/Recommandation/runs/diagnostics/mining_taxonomy_consumer_20261023_v1/independent')
BEFORE=hashlib.sha256(Path(stage.__file__).read_bytes()).hexdigest();results=[]
def check(name,fn):
 try:results.append({'name':name,'pass':True,'detail':fn()})
 except Exception as e:results.append({'name':name,'pass':False,'error_type':type(e).__name__,'error':str(e),'traceback':traceback.format_exc()})
def require(x,msg='Expected true'):
 if not x:raise AssertionError(msg)
def freeze_cases():
 got=[]
 for mode in ('content','source-added','source-removed','code-added'):
  with tempfile.TemporaryDirectory(dir=BASE/'tmp') as td:
   b=Path(td);source=b/'source.json';source.write_text('{}');old=stage.binding(source)
   stage.save(b/'preflight','result',{'source_files':[old],'code_files':[]})
   stage.save(b/'reference','prefreeze-obligations',{})
   if mode=='content':source.write_text('{"changed":true}')
   now=[stage.binding(source)]
   if mode=='source-added':
    extra=b/'extra.json';extra.write_text('{}');now.append(stage.binding(extra))
   if mode=='source-removed':now=[]
   codes=[stage.binding(source)] if mode=='code-added' else []
   with patch.object(stage,'BASE',b),patch.object(stage,'ROOT',b/'stage'),patch.object(stage,'authorities',return_value=({},now)),patch.object(stage,'code_bindings',return_value=codes):
    try:stage.prepare()
    except ValidationError as e:got.append({'mode':mode,'rejected':str(e)})
    else:raise AssertionError('Silently refroze '+mode)
   require(not (b/'stage').exists())
 return got
check('preflight_content_inventory_drift_rejects_before_root',freeze_cases)
def countcap():
 with tempfile.TemporaryDirectory(dir=BASE/'tmp') as td,stage.guards():
  b=Path(td);client=stage.make_client(b,{'concept':'SyntheticMetric'},{'limits':stage.LIMITS},input_only=True)
  errors=[]
  for i in range(7):
   try:client.complete_json(stage='mining_controller_step',system_prompt='Synthetic size control.',payload={**json.loads(next(m['content'] for m in json.loads((BASE.parent/'baseline/requests/eabb9371dcb7384e46adbf7845d178d281bd9842cbd1d8dbb1294d7ef98df95b.json').read_text())['request']['messages'] if m['role']=='user')),'index':i},allow_outcomes=True,max_output_tokens=32)
   except BaseException as e:errors.append(type(e).__name__)
   else:raise AssertionError('Crossed receive')
  require(errors==['InputCaptured']*6+['LocalRoleBudgetExhausted'],str(errors))
  require(len(list((b/'requests').glob('*.json')))==6 and not list(b.rglob('inbox/*.json')))
  return {'stops':errors,'journals':6,'inboxes':0}
check('seventh_native_position_stops_before_journal',countcap)
def pending_restore():
 with tempfile.TemporaryDirectory(dir=BASE/'tmp') as td:
  b=Path(td);root=b/'stage'
  sample={'case_id':'synthetic-fixture','case_ref':'synthetic','company_id':'synthetic-issuer','cutoff':'2024-08-02T00:00:00+00:00','label':'control','concept':'Metric','content':json.dumps({'facts':{'same-namespace':{'Metric':{'units':{'USD':[{'end':'2024-06-30','val':120},{'end':'2023-06-30','val':100}]}}}}})}
  inputs={'namespace':sample};contract={'limits':stage.LIMITS};manifest={'inputs_hash':canonical_json_hash(inputs),'contract_hash':canonical_json_hash(contract),'source_files':[],'code_files':[]};manifest['manifest_hash']=canonical_json_hash(manifest)
  for name,value in (('inputs',inputs),('contract',contract),('manifest',manifest)):stage.save(root,name,value)
  with patch.object(stage,'ROOT',root),patch.object(stage,'code_bindings',return_value=[]):
   pending=stage.advance('namespace');require(pending['state']=='pending')
   def payload(p):return json.loads(next(m['content'] for m in json.loads(Path(p['inbox_path']).read_text())['messages'] if m['role']=='user'))
   refs=payload(pending)['known_fact_refs'];require(len(refs)==2)
   actions=[{'action':'read_span','fact_ref':ref,'rationale':['Explicit offline reconstruction fixture.']} for ref in refs]+[{'action':'compare_groups','concepts':['Metric'],'rationale':['Inspect local basis.']},{'action':'record_deferred','rationale':['Controlled module boundary, no domain terminal.']}]
   journal_counts=[]
   for i,action in enumerate(actions):
    # Repeated pending advance may replay accepted caches, but adds no new receive/proof.
    same=stage.advance('namespace');require(same==pending)
    Path(pending['outbox_path']).write_text(json.dumps(action))
    LocalRoleExchange(root/'namespace/exchange',max_calls=6).submit(pending['request_hash'],agent_id='explicit-offline-reconstruction-fixture')
    pending=stage.advance('namespace');journal_counts.append(len(list((root/'namespace/requests').glob('*.json'))))
    if i<3:require(pending['state']=='pending')
   require(pending['state']=='completed_module_boundary')
   boundary=json.loads((root/'namespace/boundary.json').read_text());items=boundary['view']['structured_read_progress']['items']
   require({x['fact_ref'] for x in items}==set(refs) and [x['read_count'] for x in items]==[1,1])
   require(not boundary['native_domain_terminal_executed'])
   require('record_deferred' not in [x['action'] for x in boundary['ledger']['entries']])
   require(boundary['view']['last_action_result']['action']=='compare_groups')
   with patch.object(stage,'make_client',side_effect=AssertionError('terminal reentry')):require(stage.advance('namespace')==pending)
   reservations=[stage.request_reservation(p) for p in (root/'namespace/requests').glob('*.json')]
   beforecompletion=copy.deepcopy(pending)
   # Test the claimed terminal seal, without altering any original artifact.
   terminalpath=root/'namespace/completion.json';tampered=json.loads(terminalpath.read_text());tampered['state']='synthetic-corrupted-terminal-state';terminalpath.write_text(json.dumps(tampered))
   try:returned=stage.advance('namespace')
   except Exception as exc:tamper={'rejected':True,'type':type(exc).__name__}
   else:tamper={'rejected':False,'returned_state':returned.get('state')}
   result={'physical_offline_receipts':4,'journal_counts':journal_counts,'read_counts':[x['read_count'] for x in items],'native_terminal_executed':False,'reservations':reservations,'aggregate':sum(reservations),'completion_metadata_tamper':tamper}
   # Preserve this sub-result even if the terminal-integrity expectation fails.
   assert not (BASE/'pending-final-reconstruction-detail.json').exists()
   (BASE/'pending-final-reconstruction-detail.json').write_text(json.dumps(result,indent=2)+'\n')
   require(tamper['rejected'],'Terminal completion metadata corruption was accepted')
   return result
check('pending_cache_reconstruction_and_terminal_integrity',pending_restore)
AFTER=hashlib.sha256(Path(stage.__file__).read_bytes()).hexdigest()
report={'scope':'All stage writes under independent/tmp, synthetic local raw actions only,0fresh models/business labels/API/original edits.','checks':results,'passed':sum(x['pass'] for x in results),'total':len(results),'stage_sha_before':BEFORE,'stage_sha_after':AFTER,'source_drift':BEFORE!=AFTER}
assert not (BASE/'stage-final-recheck-results.json').exists()
(BASE/'stage-final-recheck-results.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
