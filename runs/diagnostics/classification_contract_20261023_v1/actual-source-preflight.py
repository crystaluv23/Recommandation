"""One fresh deterministic source apply, then stop before any role receive/inbox."""
from contextlib import ExitStack
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
import json
import socket
from unittest.mock import patch

import run_financial_context_consumer_stage as old
from diagnose_executed_answer_scope import StageContract, binding
from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.data.reviewed_snapshot import open_raw_info_store
from stock_opportunity_agent.llm import get_model
from stock_opportunity_agent.llm.agent import AgentUsage
from stock_opportunity_agent.research.evolution_core import AgentStep, EvolutionControlFlow, InformationPlan, ResearchState, RuntimeLimits, SignalSelectionDecision, execute_information_plan, project_basic_info_bundle
from stock_opportunity_agent.research.evolution_plan_roles import LLMResearchController, LLMBlindPredictor
from stock_opportunity_agent.research.evolution_transport import StructuredRoleClient, ExternalAttemptLedger
from stock_opportunity_agent.research.local_role_exchange import LocalRoleExchange, _immutable
from stock_opportunity_agent.signal_library import SignalExecutor, SignalRegistry

BASE=old.REPO/'runs/diagnostics/classification_contract_20261023_v1'
ROOT=BASE/'actual-source-preflight'
if ROOT.exists(): raise AssertionError('preflight is single-entry')
ROOT.mkdir()
class Ready(EvolutionControlFlow): pass

def save(name,value): return _immutable(ROOT/(name+'.json'),value)

def observe(event):
    if event.get('event_type')=='request_ready':
        assert event['stage']=='research_controller_reflect'
        request=old.read_json(Path(event['request_path']))['request']
        reservation=len(json.dumps(request['messages'],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode())+request['max_output_tokens']
        assert reservation <= reflection_budgets[-1]
        save('request-ready',{**event,'logical_reservation':reservation})
        raise Ready()

with ExitStack() as guards:
    for owner,name in ((socket,'create_connection'),(socket.socket,'connect'),(socket.socket,'connect_ex'),
        (old.LabelStore,'__init__'),(old.LabelStore,'load'),(old.LabelStore,'ground_truth'),(old.LabelStore,'record'),
        (old.RawInfoStore,'append'),(old.ReviewedRawInfoStore,'append'),(SignalRegistry,'freeze'),
        (SignalRegistry,'register_stable'),(ExternalAttemptLedger,'reserve')):
        guards.enter_context(patch.object(owner,name,old.forbidden))
    inputs,protected=old.authorities()  # data authority only; never resume a completed stage
    sample=inputs['sample'];group=inputs['registry_group'];source=inputs['sources'][sample['source']]
    frozen=SignalRegistry(group['root'],candidate_root=ROOT/'unused_candidates').snapshot_from_refs(group['version'],tuple(group['refs']))
    assert frozen.registry_hash==group['registry_hash']
    resolver=old.initial.orientation._ObservedResolver(open_raw_info_store(source['root'],reviewed_snapshot=source).snapshot())
    contract={'limits':{**old.initial.LIMITS,'max_local_role_calls':3}}
    client=StructuredRoleClient(registration=get_model('independent-subagent'),contract=StageContract(contract),workspace=ROOT,
        ledger=ExternalAttemptLedger(ROOT/'unused_external.json',max_attempts=1,max_total_cost=.01),
        local_role_exchange=LocalRoleExchange(ROOT/'exchange',max_calls=3),allow_external=False,environ={},on_progress=observe)
    actual_batches=[]; reflection_budgets=[]; reservations=[]
    class Executor(SignalExecutor):
        def execute_batch(self,refs,**kwargs):
            assert tuple(refs)==(old.REF,) and not actual_batches
            batch=super().execute_batch(refs,**kwargs)
            assert batch.results[0].to_dict()==inputs['imported_batch']['results'][0]
            declarations=self.classification_contracts_for(batch.results)
            assert old.REF in declarations
            actual_batches.append(batch)
            save('actual-apply',{'results':[r.to_dict() for r in batch.results],
                'resolutions':[r.to_dict() for r in batch.resolutions],
                'document_fingerprints':batch.document_fingerprints,'classification_contracts':declarations,
                'physical_batch_calculations':1,'old_result_used_as_execution_input':False})
            return batch
    class Controller(LLMResearchController):
        def initialize(self,plan,basic):
            model,lineage=project_basic_info_bundle(resolver.observed_bundle)
            bootstrap={'plan':plan.to_dict(),'bundle':resolver.observed_bundle.to_dict(),'model_context':basic,
                'projection_lineage':lineage,'evaluation_context':self.evaluation_context,'evaluation_anchor':self.evaluation_anchor,
                'computed_metrics':self.computed_metrics,'document_channel_set_by_core':self.document_channel is not None}
            assert model==basic and canonical_json_hash(bootstrap)==canonical_json_hash(inputs['bootstrap'])
            save('bootstrap-binding',{'parent':binding(old.PARENT/'samples/h01/bootstrap.json'),'rebuilt_hash':canonical_json_hash(bootstrap),'whole_structure_equal':True})
            step=inputs['accepted_initial_step']
            return AgentStep(ResearchState.from_dict(step['state']),AgentUsage(**step['usage']),step['metadata'])
        def reflect(self,plan,state,batch):
            reflection_budgets.append(self.request_token_budget)
            return super().reflect(plan,state,batch)
    class Predictor(LLMBlindPredictor):
        def estimate_prediction_tokens(self,context):
            estimate=super().estimate_prediction_tokens(context)
            reservations.append(estimate)
            save('predictor-estimate-'+str(len(reservations)),{'logical_reservation':estimate,'context':context})
            return estimate
    class Selector:
        def select(self,*_args,**_kwargs):
            return AgentStep((SignalSelectionDecision.from_dict(inputs['context_intent']),),AgentUsage(**inputs['selection_usage']))
    stopped=False
    with client.anonymous_case(aliases=tuple(sample['identity']['identity_aliases']),company_id=sample['company_id'],ticker=sample['identity']['ticker']):
        try:
            execute_information_plan(plan=InformationPlan.from_dict(inputs['plan']),company_id=sample['company_id'],
                company_basic_source=sample['identity'],prediction_time=datetime.fromisoformat(sample['prediction_time']),signal_registry=frozen,
                signal_executor=Executor(frozen,resolver.store,resolver=resolver),controller=Controller(client),signal_agent=Selector(),
                predictor=Predictor(client),prediction_sink=old.forbidden,ground_truth_provider=old.forbidden,
                limits=RuntimeLimits(**old.read_json(old.ROUTING/'contract.json')['runtime_limits']))
        except Ready:stopped=True
    assert stopped and len(actual_batches)==1 and not list(ROOT.rglob('inbox/*.json'))
    old.initial.check(protected)
    save('result',{'state':'input_only_actual_apply_verified','physical_deterministic_batches':1,'production_model_responses':0,
        'inboxes':0,'external_API':0,'labels':0,'whole_parent_bootstrap_equal':True,'old_result_exact_equal':True,
        'reflection_budget':reflection_budgets[-1],'native_predictor_estimates':reservations,
        'source_bindings_unchanged':len(protected),'prior_usage_not_reset':asdict(old.PRIOR),
        'code_files':old.code_bindings(),'limitations':'Input-only. No claim about fresh model compliance; old consumer0of1 stays unchanged.'})
print('actual source preflight verified; model receives/inboxes/API/labels=0')
