"""Native reflect/parser/correction/salvage wiring fixtures, no model/role answers."""
from pathlib import Path
from copy import deepcopy
from contextlib import nullcontext
from importlib.machinery import SourceFileLoader
import importlib.util,sys,tempfile,json,hashlib
import run_reviewed_posthoc_stage as current
from tests.test_evolution_state_patch import PatchCaller,patch
from tests.test_evolution_reflection_memory import authored
from stock_opportunity_agent.research.evolution_output_validation import _blind_prediction_from_role
from stock_opportunity_agent.research.evolution_core import GroundTruth
from scripts.replay_incremental_reflection_memory import deny_network
OUT=Path(__file__).resolve().parent
oldpath=OUT/'original-fallback-observer-script.py.txt'
loader=SourceFileLoader('independent_old_posthoc_observer',str(oldpath));spec=importlib.util.spec_from_loader(loader.name,loader);old=importlib.util.module_from_spec(spec);sys.modules[loader.name]=old;loader.exec_module(old)
prediction=_blind_prediction_from_role({'candidate_judgment':'possible','magnitude':'2-3x','confidence':{'level':'low'},'session_id':'anonymous','key_reasons':['Source-backed operating evidence supports a possible repricing.'],'uncertainties':['Operating recovery remains uncertain.']})
saved={'company_id':'cik_00000042','prediction_time':'2025-01-15T00:00:00+00:00','prediction':prediction.to_dict(),'final_context':{}}
truth=GroundTruth(1.1) # Explicit synthetic fixture, never used for formal sample.
inputs={'identity':{'identity_aliases':[],'ticker':'DEMO'}}
contract={'max_local_calls':8,'limits':{'max_structured_corrections':1,'max_request_tokens':131072,'structured_reasoning_token_reserve':0}}
results=[]
def run(module,variant):
 capture={'raw_fixture_responses':[]}
 def initial(call):
  if variant=='honest_empty':value={'reflection_items':[],'selected_reflection_refs':[],'no_findings_reason':'The synthetic limited packet provides no supported additional lesson.'}
  else:
   source=call['payload']['source_catalog'][0];bad=authored(source,category='misleading_signals');bad.update(kind='fact',brief='The prediction acknowledged but underweighted the negative fundamental signals.',detail='The source-backed guidance acceleration and financing actions were sufficient to identify the outcome class and scale.')
   good=deepcopy(bad);good.update(brief='The saved prediction was positive and the revealed outcome was negative.',detail='The saved prediction was positive and the revealed outcome was negative.')
   value={'reflection_items':[bad,good] if variant=='partial_valid' else [bad],'selected_reflection_refs':[],'no_findings_reason':None};capture['good_sibling']=good
  capture['raw_fixture_responses'].append(deepcopy(value));return value
 def correction(call):
  value=patch(call['payload']['output_patch_contract'],{'op':'replace','path':'reflection_items[0].brief','value':'The prediction acknowledged but underweighted the negative fundamental signals. Keep this interpretation.'})
  capture['raw_fixture_responses'].append(deepcopy(value));return value
 def factory(**kwargs):
  caller=PatchCaller(initial,correction);caller.max_structured_corrections=1;caller.request_hash_trace=[];caller.on_progress=kwargs.get('on_progress');caller.anonymous_case=lambda **_:nullcontext();return caller
 original_client=module.StructuredRoleClient;original_reflect=module.LLMBlindPredictor.reflect
 def observed_reflect(self,*args,**kwargs):
  step=original_reflect(self,*args,**kwargs);capture['native_return_value']=step.value.to_dict();return step
 module.StructuredRoleClient=factory;module.LLMBlindPredictor.reflect=observed_reflect
 try:
  with tempfile.TemporaryDirectory(prefix='independent-posthoc-fallback-') as td:
   root=Path(td);result=module._execute(root,'synthetic-manifest',inputs,contract,saved,truth)
   assert result['status']=='feedback_persisted_requires_independent_review',result
   feedback=json.loads((root/'feedback.json').read_text());assert feedback['value']==capture['native_return_value']
   before=module._files(root);restored=module._completed_restore(root,'synthetic-manifest',contract);assert restored['restored_without_execution'] and before==module._files(root)
   capture.update(observer_version='old' if module is old else 'current',variant=variant,feedback=feedback,result=result,exact_native_value_persisted=True,completed_restore_without_writes=True)
 finally:module.StructuredRoleClient=original_client;module.LLMBlindPredictor.reflect=original_reflect
 value=feedback['value'];items=value.get('reflection_items',[])
 if variant=='partial_valid':
  assert len(items)==1 and value.get('no_findings_reason') is None
  assert all(items[0][k]==v for k,v in capture['good_sibling'].items())
 elif variant=='all_invalid':assert not items and value['no_findings_reason'].startswith('reflection_items_all_invalid_salvaged:')
 else:assert not items and value['no_findings_reason'].startswith('The synthetic limited packet')
 if module is old:assert feedback['native_validation_fallback'] is False
 elif variant=='honest_empty':assert feedback['native_validation_fallback'] is False and not feedback['native_validation_fallback_events']
 else:
  assert feedback['native_validation_fallback'] is True
  assert any(e['event_type']=='structured_validation_fallback_applied' for e in feedback['native_validation_fallback_events'])
  assert feedback['native_validation_fallback_events']==[e for e in feedback['validation_events'] if e['event_type'] in {'structured_validation_fallback_applied','deterministic_fallback_promoted','posthoc_reflection_validation_failed'}]
 results.append(capture)
with deny_network() as net:
 for module in [old,current]:
  for variant in ['partial_valid','all_invalid','honest_empty']:run(module,variant)
for variant in ['partial_valid','all_invalid','honest_empty']:
 before,after=[r for r in results if r['variant']==variant]
 assert before['native_return_value']==after['native_return_value'];assert before['raw_fixture_responses']==after['raw_fixture_responses']
out={'scope':'Native LLMBlindPredictor.reflect, production parser/correction/salvage and harness exact persistence/restore. Scripted caller generates explicit synthetic test responses, no independent role/model execution, no formal parent/labels/root mutation. Complete request/receipt behavior is separately tested; this fixture dispatches zero requests.','all_passed':True,'variants':results,'native_value_and_scripted_responses_identical_old_vs_current':True,'network_attempts':net['network_attempts'],'bindings':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [oldpath,Path(current.__file__),Path('spec/scripts/run_reviewed_posthoc_stage.md'),Path('src/stock_opportunity_agent/research/evolution_plan_roles.py'),Path('src/stock_opportunity_agent/research/evolution_output_validation.py')]}}
p=OUT/'fallback-observer-results.json';assert not p.exists();p.write_text(json.dumps(out,indent=2,ensure_ascii=False)+'\n');print(json.dumps({'all_passed':True,'runs':len(results),'old_fallback_flags':[r['feedback']['native_validation_fallback'] for r in results if r['observer_version']=='old'],'current_fallback_flags':[r['feedback']['native_validation_fallback'] for r in results if r['observer_version']=='current'],'current_events':[[e['event_type'] for e in r['feedback']['native_validation_fallback_events']] for r in results if r['observer_version']=='current']},indent=2))
