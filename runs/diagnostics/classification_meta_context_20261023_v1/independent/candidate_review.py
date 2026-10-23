"""Independent candidate wiring, paging and rejection controls; no research answers."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import runpy
import subprocess
import sys
from dataclasses import replace
from tempfile import TemporaryDirectory
from types import SimpleNamespace

BASE = Path(__file__).resolve().parent
env = runpy.run_path(str(BASE/'counterreview.py'))
globals().update({k: env[k] for k in ('ROOT','cases','plan','metrics','rows','index','full','memory','bindings','references','network')})
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.llm.agent import AgentUsage
from stock_opportunity_agent.research.evolution_core import CaseReflectionEvidence, _mask_identity_values
from stock_opportunity_agent.research.evolution_plan_roles import LLMPlanCritic, _ReflectionMemoryCaller
from stock_opportunity_agent.research.evolution_reflection_memory import ReflectionMemoryIndex
from stock_opportunity_agent.research.mining_controller import LabelAwareMiningController
from stock_opportunity_agent.research.plan_evolution import EvolutionWorkspace
from stock_opportunity_agent.research.signal_evolution import SignalEvolutionEngine
from stock_opportunity_agent.signal_library import SignalRegistry, validate_signal_classification_contract
from stock_opportunity_agent.data.raw_info import RawInfoStore
from tests.scheme_evolution_test_support import make_case

before = bindings()
def size(value): return len(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode())
def final(): return {'reflection_items': [], 'selected_reflection_refs': [], 'no_findings_reason': 'Independent wiring control; research semantics unassessed.'}

class Critic:
    max_structured_corrections = 1
    def __init__(self): self.calls=[]
    def complete_json(self, **kwargs):
        self.calls.append(deepcopy(kwargs))
        payload=kwargs['payload']
        if len(self.calls)==1:
            self.initial=references(payload)
            return {'browse_memory': {'cursor':0, 'level':'case', 'signal_ref':rows[0]['signal_classification_context'][0]['signal_ref']}}, AgentUsage(llm_calls=1)
        if len(self.calls)==2:
            self.header=next(r for r in payload['memory_disclosures'][-1]['sources'] if r['source_ref'] not in self.initial)
            return {'read_refs':[self.header['source_ref']]}, AgentUsage(llm_calls=1)
        self.source=payload['memory_disclosures'][-1]['sources'][0]
        assert self.source['source_ref']==self.header['source_ref']
        validate_signal_classification_contract(self.source['content']['contract'], signal_ref=self.header['signal_ref'])
        return final(), AgentUsage(llm_calls=1)
critic=Critic()
LLMPlanCritic(critic).critique(plan=plan, trajectories=cases, metrics=metrics)
assert len(critic.calls)==3
assert critic.source['content']==index.read_refs([critic.header['source_ref']],role='plan_critic',max_bytes=48_000)['sources'][0]['content']

class H1:
    def __init__(self): self.calls=[]
    def request_slow_sources(self,payload):
        self.calls.append(deepcopy(payload))
        self.header=next(r for r in payload['available_sources'] if r.get('source_kind')=='runtime_signal_classification' and r['ref'] not in self.initial)
        return SimpleNamespace(value=(self.header['ref'],),metadata={},usage=AgentUsage())
h1=H1()
with TemporaryDirectory() as temporary:
    engine=SignalEvolutionEngine(registry=SignalRegistry(Path(temporary)/'signals'), raw_info_store=RawInfoStore(),
        discovery_cases=(make_case('independent_discovery',1.1),),meta_memory=memory,workspace=EvolutionWorkspace(Path(temporary)/'workspace'),
        mining_model=h1,update_model=SimpleNamespace(),llm_signal_runner=None)
    slow_index=engine._controller_memory_index()
    h1.initial=references(slow_index.catalog_view(max_bytes=16_000))
    context=engine._mining_context(cycle_id=1)
    selected=next(s for s in context['meta_memory_disclosures'] if s['ref']==h1.header['ref'])
    assert selected['content']==slow_index.read_refs([h1.header['ref']],role='signal_mining',max_bytes=48_000)['sources'][0]
    validate_signal_classification_contract(selected['content']['content']['contract'],signal_ref=h1.header['signal_ref'])

class Mining:
    def __init__(self): self.views=[]
    def next_action(self,view):
        self.views.append(deepcopy(view))
        if len(self.views)==1:
            return {'action':'inspect_catalog','scope':'memory','cursor':0,'level':'case','signal_ref':rows[0]['signal_classification_context'][0]['signal_ref'],'rationale':['Inspect original declaration headers.']}
        if len(self.views)==2:
            self.header=view['last_action_result']['result']['directory']['sources'][0]
            return {'action':'inspect_catalog','scope':'memory','item_refs':[self.header['source_ref']],'rationale':['Read the disclosed complete declaration.']}
        self.packet=view['last_action_result']['result']
        assert self.packet['sources'][0]['source_ref']==self.header['source_ref']
        return {'action':'record_deferred','rationale':['Independent transport control; no research conclusion.']}
mining=Mining()
controller=LabelAwareMiningController(store=RawInfoStore(),model=mining,case_pairs=(('case_control',make_case('independent_discovery',1.1)),),
    measurable_evidence_manifest={},signal_catalog=(),seed='discovery',memory_index=slow_index)
mining_result=controller.run()
assert len(mining.views)==3 and controller._browse_used==2 and controller._light_used==0 and controller._heavy_used==0
assert controller.meta_memory_disclosures[0]['ref']==mining.header['source_ref']

# Full discovery is measured separately from whether a single role can afford every read.
mixed_rows=deepcopy(rows)
mixed_rows[0]['self_reflection']['plan_issues']=['Independent legacy action item.']
mixed=ReflectionMemoryIndex.from_case_rows(mixed_rows,owner_ref='plan:independent_mixed')
def walk(idx,**kwargs):
    cursor=0; seen=[]; pages=[]
    while cursor is not None:
        page=idx.directory(cursor=cursor,**kwargs); pages.append(page)
        seen += [r['source_ref'] for r in page.get('sources',())]+[r['item_ref'] for r in page['items']]+page['oversized_refs']
        assert page['next_cursor']!=cursor
        cursor=page['next_cursor']
    assert len(seen)==len(set(seen))
    return seen,pages
seen,pages=walk(mixed,max_bytes=1500)
expected=set(full)|{r['item_ref'] for r in mixed.brief_view(max_bytes=100_000,max_items=100)['items']}
# Source refs hash content, so changing self-reflection does not change the individual runtime units.
assert set(seen)==expected
signal=rows[0]['signal_classification_context'][0]['signal_ref']
filtered,filtered_pages=walk(mixed,max_bytes=1500,level='case',signal_ref=signal)
assert set(filtered)==full
for level in ('plan','round','cross_round'):
    assert not mixed.directory(level=level).get('sources')
assert not mixed.directory(signal_ref=signal.rsplit(':v',1)[0]+':v2').get('sources')
for bad in (True,-1,len(expected)+1):
    try: mixed.directory(cursor=bad)
    except ValidationError: pass
    else: raise AssertionError('Invalid cursor accepted')

single=ReflectionMemoryIndex.from_case_rows([rows[0]],owner_ref='plan:single')
page=single.directory(max_bytes=100_000)
assert single.directory(max_bytes=size(page))==page
smaller=single.directory(max_bytes=size(page)-1)
assert size(smaller)<=size(page)-1 and smaller!=page
oversized=single.directory(max_bytes=300)
assert oversized['oversized_refs'] and not oversized.get('sources') and oversized['next_cursor']!=0
try: single.directory(max_bytes=10)
except ValidationError: pass
else: raise AssertionError('Unfit manifest accepted')
header=single.source_catalog()[2]
ref=next(r['source_ref'] for r in single.source_catalog() if r.get('runtime_signal_classification'))
cost=single.read_refs([ref],role='plan_critic',max_bytes=48_000)['byte_count']
try: single.read_refs([ref],role='plan_critic',max_bytes=cost-1)
except ValidationError: pass
else: raise AssertionError('Partial whole-unit read accepted')

# Native wrapper fourth request is refused under the existing three-request cap.
class Four:
    def __init__(self): self.calls=0
    def complete_json(self,**kwargs):
        self.calls+=1
        return {'browse_memory': {'cursor':self.calls-1,'level':'case','signal_ref':signal}},AgentUsage(llm_calls=1)
four=Four()
try: _ReflectionMemoryCaller(four,index,role='plan_critic',aliases=()).complete_json(payload={},stage='plan_critic',system_prompt='Independent transport control.',allow_outcomes=True)
except Exception as exc:
    assert 'three requests' in str(exc); fourth_error=str(exc)
else: raise AssertionError('Fourth request allowed')
assert four.calls==4

# Actual executor declaration text can exceed a reader cap; complete source remains saved.
from tests.test_classification_meta_context import executed_trajectory
huge_trajectory=executed_trajectory(flows=(-60,),declaration_repeat=2000)
huge_row=CaseReflectionEvidence.from_trajectory(huge_trajectory,case_index=1).to_dict()
huge_index=ReflectionMemoryIndex.from_case_rows([huge_row],owner_ref='plan:huge')
huge_header=next(r for r in huge_index.catalog_view()['sources'] if r.get('runtime_signal_classification'))
assert huge_header['read_bytes']>48_000
assert any(r['source_ref']==huge_header['source_ref'] for r in huge_index.directory()['sources'])
try: huge_index.read_refs([huge_header['source_ref']],role='plan_critic',max_bytes=48_000)
except ValidationError as exc: huge_error=str(exc)
else: raise AssertionError('Oversized source disclosed partially')
assert CaseReflectionEvidence.from_dict(huge_row).to_dict()==huge_row

# Three individually admissible original reads must still fail once cumulative disclosure exceeds 48 KB.
aggregate_rows=deepcopy(rows[:3])
from stock_opportunity_agent.artifacts import canonical_json_hash
for number,row in enumerate(aggregate_rows):
    row['signal_classification_context']=row['signal_classification_context'][:1]
    decl=row['signal_classification_context'][0]['contract']
    decl['definition']+=' Cumulative budget control.'*700
    decl.pop('contract_hash'); decl['contract_hash']=canonical_json_hash(decl)
aggregate_index=ReflectionMemoryIndex.from_case_rows(aggregate_rows,owner_ref='plan:aggregate')
aggregate_headers=[r for r in aggregate_index.catalog_view()['sources'] if r.get('runtime_signal_classification')]
assert len(aggregate_headers)==3 and all(r['read_bytes']<48_000 for r in aggregate_headers)
class Aggregate:
    def __init__(self): self.calls=[]
    def complete_json(self,**kwargs):
        self.calls.append(deepcopy(kwargs))
        return {'read_refs':[aggregate_headers[len(self.calls)-1]['source_ref']]},AgentUsage(llm_calls=1)
aggregate=Aggregate()
try:
    _ReflectionMemoryCaller(aggregate,aggregate_index,role='plan_critic',aliases=()).complete_json(payload={'source_catalog':aggregate_index.catalog_view()},stage='plan_critic',system_prompt='Independent budget control.',allow_outcomes=True)
except Exception as exc:
    assert 'read byte budget' in str(exc) or 'aggregate byte budget' in str(exc); aggregate_error=str(exc)
else: raise AssertionError('Aggregate disclosure cap bypassed')
assert len(aggregate.calls)==3 and size(aggregate.calls[-1]['payload']['memory_disclosures'])<=48_000

# Legacy directory bytes/count/cursors remain identical to the pre-change implementation.
legacy=deepcopy(mixed_rows)
for row in legacy: row.pop('signal_classification_context')
old_source=subprocess.check_output(['git','show','HEAD:src/stock_opportunity_agent/research/evolution_reflection_memory.py'],cwd=ROOT,text=True)
legacy_path=BASE/'memory-before.py'; legacy_path.write_text(old_source)
spec=importlib.util.spec_from_file_location('independent_legacy_memory',legacy_path)
oldmodule=importlib.util.module_from_spec(spec); sys.modules[spec.name]=oldmodule; spec.loader.exec_module(oldmodule)
old=oldmodule.ReflectionMemoryIndex.from_case_rows(legacy,owner_ref='plan:legacy')
new=ReflectionMemoryIndex.from_case_rows(legacy,owner_ref='plan:legacy')
assert old.source_catalog()==new.source_catalog()
assert walk(old,max_bytes=1500)==walk(new,max_bytes=1500)
for row in legacy:
    assert CaseReflectionEvidence.from_dict(row).to_dict()==row

# Anonymous definition projection retains source hash and has valid own integrity.
private=deepcopy(rows[0]); private['signal_classification_context'][0]['contract']['definition']+=' Independent Private Issuer Inc.'
contract=private['signal_classification_context'][0]['contract']; contract.pop('contract_hash'); contract['contract_hash']=canonical_json_hash(contract)
private_index=ReflectionMemoryIndex.from_case_rows([private],owner_ref='plan:private')
private_ref=next(r['source_ref'] for r in private_index.source_catalog() if r.get('runtime_signal_classification') and r['signal_round']==1)
packet=private_index.read_refs([private_ref],role='plan_critic',max_bytes=48_000)
masked=_mask_identity_values(packet,('Independent Private Issuer Inc.',))
projected=masked['sources'][0]['content']['contract']
assert projected['source_contract_hash']==contract['contract_hash'] and projected['contract_hash']!=contract['contract_hash']
validate_signal_classification_contract(projected,signal_ref=signal)
assert 'Independent Private Issuer Inc.' not in json.dumps(masked)

# Missing data and deterministic technical failures preserve different statuses and invent no declaration.
from stock_opportunity_agent.signal_library import SignalExecutor
from stock_opportunity_agent.research.evolution_core import SignalRound, ResearchDecision, ResearchState, _assemble_final_context, default_information_plan
spec,frozen,store=env['inputs'](cash_flow=-60)
def broken(*args):
    """Deliberately fail a deterministic measurement for a technical-status control."""
    raise ValueError('Independent technical failure control')
status_controls=[]
for raw_store,functions in ((RawInfoStore(),None),(store,{spec.function:broken})):
    executor=SignalExecutor(frozen,raw_store,deterministic_functions=functions)
    batch=executor.execute_batch((spec.ref,),company_id='issuer_1',as_of=env['AS_OF'])
    declarations=executor.classification_contracts_for(batch.results)
    assert declarations=={}
    round_value=SignalRound((),cases[0].signal_rounds[0].selections,batch)
    final_context=_assemble_final_context(plan=default_information_plan(),company_id='issuer_1',additional_identity_aliases=(),basic_info={'requests':[]},
        state=ResearchState(decision=ResearchDecision.FINALIZE),rounds=(round_value,),prediction_time=env['AS_OF'],signal_classification_contracts=(declarations,))
    trajectory=replace(env['make_trajectory']('issuer_1',1.1,False,None),prediction_time=env['AS_OF'],signal_rounds=(round_value,),final_context=final_context)
    saved=CaseReflectionEvidence.from_trajectory(trajectory,case_index=1)
    assert saved.signal_classification_context is None
    status_controls.append({'status':batch.results[0].execution_status.value,'failures':saved.recorded_signal_execution_failures})
assert status_controls[0]['status']=='domain_unavailable' and status_controls[1]['status']=='validation_failed'
assert not status_controls[0]['failures'] and status_controls[1]['failures']
excluded=replace(cases[0],prediction=replace(cases[0].prediction,session_id='exclusion_independent'))
excluded_row=CaseReflectionEvidence.from_trajectory(excluded,case_index=1).to_dict()
assert 'technical_exclusion' in excluded_row and 'signal_classification_context' not in excluded_row
assert not any(r.get('runtime_signal_classification') for r in ReflectionMemoryIndex.from_case_rows([excluded_row],owner_ref='plan:excluded').source_catalog())

result={'kind':'offline independent wiring and counterexamples; no live semantic conclusion',
    'critic_calls':len(critic.calls),'critic_selected_newly_disclosed_ref':critic.header['source_ref'],
    'h1_selected_outside_initial_slice':h1.header['ref'],'h1_selector_runtime_headers':sum(r.get('source_kind')=='runtime_signal_classification' for r in h1.calls[0]['available_sources']),
    'h1_selector_omitted_count':h1.calls[0]['omitted_available_sources'],
    'native_mining_browse_read':{'selected_ref':mining.header['source_ref'],'browse_used':controller._browse_used,'light_used':controller._light_used,'heavy_used':controller._heavy_used},
    'directory_runtime_sources_discovered':len(set(seen)&full),'directory_all_units_discovered':len(seen),'mixed_pages':len(pages),'signal_filtered_pages':len(filtered_pages),
    'exact_fit_and_minus_one':True,'oversized_progress':oversized,'legacy_exact_match':True,'anonymous_hash':True,
    'fourth_request_error':fourth_error,'huge_complete_source_read_bytes':huge_header['read_bytes'],'huge_read_error':huge_error,
    'aggregate_read_error':aggregate_error,'aggregate_individual_read_bytes':[r['read_bytes'] for r in aggregate_headers],
    'unknown_and_technical_controls':status_controls,'whole_case_exclusion_has_no_context':True,
    'source_hashes_before':before,'source_hashes_after':bindings(),'source_hashes_stable':before==bindings(),'network_attempts':len(network)}
(BASE/'candidate-review-result.json').write_text(json.dumps(result,indent=2)+'\n')
(BASE/'candidate-critic-requests.json').write_text(json.dumps(critic.calls,indent=2,default=str)+'\n')
(BASE/'candidate-h1-selector.json').write_text(json.dumps(h1.calls,indent=2)+'\n')
(BASE/'candidate-native-mining-views.json').write_text(json.dumps(mining.views,indent=2,default=str)+'\n')
print(json.dumps(result,indent=2))
