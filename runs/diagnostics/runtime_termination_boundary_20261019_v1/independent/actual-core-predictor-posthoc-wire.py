import json,hashlib,tempfile,copy,socket
from pathlib import Path
from dataclasses import replace
from types import SimpleNamespace
from tests.scheme_evolution_test_support import NOW,OneBatchController,OneSignalSelector,ResearchState,ResearchDecision,AgentStep,AgentUsage,RuntimeLimits,SignalExecutor,default_information_plan,execute_information_plan,BlindPrediction,GroundTruth
from tests.test_information_plan_engine import InformationPlanRuntimeTests
from stock_opportunity_agent.research.evolution_core import RuntimeTerminationInputRejected,_assemble_final_context
from stock_opportunity_agent.research.evolution_plan_roles import LLMBlindPredictor
from stock_opportunity_agent.research.evolution_output_validation import _compact_posthoc_context
from stock_opportunity_agent.research.evolution_transport import StructuredRoleClient,ExternalAttemptLedger
from stock_opportunity_agent.research.local_role_exchange import LocalRoleRequestPending
from stock_opportunity_agent.llm import get_model
from scripts.replay_incremental_reflection_memory import deny_network
repo=Path('/Users/l/Project/Recommandation')
prediction=BlindPrediction(False,'insufficient_information',None,'low',('Synthetic transport fixture only.',),('No model answer generated.',),'synthetic-runtime-wire')
truth=GroundTruth(1.0)
results=[];rejects=[];posthoc=[];contexts={}
with deny_network() as network:
 for case,reason,trigger in [('init_finalize','finalized',None),('no_match','finalized','no_signal_match'),('max_round','finalized','max_signal_rounds'),('max_calls','finalized','max_signal_calls'),('terminal_budget','finalized','budget_exhausted'),('hard_budget','budget_exhausted','budget_exhausted'),('max_round_continue','max_signal_rounds','max_signal_rounds')]:
  with tempfile.TemporaryDirectory(prefix='independent-runtime-stop-') as td:
   root=Path(td);registry,store=InformationPlanRuntimeTests._registry_and_store(None,td)
   class Controller(OneBatchController):
    def __init__(self):super().__init__();self.reflect_contexts=[]
    def initialize(self,plan,basic):
     return AgentStep(ResearchState(next_information_needs=('What material evidence remains unavailable?',),decision=ResearchDecision.FINALIZE if case=='init_finalize' else ResearchDecision.CONTINUE),AgentUsage(llm_calls=1,tokens=20))
    def set_reflection_runtime_context(self,**context):self.reflect_contexts.append(context)
    def reflect(self,plan,state,batch):
     assert self.reflect_contexts[-1]['must_finalize']
     return AgentStep(replace(state,decision=ResearchDecision.CONTINUE if case=='max_round_continue' else ResearchDecision.FINALIZE),AgentUsage(llm_calls=1,tokens=20))
   class Selector(OneSignalSelector):
    def select(self,*a,**kw):return AgentStep((),AgentUsage(llm_calls=1,tokens=10)) if case=='no_match' else super().select(*a,**kw)
   contract=SimpleNamespace(contract_hash='e'*64,limits={'max_local_role_calls':8,'max_structured_corrections':1})
   caller=StructuredRoleClient(registration=get_model('independent-subagent'),contract=contract,workspace=root/'roles',ledger=ExternalAttemptLedger(root/'ledger.json',max_attempts=1,max_total_cost=1),allow_external=False,environ={})
   class Predictor(LLMBlindPredictor):
    def __init__(self):super().__init__(caller,anonymous_aliases=('winner_1',));self.reservations=[]
    def estimate_prediction_tokens(self,context):
     self.reservations.append(copy.deepcopy(context));return super().estimate_prediction_tokens(context)
   predictor=Predictor();controller=Controller();limits=RuntimeLimits(max_signal_rounds=1 if case in ('max_round','max_round_continue') else 2,max_signal_calls=1 if case=='max_calls' else 20,max_llm_calls=3 if case=='hard_budget' else 6 if case=='terminal_budget' else 30)
   def forbidden(*a):raise AssertionError('sink/labels must not be reached without prediction answer')
   with caller.anonymous_case(aliases=('winner_1',),company_id='winner_1'):
    try:
     execute_information_plan(plan=default_information_plan(),company_id='winner_1',company_basic_source={},prediction_time=NOW,signal_registry=registry.freeze(),signal_executor=SignalExecutor(registry.freeze(),store),controller=controller,signal_agent=Selector(),predictor=predictor,limits=limits,prediction_sink=forbidden,ground_truth_provider=forbidden)
     raise AssertionError('actual predictor should pend')
    except LocalRoleRequestPending as e:
     raw=json.loads(Path(e.pending['inbox_path']).read_text());context=json.loads(raw['messages'][-1]['content'])['final_context'];request_hash=e.pending['request_hash']
    expected={'phase':'prediction_ready','stop_reason':reason,'termination_trigger':trigger}
    assert context['runtime_termination']==expected
    assert context['final_research_state']['next_information_needs']==['What material evidence remains unavailable?']
    assert all(c['runtime_termination']=={'phase':'research_in_progress','stop_reason':None,'termination_trigger':None} for c in predictor.reservations)
    assert case=='init_finalize' or predictor.reservations
    assert 'winner_1' not in json.dumps(raw['messages'])
    contexts[case]=context
    # Actual posthoc caller wire, using explicit synthetic prediction/outcome solely for transport.
    try:predictor.reflect(context,prediction,truth);raise AssertionError('posthoc should pend')
    except LocalRoleRequestPending as e:
     raw=json.loads(Path(e.pending['inbox_path']).read_text());payload=json.loads(raw['messages'][-1]['content']);assert payload['compact_context']['runtime_termination']==expected
     assert 'winner_1' not in json.dumps(raw['messages']);phash=e.pending['request_hash']
    results.append({'case':case,'runtime_termination':expected,'decision':context['final_research_state']['decision'],'reflect_count':len(controller.reflect_contexts),'reservation_count':len(predictor.reservations),'predictor_request_hash':request_hash,'posthoc_request_hash':phash,'actual_wire_anonymous':True,'retained_need':True})
   # Technical rejections must precede dispatch; use direct predictor & reflect calls.
   pending_before=len(list((root/'roles').rglob('inbox/*.json')))
   malformed=[None,{}, {'phase':'other','stop_reason':'finalized','termination_trigger':None},{'phase':'prediction_ready','stop_reason':None,'termination_trigger':None},{'phase':'prediction_ready','stop_reason':True,'termination_trigger':None},{'phase':'prediction_ready','stop_reason':'finalized','termination_trigger':[]},{'phase':'prediction_ready','stop_reason':'finalized','termination_trigger':None,'extra':0},{'phase':'research_in_progress','stop_reason':'finalized','termination_trigger':None},{'phase':'research_in_progress','stop_reason':None,'termination_trigger':None}]
   for index,block in enumerate(malformed):
    bad={**context,'runtime_termination':block}
    for entry,action in [('predict',lambda:predictor.predict(bad)),('posthoc',lambda:predictor.reflect(bad,prediction,truth))]:
     try:action();raise AssertionError('malformed/reservation dispatched')
     except RuntimeTerminationInputRejected:pass
    rejects.append({'case':case,'variant':index,'typed_before_dispatch':True})
   assert pending_before==len(list((root/'roles').rglob('inbox/*.json')))
   progress={**context,'runtime_termination':{'phase':'research_in_progress','stop_reason':None,'termination_trigger':None}}
   assert predictor.estimate_prediction_tokens(progress) is not None
   legacy={k:v for k,v in context.items() if k!='runtime_termination'}
   compact=_compact_posthoc_context(legacy);assert 'runtime_termination' not in compact
   try:predictor.reflect(legacy,prediction,truth);raise AssertionError('legacy should pend')
   except LocalRoleRequestPending as e:
    payload=json.loads(json.loads(Path(e.pending['inbox_path']).read_text())['messages'][-1]['content']);assert 'runtime_termination' not in payload['compact_context']
    posthoc.append({'case':case,'legacy_posthoc_hash':e.pending['request_hash'],'legacy_runtime_block_absent':True})
   try:predictor.predict(legacy);raise AssertionError('legacy predictor should pend')
   except LocalRoleRequestPending:pass
# Legacy assembler call has no injected block.
legacy=_assemble_final_context(plan=default_information_plan(),company_id='winner_1',additional_identity_aliases=(),basic_info={},state=ResearchState(next_information_needs=('Unanswered material question?',)),rounds=(),prediction_time=NOW)
assert 'runtime_termination' not in legacy
paths=[repo/'src/stock_opportunity_agent/research/evolution_core.py',repo/'src/stock_opportunity_agent/research/evolution_plan_roles.py',repo/'src/stock_opportunity_agent/research/evolution_output_validation.py',repo/'tests/scheme_evolution_test_support.py',repo/'tests/test_information_plan_engine.py']
out={'scope':'Actual execute_information_plan→LLMBlindPredictor/StructuredRoleClient pending and actual posthoc transport only; synthetic controller/selector and prediction/truth; not production model behavior, sink completion or research result.','cases':results,'typed_rejection_checks':len(rejects)*2,'legacy':posthoc,'legacy_assembler_no_block':True,'sink_calls':0,'label_provider_calls':0,'role_answers':0,'network_attempts':network['network_attempts'],'code_bindings':{str(p.relative_to(repo)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}
Path('/tmp/independent-runtime-termination-results.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
