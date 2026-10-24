#!/usr/bin/env python3
"""Consume one completed financial result through native Reflect and Predictor."""
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
import socket
import traceback
from unittest.mock import patch

import run_gpre_native_initial_stage as initial
from diagnose_executed_answer_scope import StageContract, binding, read_json
from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.cases.label_store import LabelStore
from stock_opportunity_agent.data.raw_info import RawInfoStore
from stock_opportunity_agent.data.resolution import RawInfoResolution
from stock_opportunity_agent.data.reviewed_snapshot import ReviewedRawInfoStore, open_raw_info_store
from stock_opportunity_agent.llm import get_model
from stock_opportunity_agent.llm.agent import AgentUsage
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_core import (
    AgentStep, EvolutionControlFlow, InformationPlan, ResearchState, RuntimeLimits,
    SignalSelectionDecision, execute_information_plan, project_basic_info_bundle,
)
from stock_opportunity_agent.research.evolution_plan_roles import LLMBlindPredictor, LLMResearchController
from stock_opportunity_agent.research.evolution_transport import ExternalAttemptLedger, StructuredRoleClient
from stock_opportunity_agent.research.local_role_exchange import LocalRoleExchange, LocalRoleRequestPending, _immutable
from stock_opportunity_agent.signal_library import SignalBatchResult, SignalExecutor, SignalRegistry, SignalResult

REPO=initial.REPO
BASE=REPO/'runs/diagnostics/financial_context_consumer_20261023_v1'
ROOT=BASE/'stage'
SPEC=REPO/'spec/scripts/run_financial_context_consumer_stage.md'
REF='liquidity_runway_months:v3'
PARENT=initial.ROOT
ROUTING=REPO/'runs/diagnostics/gpre_native_routing_20261021_v1/stage'
FINANCIAL=REPO/'runs/diagnostics/current_financial_apply_20261021_v1/native/stage'
PRIOR=AgentUsage(tokens=111032,llm_calls=2)


class ConsumerBoundary(EvolutionControlFlow):
    """Prediction is durably saved; no labels or Posthoc may follow."""


class InputOnlyBoundary(EvolutionControlFlow):
    """Preflight stops before cache receive or a model inbox."""


def save(name,value):
    """Retain exact immutable diagnostic artifacts."""
    return _immutable(ROOT/(name+'.json'),value)


def forbidden(*args,**kwargs):
    """Reject effects beyond the declared completed-result consumer boundary."""
    raise ValidationError('consumer stage forbids network/labels/source or Registry writes/new Signal apply')


@contextmanager
def guards():
    """Allow the empty reviewed-memory parent, never persistent data mutation."""
    native_init=RawInfoStore.__init__
    def empty_memory(self,root=None,documents=()):
        if root is not None or tuple(documents): forbidden()
        native_init(self)
    with ExitStack() as stack:
        for owner,name in ((socket,'create_connection'),(socket.socket,'connect'),(socket.socket,'connect_ex'),
                (LabelStore,'__init__'),(LabelStore,'load'),(LabelStore,'ground_truth'),(LabelStore,'record'),
                (RawInfoStore,'append'),(ReviewedRawInfoStore,'append'),(SignalRegistry,'freeze'),
                (SignalRegistry,'register_stable'),(SignalExecutor,'execute_batch'),
                (SignalExecutor,'prepare_inputs'),(ExternalAttemptLedger,'reserve')):
            stack.enter_context(patch.object(owner,name,forbidden))
        stack.enter_context(patch.object(RawInfoStore,'__init__',empty_memory))
        yield


