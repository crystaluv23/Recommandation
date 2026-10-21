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
R=Path('/Users/l/Project/Recommandation');O=R/'runs/diagnostics/routing_literal_scope_20261021_v1/independent';S=R/'runs/diagnostics/gpre_native_routing_20261021_v1/stage'
def read(p):return json.loads(p.read_text())
def h(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def b(p):return {'path':str(p),'sha256':h(p),'bytes':p.stat().st_size}
p=argparse.ArgumentParser();p.add_argument('--mode',choices=('baseline','candidate'),required=True);p.add_argument('--expected-sha');p.add_argument('--typed-head-only',action='store_true');p.add_argument('--sole-head-only',action='store_true');p.add_argument('--source-file',type=Path);p.add_argument('--sole-head-expectations',type=Path);p.add_argument('--output-prefix',default='');args=p.parse_args()
casefile=O/'axis-only-expectations.json';assert h(casefile)=='11ef5ab284e1948fab27faa0c05056779f16f9231bbce654a48891516dc56e2e';cases=read(casefile)
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
 needs=list(ctx['information_needs']);needs[1]=case['target_need'];payload=deepcopy(raw);payload['selections'][1].update(selection_reason=case['selection_reason'],residual_need=case['residual_need']);payload['selections'][1].update(deepcopy(case.get('row_overrides',{})));state=deepcopy(state0);state['next_information_needs']=needs
 caller=OfflineScriptedRoleCaller(payload,repair);agent=roles.LLMSignalRetrievalAgent(caller);agent.set_evaluation_context(datetime.fromisoformat('2025-05-30T00:00:00+00:00'));agent.set_deterministic_functions(default_deterministic_signal_functions())
 outcome=None;error=None
 try:outcome=agent.select(tuple(needs),registry,{},research_state=ResearchState.from_dict(state),eligible_signal_refs=tuple(group['refs']),prior_context_tags=())
 except Exception as e:error={'type':type(e).__name__,'message':str(e)}
 selected=[x.to_dict() for x in outcome.value] if outcome else[];order=next((x for x in selected if x['signal_ref']=='order_confirmation_disclosed:v3'),None)
 direct=len(caller.calls)==1 and order is not None and order.get('reason_code')=='answer_need' and order.get('answer_scope')=='partial' and order.get('selection_reason')==case['selection_reason'] and order.get('residual_need')==case['residual_need']
 sibling_ok=all(next((x for x in selected if x['signal_ref']==row['signal_ref']),None)=={k:v for k,v in row.items() if v is not None} for row in (raw['selections'][0],raw['selections'][2])) if selected else False
 feedback=[c['payload'].get('validation_feedback') for c in caller.calls[1:]]
 return {'direct_first_answer':direct,'calls':len(caller.calls),'offline_returned_answers':caller.responses,'error':error,'selected':selected,'siblings_exact':sibling_ok,'feedback':feedback,'typed_contracts':[c['payload'].get('output_patch_contract') for c in caller.calls[1:]]}
results=[]
with ExitStack() as st:
 for owner,method in ((socket,'socket'),(socket,'create_connection'),(LabelStore,'__init__'),(LabelStore,'load'),(LabelStore,'record'),(LabelStore,'ground_truth'),(RawInfoStore,'__init__'),(RawInfoStore,'append'),(SignalExecutor,'execute_batch'),(SignalExecutor,'prepare_inputs'),(SignalRegistry,'freeze'),(SignalRegistry,'install_catalog')):st.enter_context(patch.object(owner,method,forbidden))
 st.enter_context(patch.object(roles,'_shared_distinctive_phrase',fn))
 for case in cases['cases']:
  shared=fn(case['selection_reason'],case['residual_need'],target_need=case['target_need'])
  native=run(case)
  ok=native['direct_first_answer']==case['expected_direct_partial'] and native['siblings_exact']
  results.append(dict(case_id=case['case_id'],expected_direct_partial=case['expected_direct_partial'],helper_shared_phrase=shared,native=native,pass_=ok))
 with tempfile.TemporaryDirectory(prefix='literal-scope-typed-') as temp:
  f=Path(temp)/'native-selected.json';f.write_text(json.dumps([x['native']['selected'] for x in results]));assert read(f)==[x['native']['selected'] for x in results]
 assert not trips
out=dict(mode=args.mode,module_file=str(module.__file__),code_filename=fn.__code__.co_filename,source=b(path),parser=b(Path(roles.__file__)),expectations=b(casefile),results=results,forbidden=trips,passed=sum(x['pass_'] for x in results),total=len(results),limits='Offline scripted native parser only; no fresh role/Signal calculation/Store/LabelStore/API/network/stage entry. Helper isolated while common parser remains current pinned revision.')
dest=O/(args.output_prefix+'results.json');assert not dest.exists();dest.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps(dict(result=b(dest),passed=out['passed'],total=out['total'],mismatches=[x['case_id'] for x in results if not x['pass_']]),indent=2));sys.exit(0 if all(x['pass_'] for x in results) else 1)
