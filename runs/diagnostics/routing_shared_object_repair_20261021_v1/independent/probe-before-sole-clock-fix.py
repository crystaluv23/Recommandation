"""Offline helper/native-selector controls from independently frozen cases; no models."""
import sys
sys.dont_write_bytecode=True
from pathlib import Path
from datetime import datetime
from contextlib import ExitStack
from copy import deepcopy
import argparse,hashlib,importlib.util,json,socket,tempfile
from unittest.mock import patch
from stock_opportunity_agent.research import evolution_plan_roles as roles
from stock_opportunity_agent.research import evolution_research_validation as current
from stock_opportunity_agent.research.evolution_core import ResearchState,RuntimeBudgetExceeded
from stock_opportunity_agent.llm.agent import AgentUsage
from stock_opportunity_agent.signal_library import SignalSpec,FrozenSignalRegistry,SignalRegistry,SignalExecutor,default_deterministic_signal_functions
from stock_opportunity_agent.data.raw_info import RawInfoStore
from stock_opportunity_agent.cases.label_store import LabelStore
R=Path('/Users/l/Project/Recommandation');O=R/'runs/diagnostics/routing_shared_object_repair_20261021_v1/independent';S=R/'runs/diagnostics/gpre_native_routing_20261021_v1/stage'
def read(p):return json.loads(p.read_text())
def h(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def b(p):return {'path':str(p),'sha256':h(p),'bytes':p.stat().st_size}
p=argparse.ArgumentParser();p.add_argument('--mode',choices=('baseline','candidate'),required=True);p.add_argument('--expected-sha');p.add_argument('--typed-head-only',action='store_true');p.add_argument('--sole-head-only',action='store_true');p.add_argument('--source-file',type=Path);p.add_argument('--output-prefix',default='');args=p.parse_args()
casefile=O/'frozen-cases-v3.json';assert h(casefile)=='6de09ea83f854dd541a65e1927e832e3a3b14dbe75b423c3020a2cf65790a258';cases=read(casefile)
if args.mode=='baseline':
 path=args.source_file or O/'original-9ac20df4-validation.py';name='stock_opportunity_agent.research._independent_saved_validation'
 if args.source_file:assert args.expected_sha and h(path)==args.expected_sha
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module);fn=module._shared_distinctive_phrase
else:
 module=current;path=Path(current.__file__);assert args.expected_sha and h(path)==args.expected_sha;fn=current._shared_distinctive_phrase
assert Path(fn.__code__.co_filename).resolve()==path.resolve()
raw=read(S/'exchange/outbox/6dd836684a001330e31e78797bfbb439f2d751fc1aa79a6364224836029aabf8.txt');ctx=read(S/'native-select-context.json');state0=ctx['research_state'];group=read(S/'inputs.json')['registry_group'];specs=[]
for ref in group['refs']:
 sid,ver=ref.split(':');paths=[Path(x['path']) for x in group['definition_bindings'] if x['path'].endswith('/'+sid+'/versions/'+ver+'/spec.json')];assert len(paths)==1;specs.append(SignalSpec.from_dict(read(paths[0])))
registry=FrozenSignalRegistry(group['version'],group['registry_hash'],tuple(specs),{})
trips=[]
def forbidden(*a,**k):trips.append('forbidden');raise AssertionError('forbidden effect')
class OfflineScriptedRoleCaller:
 max_structured_corrections=1
 def __init__(self,first,repair=None):self.first=first;self.repair=repair;self.calls=[];self.responses=0
 def complete_json(self,**kwargs):
  self.calls.append(deepcopy(kwargs))
  if len(self.calls)==1:self.responses+=1;return deepcopy(self.first),AgentUsage(llm_calls=1,tokens=5,cost=0.0)
  if self.repair is None:raise RuntimeBudgetExceeded('offline synthetic correction response blocked; inspect native fallback, not a model')
  contract=kwargs['payload']['output_patch_contract'];self.responses+=1
  return {'base_hash':contract['base_hash'],'operations':[{'op':'replace','path':'selections[1].selection_reason','value':self.repair}]},AgentUsage(llm_calls=1,tokens=5,cost=0.0)
def run(case,repair=None):
 needs=list(ctx['information_needs']);needs[1]=case['target_need'];payload=deepcopy(raw);payload['selections'][1].update(selection_reason=case['selection_reason'],residual_need=case['residual_need']);state=deepcopy(state0);state['next_information_needs']=needs
 caller=OfflineScriptedRoleCaller(payload,repair);agent=roles.LLMSignalRetrievalAgent(caller);agent.set_evaluation_context(datetime.fromisoformat('2025-05-30T00:00:00+00:00'));agent.set_deterministic_functions(default_deterministic_signal_functions())
 outcome=None;error=None
 try:outcome=agent.select(tuple(needs),registry,{},research_state=ResearchState.from_dict(state),eligible_signal_refs=tuple(group['refs']),prior_context_tags=())
 except Exception as e:error={'type':type(e).__name__,'message':str(e)}
 selected=[x.to_dict() for x in outcome.value] if outcome else[];order=next((x for x in selected if x['signal_ref']=='order_confirmation_disclosed:v3'),None)
 direct=len(caller.calls)==1 and order is not None and order.get('reason_code')=='answer_need' and order.get('answer_scope')=='partial' and order.get('selection_reason')==case['selection_reason'] and order.get('residual_need')==case['residual_need']
 sibling_ok=all(next((x for x in selected if x['signal_ref']==row['signal_ref']),None)=={k:v for k,v in row.items() if v is not None} for row in (raw['selections'][0],raw['selections'][2])) if selected else False
 feedback=[c['payload'].get('validation_feedback') for c in caller.calls[1:]]
 return {'direct_first_answer':direct,'calls':len(caller.calls),'offline_returned_answers':caller.responses,'error':error,'selected':selected,'siblings_exact':sibling_ok,'feedback':feedback,'typed_contracts':[c['payload'].get('output_patch_contract') for c in caller.calls[1:]]}