def authorities():
    """Read immutable accepted data without resuming historical code."""
    manifest=read_json(PARENT/'manifest.json')
    digest=manifest.pop('manifest_hash')
    if canonical_json_hash(manifest)!=digest: raise ValidationError('parent manifest mismatch')
    inputs=read_json(PARENT/'inputs.json');contract=read_json(PARENT/'contract.json')
    if canonical_json_hash(inputs)!=manifest['inputs_hash'] or canonical_json_hash(contract)!=manifest['contract_hash']:
        raise ValidationError('parent immutable input/contract mismatch')
    initial.check(manifest['source_files']+[manifest['expectations']])
    binding(PARENT/'completion.json', '58082055515d8809e51a0ba897378cc9fb39c4fc61c426867c514c44c0ab5ec0')
    binding(PARENT.parent/'independent-preflight/actual-initial-review.json',
            '455ca111aedd1f8e107de32b023f51ebb4003e3650bdd3ad980f8b15005090d2')
    completion=read_json(PARENT/'completion.json');initial.check([completion['initial_state']])
    accepted=read_json(PARENT/'samples/h01/initial_state.json')
    parsed=read_json(PARENT/'samples/h01/parsed_step.json')
    if {k:accepted[k] for k in ('state','usage','metadata','request_hashes')}!=parsed or accepted['usage']!=accepted['native_budget_usage']:
        raise ValidationError('accepted initial step differs from parsed authority')
    route_completion=read_json(ROUTING/'completion.json');initial.check([route_completion['accepted_selection']])
    selection=read_json(ROUTING/'accepted-selection.json')
    intent=next(r for r in selection['selections'] if r['signal_ref']==REF)
    if intent['reason_code']!='combine_evidence' or intent.get('answer_scope') is not None:
        raise ValidationError('consumer input must have context-only authority')
    usage=AgentUsage(**accepted['usage'])+AgentUsage(**selection['new_selection_usage'])
    if usage!=PRIOR or selection['native_combined_case_usage']!=asdict(PRIOR):
        raise ValidationError('prior usage cannot be reset')
    result=read_json(FINANCIAL/'result.json');initial.check([result['native_batch']])
    index=next(i for i,r in enumerate(result['comparisons']) if r['signal_ref']==REF)
    if not result['comparisons'][index]['passed'] or result['fixed_denominator']!=9:
        raise ValidationError('imported financial result is not an original strict pass')
    batch=read_json(Path(result['native_batch']['path']))
    if batch['results'][index]['signal_id']+':v'+str(batch['results'][index]['version'])!=REF:
        raise ValidationError('financial result order differs')
    group=inputs['registry_group'];initial.check(group['definition_bindings'])
    imported={'results':[batch['results'][index]],'resolutions':[batch['resolutions'][index]],
        'signal_calls':1,'usage':batch['usage'],'document_fingerprints':{REF:batch['document_fingerprints'][REF]}}
    if imported['usage']!=asdict(AgentUsage()): raise ValidationError('unexpected imported model usage')
    value={**inputs,'accepted_initial_step':accepted,'bootstrap':read_json(PARENT/'samples/h01/bootstrap.json'),
        'context_intent':intent,'selection_usage':selection['new_selection_usage'],'imported_batch':imported}
    protected=initial.unique([*manifest['source_files'],manifest['expectations'],
        *[r for r in initial.files(PARENT) if r['path']!=str(PARENT/'exchange/.dispatch.lock')],
        binding(ROUTING/'completion.json'),binding(ROUTING/'accepted-selection.json'),
        binding(FINANCIAL/'result.json'),result['native_batch']])
    return value,protected


def code_bindings():
    """Bind current code separately from immutable historical input authority."""
    return initial.unique([*initial.code_bindings(),binding(Path(__file__)),binding(SPEC)])


def prepare(expectations):
    """Freeze the one formal consumer stage after input-only verification."""
    if ROOT.exists(): raise ValidationError('formal consumer destination must be new')
    if expectations is None: raise ValidationError('pre-answer expectations are required')
    with guards(): inputs,protected=authorities()
    preflight_root=BASE/'preflight'
    ready=read_json(preflight_root/'request-ready.json')
    if (ready['stage']!='research_controller_reflect'
            or read_json(preflight_root/'bootstrap.json')!=inputs['bootstrap']
            or list(preflight_root.rglob('inbox/*.json'))):
        raise ValidationError('input-only native preflight is missing or differs')
    protected=initial.unique([*protected,*initial.files(preflight_root),
        binding(BASE/'reference/bootstrap-binding-addendum.json')])
    runtime=read_json(ROUTING/'contract.json')['runtime_limits']
    contract={'schema_version':'completed-financial-context-consumer-v1','backend':'independent-subagent',
        'limits':{**initial.LIMITS,'max_local_role_calls':3},'runtime_limits':runtime,
        'prior_case_usage':asdict(PRIOR),'scope':'completed context-result consumer subset; no new routing/apply/labels/round commit',
        'fixed_denominator':1}
    manifest={'inputs_hash':canonical_json_hash(inputs),'contract_hash':canonical_json_hash(contract),
        'source_files':protected,'code_files':code_bindings(),'expectations':binding(Path(expectations))}
    manifest['manifest_hash']=canonical_json_hash(manifest)
    ROOT.mkdir(parents=True,exist_ok=False)
    for name,value in (('inputs',inputs),('contract',contract),('manifest',manifest)):save(name,value)
    return {'state':'prepared','prior_usage':asdict(PRIOR),'source_bindings':len(protected)}


