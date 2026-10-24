#!/usr/bin/env python3
"""Verify approved repaired classification semantics through native consumers."""
from __future__ import annotations

import argparse
import json
from contextlib import ExitStack, contextmanager
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
import socket
import traceback
from unittest.mock import patch

import run_gpre_native_initial_stage as initial
from diagnose_executed_answer_scope import StageContract, binding, read_json
from stock_opportunity_agent.artifacts import atomic_write_json, canonical_json_hash
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

import run_financial_context_consumer_stage as historical

REPO=initial.REPO
BASE=REPO/'runs/diagnostics/classification_fresh_consumer_20261024_v1'
ROOT=BASE/'stage'
SPEC=REPO/'spec/scripts/run_classification_consumer_stage.md'
REF=historical.REF
PRIOR=historical.PRIOR
HISTORY=AgentUsage(tokens=235851,llm_calls=4)
ALLOWANCE=144968
NEW_CALLS=3
AUTH=BASE/'authorization-20261025.json'
ORACLE=BASE/'independent/conditional-consumer-oracle.json'
REVIEW=BASE/'independent/approved-review-20261025/pre-dispatch.json'
PREFLIGHT=BASE/'approved-preflight-v2'
ConsumerBoundary=historical.ConsumerBoundary
InputOnlyBoundary=historical.InputOnlyBoundary
forbidden=historical.forbidden


class ApprovedAllowanceStop(EvolutionControlFlow):
    """Stop the entire diagnostic; native research finalization cannot absorb it."""


def save(name,value):
    """Preserve exact immutable artifacts in this fixed diagnostic only."""
    return _immutable(ROOT/(name+'.json'),value)


@contextmanager
def guards():
    """Forbid labels/network/Registry mutation while permitting real calculation."""
    with ExitStack() as stack:
        for owner,name in ((socket,'create_connection'),(socket.socket,'connect'),(socket.socket,'connect_ex'),
                (LabelStore,'__init__'),(LabelStore,'load'),(LabelStore,'ground_truth'),(LabelStore,'record'),
                (RawInfoStore,'append'),(ReviewedRawInfoStore,'append'),(SignalRegistry,'freeze'),
                (SignalRegistry,'register_stable'),(ExternalAttemptLedger,'reserve')):
            stack.enter_context(patch.object(owner,name,forbidden))
        yield


def code_bindings():
    """Freeze actual current production code, fixed profile and owning contract."""
    return initial.unique([*historical.code_bindings(),binding(Path(__file__)),binding(SPEC)])


def contract():
    """Retain native limits plus the independently approved extra envelope."""
    return {'schema_version':'approved-classification-consumer-v1',
        'limits':{**initial.LIMITS,'max_local_role_calls':NEW_CALLS},
        'runtime_limits':read_json(historical.ROUTING/'contract.json')['runtime_limits'],
        'scope':'same runway classification native consumer; no labels/round commit',
        'new_logical_units':ALLOWANCE,'new_role_calls':NEW_CALLS,
        'historical_usage':asdict(HISTORY),'prior_case_usage':asdict(PRIOR),
        'cumulative_ceiling':{'tokens':380819,'llm_calls':7},'fixed_denominator':1}