results=[];extras=[]
with ExitStack() as st:
 for owner,method in ((socket,'socket'),(socket,'create_connection'),(LabelStore,'__init__'),(LabelStore,'load'),(LabelStore,'record'),(LabelStore,'ground_truth'),(RawInfoStore,'__init__'),(RawInfoStore,'append'),(SignalExecutor,'execute_batch'),(SignalExecutor,'prepare_inputs'),(SignalRegistry,'freeze'),(SignalRegistry,'install_catalog')):st.enter_context(patch.object(owner,method,forbidden))
 st.enter_context(patch.object(roles,'_shared_distinctive_phrase',fn))
 for case in ([] if (args.typed_head_only or args.sole_head_only) else cases['cases']):
  observed=fn(case['selection_reason'],case['residual_need'],target_need=case['target_need']);helper_expect=case['helper_conflict_expectation'];helper_ok=helper_expect=='not_asserted' or ((observed is None)==(helper_expect=='none'))
  native=run(case);native_ok=native['direct_first_answer']==case['expected_direct_partial'];safe_siblings=native['siblings_exact']
  results.append({'case_id':case['case_id'],'expected_direct_partial':case['expected_direct_partial'],'helper_shared_phrase':observed,'helper_expected':helper_expect,'helper_ok':helper_ok,'native_ok':native_ok,'native':native,'pass':helper_ok and native_ok and safe_siblings})
 # Native typed repair or independent two-answer retained-head attack.
 source=cases['cases'][0];bad=deepcopy(source)
 if args.typed_head_only or args.sole_head_only:
  if args.sole_head_only:
   attack=read(O/'sole-retained-head-expectation.json');bad['target_need']=attack['target_need'];bad['selection_reason']=attack['first_reason'];bad['residual_need']=attack['residual_need'];corrected=attack['second_typed_reason']
  else:
   bad['selection_reason']+=' Also measures premiums.'
   bad['residual_need']=bad['residual_need'].replace('realized premiums','premiums')
   corrected=source['selection_reason'].replace('Ultra-High Protein ','')+' Also measures premiums.'
  repair=run(bad,corrected);repaired=next((x for x in repair['selected'] if x['signal_ref']=='order_confirmation_disclosed:v3'),{})
  extras.append({'name':'sole_head_typed_remove_object_still_overclaims' if args.sole_head_only else 'typed_remove_shared_object_must_not_rescue_retained_premium','first_reason':bad['selection_reason'],'residual':bad['residual_need'],'second_author_typed_reason':corrected,'result':repair,'pass':repair['calls']>=2 and repaired.get('reason_code')!='answer_need' and repair['siblings_exact']})
 else:
  bad['selection_reason']+=' Also measures sales volumes.'
  repair=run(bad,source['selection_reason']);repaired=next((x for x in repair['selected'] if x['signal_ref']=='order_confirmation_disclosed:v3'),{})
  extras.append({'name':'typed_replace_reason_complete_reparse','result':repair,'pass':repair['calls']==2 and repair['offline_returned_answers']==2 and repaired.get('reason_code')=='answer_need' and repaired.get('selection_reason')==source['selection_reason'] and repaired.get('residual_need')==source['residual_need'] and repair['siblings_exact']})
 # Persist and reread actual typed to_dict output outside all source/real stores.
 with tempfile.TemporaryDirectory(prefix='independent-routing-typed-') as temp:
  f=Path(temp)/'typed-selection.json';f.write_text(json.dumps({'selections':repair['selected']},sort_keys=True));assert read(f)['selections']==repair['selected']
 assert not trips
out={'mode':args.mode,'helper_module':module.__name__,'helper_module_file':str(module.__file__),'helper_code_filename':fn.__code__.co_filename,'helper_module_file_binding':b(path),'active_parser':b(Path(roles.__file__)),'current_helper_file_not_old_isolation':b(Path(current.__file__)),'cases':b(casefile),'results':results,'extras':extras,'passed':sum(r['pass'] for r in results),'case_count':len(results),'extra_passed':sum(x['pass'] for x in extras),'forbidden_calls':trips,'limits':'Offline authors scripted, not fresh. Old9ac helper is isolated module with exactfile/hash and nativecurrentparser identical except helperbinding; no productionStore orSignalcalculation.'}
name=('baseline-9ac-typed-head-results.json' if args.mode=='baseline' else 'candidate-typed-head-results.json') if args.typed_head_only else ('baseline-9ac-results.json' if args.mode=='baseline' else 'candidate-results.json');name=(('sole-head-'+name) if args.sole_head_only else name);name=args.output_prefix+name;dest=O/name;assert not dest.exists();dest.write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+'\n');print(json.dumps({'mode':args.mode,'passed':out['passed'],'total':len(results),'extras':out['extra_passed'],'result':b(dest),'failures':[{'case_id':r['case_id'],'helper':r['helper_shared_phrase'],'helper_ok':r['helper_ok'],'native_ok':r['native_ok'],'native_error':r['native']['error'],'first_direct':r['native']['direct_first_answer'],'siblings_exact':r['native']['siblings_exact']} for r in results if not r['pass']]},indent=2));sys.exit(0 if all(r['pass'] for r in results) and all(e['pass'] for e in extras) else 1)