def verify():
    """Reject code/source/input drift before each pending boundary."""
    manifest=read_json(ROOT/'manifest.json');digest=manifest.pop('manifest_hash')
    inputs=read_json(ROOT/'inputs.json');contract=read_json(ROOT/'contract.json')
    if (digest!=canonical_json_hash(manifest) or canonical_json_hash(inputs)!=manifest['inputs_hash']
            or canonical_json_hash(contract)!=manifest['contract_hash']): raise ValidationError('consumer manifest drift')
    initial.check(manifest['source_files']+manifest['code_files']+[manifest['expectations']])
    return inputs,contract


def native(inputs,contract,client):
    """Run actual core consumers over a declared completed-result input boundary."""
    sample=inputs['sample'];source=inputs['sources'][sample['source']]
    resolver=initial.orientation._ObservedResolver(open_raw_info_store(source['root'],reviewed_snapshot=source).snapshot())
    group=inputs['registry_group']
    snapshot=SignalRegistry(group['root'],candidate_root=ROOT/'unused_candidates').snapshot_from_refs(group['version'],tuple(group['refs']))
    if snapshot.registry_hash!=group['registry_hash']:raise ValidationError('Registry identity drift')
    raw=inputs['imported_batch']
    batch=SignalBatchResult(tuple(SignalResult.from_dict(r) for r in raw['results']),1,
        usage=AgentUsage(**raw['usage']),resolutions=tuple(RawInfoResolution.from_dict(r) for r in raw['resolutions']),
        document_fingerprints={k:tuple(v) for k,v in raw['document_fingerprints'].items()})
    cutoff=datetime.fromisoformat(sample['prediction_time'])
    for evidence in batch.results[0].supporting_evidence:
        doc=resolver.store.load(evidence.document_id,as_of=cutoff)
        if (doc.company_id!=sample['company_id'] or evidence.exact_span not in doc.content
                or evidence.timestamp!=doc.available_at):raise ValidationError('imported source literal/PIT differs')
    for fingerprint in batch.document_fingerprints[REF]:
        doc_id,content_hash=fingerprint.rsplit(':',1)
        if resolver.store.load(doc_id,as_of=cutoff).content_hash!=content_hash:raise ValidationError('fingerprint source drift')
    reflect_usage=AgentUsage();predict_usage=AgentUsage()

    class Controller(LLMResearchController):
        def initialize(self,plan,basic):
            model,lineage=project_basic_info_bundle(resolver.observed_bundle)
            actual={'plan':plan.to_dict(),'bundle':resolver.observed_bundle.to_dict(),'model_context':basic,
                'projection_lineage':lineage,'evaluation_context':self.evaluation_context,
                'evaluation_anchor':self.evaluation_anchor,'computed_metrics':self.computed_metrics,
                'document_channel_set_by_core':self.document_channel is not None}
            if model!=basic or canonical_json_hash(actual)!=canonical_json_hash(inputs['bootstrap']):
                raise ValidationError('native bootstrap differs from accepted H_init')
            save('bootstrap',actual)
            step=inputs['accepted_initial_step']
            return AgentStep(ResearchState.from_dict(step['state']),AgentUsage(**step['usage']),step['metadata'])
        def reflect(self,plan,state,actual_batch):
            nonlocal reflect_usage
            save('reflect-input',{'state':state.to_dict(),'results':[r.to_dict() for r in actual_batch.results],
                'selections':[s.to_dict() for s in self.reflection_selections],
                'request_budget':self.request_token_budget,'must_finalize':self.reflection_must_finalize,
                'termination_trigger':str(self.reflection_termination_trigger)})
            step=super().reflect(plan,state,actual_batch);reflect_usage=step.usage
            save('accepted-reflect',{'state':step.value.to_dict(),'usage':asdict(step.usage),'metadata':step.metadata})
            return step

    class Selector:
        def set_request_token_budget(self,value):self.request_token_budget=value
        def select(self,needs,registry,prior_fingerprints,prior_results=None,**kwargs):
            if tuple(needs)!=tuple(inputs['accepted_initial_step']['state']['next_information_needs']):
                raise ValidationError('original needs changed before consumer')
            save('declared-context-input',{'intent':inputs['context_intent'],'prior_selection_usage':inputs['selection_usage'],
                'scope':'controlled consumer input; not a fresh route or application authorization'})
            return AgentStep((SignalSelectionDecision.from_dict(inputs['context_intent']),),AgentUsage(**inputs['selection_usage']))

    class ImportedExecutor(SignalExecutor):
        def execute_batch(self,refs,**kwargs):
            if tuple(refs)!=(REF,) or kwargs['company_id']!=sample['company_id'] or kwargs['as_of']!=cutoff:
                raise ValidationError('unexpected completed-result import')
            save('imported-batch',raw)
            return batch

    class Predictor(LLMBlindPredictor):
        def predict(self,context):
            nonlocal predict_usage
            save('predictor-input',{'context':context,'request_budget':self.request_token_budget})
            step=super().predict(context);predict_usage=step.usage
            save('accepted-prediction',{'prediction':step.value.to_dict(),'usage':asdict(step.usage),'metadata':step.metadata})
            return step
        def reflect(self,*args,**kwargs):return forbidden()

    def sink(company_id,prediction_time,context,prediction):
        save('prediction-sink',{'company_id':company_id,'prediction_time':prediction_time.isoformat(),
            'context':context,'prediction':prediction.to_dict(),
            'combined_case_usage':asdict(PRIOR+reflect_usage+predict_usage),'labels':0,'new_Signal_calculations':0})
        raise ConsumerBoundary()

    identity=sample['identity']
    with client.anonymous_case(aliases=tuple(identity['identity_aliases']),company_id=sample['company_id'],ticker=identity['ticker']):
        execute_information_plan(plan=InformationPlan.from_dict(inputs['plan']),company_id=sample['company_id'],
            company_basic_source=identity,prediction_time=cutoff,signal_registry=snapshot,
            signal_executor=ImportedExecutor(snapshot,raw_info_store=resolver.store,resolver=resolver),
            controller=Controller(client),signal_agent=Selector(),predictor=Predictor(client),
            prediction_sink=sink,ground_truth_provider=forbidden,limits=RuntimeLimits(**contract['runtime_limits']))
    raise ValidationError('native consumer returned without persistence boundary')