class Budget:
    """Bound the whole native ordered sequence before cache or role receive."""
    def __init__(self,input_only=False):
        self.requests=[]
        self.total=0
        self.input_only=input_only

    def __call__(self,event):
        if event.get('event_type')!='request_ready':return
        request=read_json(Path(event['request_path']))['request']
        stage=request['stage']
        if not (stage.startswith('research_controller_reflect') or stage.startswith('blind_predictor_predict')):
            forbidden()
        size=len(json.dumps(request['messages'],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode())+request['max_output_tokens']
        if (size>131072 or self.total+size>ALLOWANCE or len(self.requests)>=NEW_CALLS):
            raise ApprovedAllowanceStop('approved classification new-response allowance exhausted')
        entry={'request_hash':event['request_hash'],'stage':stage,'reservation':size}
        if any(row['request_hash']==entry['request_hash'] for row in self.requests):
            raise ValidationError('duplicate native request in one consumer chain')
        self.requests.append(entry)
        self.total+=size
        _immutable(ROOT/'reservations'/(entry['request_hash']+'.json'),entry)
        atomic_write_json(ROOT/'request-reservations.json',{'requests':self.requests,'total':self.total,
            'historical_cumulative_reserved':HISTORY.tokens+self.total})
        if self.input_only:
            save('request-ready',dict(event))
            raise InputOnlyBoundary()


def client_for(c,*,input_only=False):
    """Exact fresh inboxes; global extra allowance also covers corrections."""
    return StructuredRoleClient(registration=get_model('independent-subagent'),contract=StageContract(c),workspace=ROOT,
        ledger=ExternalAttemptLedger(ROOT/'unused_external.json',max_attempts=1,max_total_cost=.01),
        local_role_exchange=LocalRoleExchange(ROOT/'exchange',max_calls=NEW_CALLS),allow_external=False,environ={},on_progress=Budget(input_only))


def preflight():
    """Capture actual final-code request without creating a role inbox."""
    global ROOT
    ROOT=PREFLIGHT
    if ROOT.exists():raise ValidationError('approved preflight is single-entry')
    ROOT.mkdir(parents=True)
    with guards():
        inputs,protected=historical.authorities()
        try:native(inputs,contract(),client_for(contract(),input_only=True))
        except InputOnlyBoundary:
            initial.check(protected)
            save('result',{'state':'input_only','code_files':code_bindings(),
                'source_bindings':len(protected),'inboxes':0,'production_answers':0,
                'authorization':binding(AUTH),'oracle':binding(ORACLE)})
            return {'state':'input_only','inboxes':len(list(ROOT.rglob('inbox/*.json')))}
    raise ValidationError('preflight did not reach actual Reflect request')


def prepare():
    """Freeze only the approved fixed diagnostic after independent review."""
    if ROOT.exists():raise ValidationError('formal classification destination must be new')
    auth=read_json(AUTH)
    if auth.get('new_logical_units')!=ALLOWANCE or auth.get('new_role_calls')!=NEW_CALLS or auth.get('approved') is not True:
        raise ValidationError('explicit approved envelope differs')
    binding(Path(auth['proposal']['path']),auth['proposal']['sha256'])
    review=read_json(REVIEW)
    if review.get('dispatch_allowed') is not True:raise ValidationError('independent pre-dispatch review required')
    initial.check(review['code_files']+[review['authorization'],review['oracle']])
    pre=PREFLIGHT
    initial.check(read_json(pre/'result.json')['code_files'])
    if list(pre.rglob('inbox/*.json')):raise ValidationError('preflight dispatched')
    with guards():inputs,protected=historical.authorities()
    if inputs['bootstrap']!=read_json(pre/'bootstrap.json'):raise ValidationError('whole bootstrap differs')
    protected=initial.unique([*protected,*initial.files(pre),binding(AUTH),binding(ORACLE),binding(REVIEW),
        binding(historical.ROOT/'completion.json'),binding(historical.ROOT/'prediction-sink.json')])
    c=contract()
    manifest={'inputs_hash':canonical_json_hash(inputs),'contract_hash':canonical_json_hash(c),
        'source_files':protected,'code_files':code_bindings(),'expectations':binding(ORACLE)}
    manifest['manifest_hash']=canonical_json_hash(manifest)
    ROOT.mkdir(parents=True)
    for name,value in (('inputs',inputs),('contract',c),('manifest',manifest)):save(name,value)
    return {'state':'prepared','source_bindings':len(protected),'historical_usage':asdict(HISTORY)}


def verify():
    """Verify exact approved code/input/oracle before each pending handoff."""
    manifest=read_json(ROOT/'manifest.json');digest=manifest.pop('manifest_hash')
    inputs=read_json(ROOT/'inputs.json');c=read_json(ROOT/'contract.json')
    if digest!=canonical_json_hash(manifest) or canonical_json_hash(inputs)!=manifest['inputs_hash'] or canonical_json_hash(c)!=manifest['contract_hash'] or c!=contract():
        raise ValidationError('classification manifest or approved contract drift')
    initial.check(manifest['source_files']+manifest['code_files']+[manifest['expectations']])
    return inputs,c


def resume():
    """Reconstruct the same unfinished chain, never reopen terminal stages."""
    if any((ROOT/f).exists() for f in ('failure.json','completion.json')):raise ValidationError('terminal classification stage cannot reenter')
    inputs,c=verify()
    try:
        with guards():native(inputs,c,client_for(c))
    except LocalRoleRequestPending as pending:
        verify();return {'state':'pending',**pending.pending}
    except ConsumerBoundary:
        verify()
        value={'state':'completed','prediction_sink':binding(ROOT/'prediction-sink.json'),
            'receipts':len(list((ROOT/'exchange/receipts').glob('*.json'))),
            'usage':read_json(ROOT/'request-reservations.json'),'external_API':0,'labels':0,
            'semantic_acceptance':'requires independent actual-answer review; old0of1 unchanged'}
        save('completion',value);return value
    except BaseException as error:
        save('failure',{'type':type(error).__name__,'error':str(error),'traceback':traceback.format_exc()});raise

def native(inputs,contract,client):
    """Run actual core with a newly executed, exact legacy measurement and declaration."""
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

    class ActualExecutor(SignalExecutor):
        def execute_batch(self,refs,**kwargs):
            if tuple(refs)!=(REF,) or kwargs['company_id']!=sample['company_id'] or kwargs['as_of']!=cutoff:
                raise ValidationError('unexpected classification measurement scope')
            actual=super().execute_batch(refs,**kwargs)
            if actual.results != batch.results or actual.resolutions != batch.resolutions or actual.document_fingerprints != batch.document_fingerprints:
                raise ValidationError('fresh deterministic result differs from original strict pass')
            declaration=self.classification_contracts_for(actual.results)
            if REF not in declaration:
                raise ValidationError('actual classification declaration missing')
            save('actual-batch',{'results':[r.to_dict() for r in actual.results],
                'resolutions':[r.to_dict() for r in actual.resolutions],
                'document_fingerprints':actual.document_fingerprints,
                'classification_contracts':declaration,
                'deterministic_batches_per_reconstruction':1})
            return actual

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
            'combined_case_usage':asdict(PRIOR+reflect_usage+predict_usage),'labels':0,'deterministic_batches_per_reconstruction':1,
            'historical_cumulative_usage':asdict(HISTORY+reflect_usage+predict_usage)})
        raise ConsumerBoundary()

    identity=sample['identity']
    with client.anonymous_case(aliases=tuple(identity['identity_aliases']),company_id=sample['company_id'],ticker=identity['ticker']):
        execute_information_plan(plan=InformationPlan.from_dict(inputs['plan']),company_id=sample['company_id'],
            company_basic_source=identity,prediction_time=cutoff,signal_registry=snapshot,
            signal_executor=ActualExecutor(snapshot,raw_info_store=resolver.store,resolver=resolver),
            controller=Controller(client),signal_agent=Selector(),predictor=Predictor(client),
            prediction_sink=sink,ground_truth_provider=forbidden,limits=RuntimeLimits(**contract['runtime_limits']))
    raise ValidationError('native consumer returned without persistence boundary')



def main():
    """Expose only fixed prepare/preflight/resume/submit actions."""
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('preflight','prepare','resume','submit'))
    parser.add_argument('--request-hash');parser.add_argument('--agent-id')
    args=parser.parse_args()
    if args.action=='preflight':value=preflight()
    elif args.action=='prepare':value=prepare()
    elif args.action=='resume':value=resume()
    else:
        verify()
        if any((ROOT/f).exists() for f in ('failure.json','completion.json')):raise ValidationError('terminal classification cannot submit')
        value=LocalRoleExchange(ROOT/'exchange',max_calls=NEW_CALLS).submit(args.request_hash,agent_id=args.agent_id or '')
    print(json.dumps(value))


if __name__=='__main__':main()