def client_for(contract,*,input_only=False):
    """Use exact native inboxes with a shared three-new-response ceiling."""
    def observe(event):
        if event.get('event_type')!='request_ready':return
        if not (event['stage'].startswith('research_controller_reflect') or event['stage'].startswith('blind_predictor_predict')):
            forbidden()
        if input_only:
            save('request-ready',dict(event));raise InputOnlyBoundary()
    return StructuredRoleClient(registration=get_model('independent-subagent'),contract=StageContract(contract),workspace=ROOT,
        ledger=ExternalAttemptLedger(ROOT/'unused_external.json',max_attempts=1,max_total_cost=.01),
        local_role_exchange=LocalRoleExchange(ROOT/'exchange',max_calls=3),allow_external=False,environ={},on_progress=observe)


def preflight():
    """Reconstruct the full native input path without any production answer."""
    global ROOT
    ROOT=BASE/'preflight'
    if ROOT.exists():raise ValidationError('input-only destination already exists')
    ROOT.mkdir(parents=True)
    with guards():
        inputs,_protected=authorities()
        contract={'limits':{**initial.LIMITS,'max_local_role_calls':3},'runtime_limits':read_json(ROUTING/'contract.json')['runtime_limits']}
        try:native(inputs,contract,client_for(contract,input_only=True))
        except InputOnlyBoundary:return {'state':'input_only_captured','inboxes':len(list(ROOT.rglob('inbox/*.json')))}
    raise ValidationError('preflight missed input-only boundary')


def resume():
    """Advance only this uncompleted frozen consumer until pending or sink."""
    if any((ROOT/f).exists() for f in ('failure.json','completion.json')):raise ValidationError('terminal consumer cannot reenter')
    inputs,contract=verify()
    try:
        with guards():native(inputs,contract,client_for(contract))
    except LocalRoleRequestPending as pending:
        verify();return {'state':'pending',**pending.pending}
    except ConsumerBoundary:
        verify();value={'state':'completed','scope':contract['scope'],'prediction_sink':binding(ROOT/'prediction-sink.json'),
            'receipts':len(list((ROOT/'exchange/receipts').glob('*.json'))),'external_API':0,'labels':0,
            'semantic_acceptance':'requires independent review; no round/cycle commit'}
        save('completion',value);return value
    except BaseException as error:
        save('failure',{'type':type(error).__name__,'error':str(error),'traceback':traceback.format_exc()});raise


def main():
    """Use fixed preflight/formal roots without exposing rename controls."""
    import json
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('preflight','prepare','resume','submit'))
    parser.add_argument('--expectations',type=Path);parser.add_argument('--request-hash');parser.add_argument('--agent-id')
    args=parser.parse_args()
    if args.action=='preflight':value=preflight()
    elif args.action=='prepare':value=prepare(args.expectations)
    elif args.action=='resume':value=resume()
    else:
        verify()
        if any((ROOT/f).exists() for f in ('failure.json','completion.json')):raise ValidationError('terminal consumer cannot submit')
        value=LocalRoleExchange(ROOT/'exchange',max_calls=3).submit(args.request_hash,agent_id=args.agent_id or '')
    print(json.dumps(value))


if __name__=='__main__':main()
