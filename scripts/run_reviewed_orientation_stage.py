#!/usr/bin/env python3
"""Freeze native Plan proposal and three real-core bootstrap/H_init boundaries."""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime
import fcntl
import json
from pathlib import Path
import socket
from types import SimpleNamespace

from diagnose_executed_answer_scope import StageContract, binding, read_json
from run_reviewed_signal_stage import REPO, REGISTRY, IDENTITY, _save_exact
from run_reviewed_posthoc_stage import _verified_responses
from stock_opportunity_agent.artifacts import atomic_write_json, canonical_json_hash
from stock_opportunity_agent.data.reviewed_snapshot import open_raw_info_store
from stock_opportunity_agent.data.resolution import EvidenceResolver
from stock_opportunity_agent.llm import get_model
from stock_opportunity_agent.llm.agent import AgentUsage
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.basic_info_orientation import (
    MENU_VERSION, make_orientation_request, orientation_menu,
)
from stock_opportunity_agent.research.evolution_core import (
    BasicInfoPolicy, DEFAULT_EVOLUTION_PRIORS, EvolutionControlFlow, InformationPlan, RuntimeLimits, RuntimeBudgetExceeded,
    _consume_model_step, default_information_plan, execute_information_plan,
    project_basic_info_bundle,
)
from stock_opportunity_agent.research.evolution_plan_roles import (
    LLMInformationPlanProposer, LLMResearchController,
)
from stock_opportunity_agent.research.evolution_transport import StructuredRoleClient, ExternalAttemptLedger
from stock_opportunity_agent.research.local_role_exchange import (
    LocalRoleExchange, LocalRoleRequestPending, LocalRoleBudgetExhausted,
)
from stock_opportunity_agent.signal_library import SignalExecutor, SignalRegistry

SOURCE_INPUTS = {
    'bmbl': REPO/'runs/diagnostics/reviewed_market_snapshot_20261019_v4/input_manifest.json',
    'enb': REPO/'runs/diagnostics/reviewed_enb_source_snapshot_20261020_v1/input_manifest.json',
}
CAPABILITIES = ('sec_filing', 'prices')
LIMITS = RuntimeLimits(max_signal_rounds=1, max_signal_calls=1, max_llm_calls=8,
    max_tokens=256000, finalization_token_reserve=64000,
    max_signals_per_round=4, max_llm_signals_per_round=2)
SIDECARS = {'progress.json','completion.json','execution_summary.json','independent-review.json'}
LOCKS = {'.orientation.lock','.dispatch.lock'}


class InitialBoundary(EvolutionControlFlow):
    """The native initial step and its real budget are accepted; no tail runs."""


def _code_bindings():
    return [binding(p) for p in sorted([*(REPO/'src').rglob('*.py'), Path(__file__),
        REPO/'scripts/run_reviewed_signal_stage.py', REPO/'scripts/run_reviewed_posthoc_stage.py',
        REPO/'scripts/run_reviewed_fast_prefix.py', REPO/'scripts/diagnose_executed_answer_scope.py',
        REPO/'spec/scripts/run_reviewed_orientation_stage.md'])]


def _files(root, *, runtime=False):
    return [binding(p) for p in sorted(root.rglob('*')) if p.is_file()
        and p.name not in LOCKS and (not runtime or p.name not in SIDECARS)]


def _nested_bindings(value):
    result = []
    if isinstance(value, dict):
        if isinstance(value.get('path'), str) and isinstance(value.get('sha256'), str):
            result.append(binding(Path(value['path']), value['sha256']))
        for item in value.values(): result.extend(_nested_bindings(item))
    elif isinstance(value, list):
        for item in value: result.extend(_nested_bindings(item))
    return result


def _source_inputs():
    sources, originals = {}, []
    for key, path in SOURCE_INPUTS.items():
        data = read_json(path); source = data['reviewed_source_snapshot']
        store = open_raw_info_store(source['root'], reviewed_snapshot=source)
        if getattr(store, 'acquisition_allowed', False):
            raise ValidationError('orientation source view must prohibit acquisition')
        sources[key] = source
        originals += [binding(path), *_files(Path(source['root']))]
        originals += _nested_bindings(data)
        if 'source_review' in data:
            originals += _nested_bindings(read_json(Path(data['source_review']['path'])))
    unique = {row['path']: row for row in originals}
    return sources, [unique[key] for key in sorted(unique)]


def prepare(root: Path, expectations: Path):
    """Freeze sources, exact Registry, manual seed and isolated independent oracle."""
    if root.exists(): raise ValidationError('orientation destination must be new')
    expected = read_json(expectations)
    if (expected.get('fixed_denominator') != {'proposer':1,'H_init':3}
        or expected.get('proposer_case',{}).get('sample_id') != 'p01'
        or [r['sample_id'] for r in expected.get('H_init_cases',[])] != ['h01','h02','h03']):
        raise ValidationError('orientation oracle must retain one proposer and three initial cases')
    sources, originals = _source_inputs()
    registry = SignalRegistry(REGISTRY).freeze()
    default = default_information_plan()
    seed = replace(default, basic_info_policy=BasicInfoPolicy(tuple(
        make_orientation_request(a) for a in ('operating_report','market_backbone'))))
    inputs = {'sources':sources,'seed_plan':seed.to_dict(),
        'proposer_prior':DEFAULT_EVOLUTION_PRIORS.propose_plan,
        'proposer_capabilities':list(CAPABILITIES),'meta_info':[],
        'proposer_menu':orientation_menu(CAPABILITIES),
        'registry_root':str(REGISTRY),'registry_version':registry.version,
        'registry_hash':registry.registry_hash,'learning_hash':registry.learning_hash,
        'registry_refs':[spec.ref for spec in registry.specs],
        'samples':[
            {'sample_id':'h01','source':'bmbl','company_id':'cik_0001830043','identity':IDENTITY,
             'prediction_time':'2025-09-30T00:00:00+00:00','plan_source':'p01'},
            {'sample_id':'h02','source':'enb','company_id':'cik_0000895728',
             'identity':{'ticker':'ENB','company_name':'Enbridge Inc.',
                 'identity_aliases':['Enbridge','Enbridge Inc.','ENB']},
             'prediction_time':'2025-09-30T00:00:00+00:00','plan':default.to_dict()},
            {'sample_id':'h03','source':'bmbl','company_id':'cik_0001830043','identity':IDENTITY,
             'prediction_time':'2025-07-01T00:00:00+00:00','plan':default.to_dict()}]}
    contract = {'schema_version':'reviewed-native-orientation-stage-v1','backend':'independent-subagent',
        'scope':'one native proposer and three actual core initial-state boundaries; no tail/labels',
        'menu_version':MENU_VERSION,'fixed_denominator':{'proposer':1,'H_init':3},
        'max_local_calls':24,'parallel_jev_decisions':False,'runtime_limits':LIMITS.to_dict(),
        'proposer_memory_requests_max':3,'proposer_meta_info_empty':True,
        'H_init_document_reads':'not_supported_by_native_initialize',
        'external_llm_calls_authorized':0,'readonly_data_requests_authorized':0,
        'actual_host_tokens':None,'actual_host_cost':None,'actual_model_version':None,
        'cost_guard_note':'zero external API accounting is not paid authorization; host cost unknown',
        'model_selection':'inherited_host_default_precise_version_unknown',
        'limits':{'max_request_tokens':131072,'max_structured_corrections':1,
            'max_local_role_calls':24,'structured_reasoning_token_reserve':0},
        'input_hash':canonical_json_hash(inputs),'expectations_hash':canonical_json_hash(expected)}
    manifest = {'schema_version':'reviewed-native-orientation-freeze-v1',
        'contract_hash':canonical_json_hash(contract),'code_files':_code_bindings(),
        'originals':originals+[binding(expectations)],
        'registry_files':[binding(p) for p in sorted(REGISTRY.rglob('*')) if p.is_file()],
        'completed_fast_round':False,'labels_read':False,'slow_source_published':False}
    manifest['manifest_hash'] = canonical_json_hash(manifest)
    for name,value in (('inputs',inputs),('expectations',expected),('contract',contract),('manifest',manifest)):
        atomic_write_json(root/(name+'.json'),value)
    return {'manifest_hash':manifest['manifest_hash'],'fixed_denominator':contract['fixed_denominator'],
        'max_local_calls':24,'new_role_answers':0}


def _verify(root):
    manifest=read_json(root/'manifest.json'); digest=manifest.pop('manifest_hash')
    contract=read_json(root/'contract.json'); inputs=read_json(root/'inputs.json')
    if (canonical_json_hash(manifest)!=digest or canonical_json_hash(contract)!=manifest['contract_hash']
        or canonical_json_hash(inputs)!=contract['input_hash']
        or canonical_json_hash(read_json(root/'expectations.json'))!=contract['expectations_hash']):
        raise ValidationError('orientation frozen manifest/contract/input/oracle changed')
    for row in manifest['code_files']+manifest['originals']+manifest['registry_files']:
        binding(Path(row['path']),row['sha256'])
    registry=SignalRegistry(Path(inputs['registry_root'])).freeze()
    if (registry.version!=inputs['registry_version'] or registry.registry_hash!=inputs['registry_hash']
        or registry.learning_hash!=inputs['learning_hash']
        or [s.ref for s in registry.specs]!=inputs['registry_refs']):
        raise ValidationError('orientation exact Registry identity changed')
    for source in inputs['sources'].values():
        open_raw_info_store(source['root'],reviewed_snapshot=source)
    return digest,inputs,contract,registry


def _tripwire(*_args, **_kwargs):
    raise AssertionError('orientation boundary must not enter routing/Signal/Reflect/Predictor/sink/truth')


def _client(root, contract, events, sample_id=None):
    ledger=ExternalAttemptLedger(root/'unused_external_attempts.json',max_attempts=1,max_total_cost=0.01)
    def progress(event):
        if event.get('event_type') == 'request_ready':
            request = read_json(Path(event['request_path']))['request']
            reservation = len(json.dumps(request['messages'], ensure_ascii=False,
                sort_keys=True, separators=(',', ':')).encode('utf-8')) + request['max_output_tokens']
            if reservation > contract['limits']['max_request_tokens']:
                raise RuntimeBudgetExceeded('orientation single request exceeds frozen reservation ceiling')
        if any(word in str(event.get('event_type','')) for word in ('validat','correct','fallback','normaliz','mechanic')):
            events.append({'sample_id':sample_id,'event':deepcopy(dict(event))})
    return StructuredRoleClient(registration=get_model('independent-subagent'),contract=StageContract(contract),
        workspace=root,ledger=ledger,local_role_exchange=LocalRoleExchange(root/'exchange',max_calls=24),
        allow_external=False,environ={},on_progress=progress)


class _ObservedResolver(EvidenceResolver):
    def resolve_basic_info(self, *args, **kwargs):
        """Retain the exact original bundle and return the same object to native core."""
        value=super().resolve_basic_info(*args, **kwargs)
        self.observed_bundle=value
        return value


def _run_initial(root, sample, plan, inputs, contract, registry, client):
    path=root/'samples'/sample['sample_id']
    source=inputs['sources'][sample['source']]
    resolver=_ObservedResolver(open_raw_info_store(source['root'],reviewed_snapshot=source).snapshot())
    limits=RuntimeLimits(**contract['runtime_limits'])
    class Controller(LLMResearchController):
        def initialize(self, actual_plan, basic_info):
            """Observe native inputs/step, enforce its real budget, then stop the tail."""
            model,lineage=project_basic_info_bundle(resolver.observed_bundle)
            if model!=basic_info or actual_plan.to_dict()!=plan.to_dict():
                raise ValidationError('native orientation input differs from exact Plan/bundle')
            _save_exact(path/'bootstrap.json',{'plan':actual_plan.to_dict(),
                'bundle':resolver.observed_bundle.to_dict(),'model_context':basic_info,
                'projection_lineage':lineage,'evaluation_context':self.evaluation_context,
                'evaluation_anchor':self.evaluation_anchor,'computed_metrics':self.computed_metrics,
                'document_channel_set_by_core':self.document_channel is not None})
            step=super().initialize(actual_plan,basic_info)
            value={'state':step.value.to_dict(),'usage':asdict(step.usage),
                'metadata':step.metadata,'request_hashes':list(client.request_hash_trace)}
            _save_exact(path/'parsed_step.json',value)
            budget=_consume_model_step(AgentUsage(),step.usage,limits)
            _save_exact(path/'initial_state.json',{**value,'native_budget_usage':asdict(budget)})
            raise InitialBoundary()
        def reflect(self,*args,**kwargs): return _tripwire(*args,**kwargs)
    controller=Controller(client)
    identity=sample['identity']
    with client.anonymous_case(aliases=tuple(identity['identity_aliases']),
            company_id=sample['company_id'],ticker=identity['ticker']):
        execute_information_plan(plan=plan,company_id=sample['company_id'],company_basic_source=identity,
            prediction_time=datetime.fromisoformat(sample['prediction_time']),signal_registry=registry,
            signal_executor=SignalExecutor(registry,raw_info_store=resolver.store,resolver=resolver),
            controller=controller,signal_agent=SimpleNamespace(select=_tripwire),
            predictor=SimpleNamespace(predict=_tripwire,reflect=_tripwire),
            prediction_sink=_tripwire,ground_truth_provider=_tripwire,limits=limits)
    raise ValidationError('native execution returned without InitialBoundary')


def _execute(root, digest, inputs, contract, registry):
    if (root/'completion.json').exists():
        saved=read_json(root/'completion.json'); hashed=saved.pop('completion_hash')
        if (canonical_json_hash(saved)!=hashed or saved['manifest_hash']!=digest
            or saved['immutable_artifacts']!=_files(root,runtime=True)):
            raise ValidationError('completed orientation artifacts changed/missing/extra')
        _verified_responses(root,contract['max_local_calls'])
        return saved['result']
    pending=[]; outcomes=[]; plan=None
    events_path=root/'validation_events.json'
    events=json.loads(events_path.read_text(encoding='utf-8')) if events_path.exists() else []
    if not isinstance(events,list) or any(not isinstance(event,dict) for event in events):
        raise ValidationError('orientation validation events must be an array of objects')
    client=_client(root,contract,events,'p01')
    try:
        proposer=LLMInformationPlanProposer(client,available_source_types=inputs['proposer_capabilities'])
        proposer.set_request_token_budget(contract['limits']['max_request_tokens'])
        proposed=proposer.propose(round_id=1,candidate_index=1,candidate_count=1,proposal_attempt=1,
            forbidden_plan_ids=(),parents=(InformationPlan.from_dict(inputs['seed_plan']),),
            meta_info=(),prior=inputs['proposer_prior'])
        _save_exact(root/'samples/p01/plan.json',{'plan':proposed.to_dict(),
            'request_hashes':list(client.request_hash_trace)})
        plan=proposed
        outcomes.append({'sample_id':'p01','status':'accepted_requires_independent_review'})
    except LocalRoleRequestPending as exc:
        pending.append({'sample_id':'p01',**exc.pending})
    except LocalRoleBudgetExhausted:
        outcomes.append({'sample_id':'p01','status':'local_budget_exhausted'})
    except RuntimeBudgetExceeded as exc:
        outcomes.append({'sample_id':'p01','status':'case_or_request_budget_exhausted','error':str(exc)})
    except Exception as exc:
        outcomes.append({'sample_id':'p01','status':'stage_failed','error_type':type(exc).__name__,'error':str(exc)})
    for sample in inputs['samples']:
        if sample['sample_id']=='h01' and plan is None:
            waiting=any(row['sample_id']=='p01' for row in pending)
            outcomes.append({'sample_id':'h01','status':'awaiting_proposer' if waiting else 'blocked_by_proposer'})
            continue
        client=_client(root,contract,events,sample['sample_id'])
        try:
            actual_plan=plan if sample['sample_id']=='h01' else InformationPlan.from_dict(sample['plan'])
            _run_initial(root,sample,actual_plan,inputs,contract,registry,client)
        except InitialBoundary:
            outcomes.append({'sample_id':sample['sample_id'],'status':'accepted_requires_independent_review'})
        except LocalRoleRequestPending as exc:
            pending.append({'sample_id':sample['sample_id'],**exc.pending})
        except LocalRoleBudgetExhausted:
            outcomes.append({'sample_id':sample['sample_id'],'status':'local_budget_exhausted'})
        except RuntimeBudgetExceeded as exc:
            outcomes.append({'sample_id':sample['sample_id'],'status':'case_or_request_budget_exhausted','error':str(exc)})
        except Exception as exc:
            outcomes.append({'sample_id':sample['sample_id'],'status':'stage_failed','error_type':type(exc).__name__,'error':str(exc)})
    atomic_write_json(events_path,events)
    result={'manifest_hash':digest,'fixed_denominator':contract['fixed_denominator'],
        'pending':pending,'outcomes':outcomes,'independent_receipts':len(list((root/'exchange/receipts').glob('*.json'))),
        'external_llm_calls':0,'readonly_data_requests':0,'labels_read':False,
        'completed_fast_round':False,'engineering_mvp_closed':False}
    atomic_write_json(root/'progress.json',result)
    if len(outcomes)==4 and not pending and all(r['status']=='accepted_requires_independent_review' for r in outcomes):
        checkpoint={'manifest_hash':digest,'immutable_artifacts':_files(root,runtime=True),'result':result}
        checkpoint['completion_hash']=canonical_json_hash(checkpoint)
        atomic_write_json(root/'completion.json',checkpoint)
    return result


def resume(root: Path):
    """Resume one serial native stage; completed restore performs only validation."""
    with (root/'.orientation.lock').open('a+') as lock:
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX)
        return _execute(root,*_verify(root))


def main():
    """Prepare/resume/submit exact native exchanges with network access forbidden."""
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True);parser.add_argument('--expectations',type=Path)
    parser.add_argument('--request-hash');parser.add_argument('--agent-id')
    modes=parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--prepare',action='store_true');modes.add_argument('--resume',action='store_true')
    modes.add_argument('--submit',action='store_true');args=parser.parse_args();root=args.root.resolve()
    def forbidden(*args,**kwargs): raise AssertionError('network forbidden in orientation stage')
    socket.socket=forbidden
    if args.prepare:
        if args.expectations is None: parser.error('--prepare requires --expectations')
        result=prepare(root,args.expectations.resolve())
    elif args.submit:
        if not args.request_hash or not args.agent_id: parser.error('--submit requires hash and actual agent id')
        _,_,contract,_=_verify(root)
        result=LocalRoleExchange(root/'exchange',max_calls=contract['max_local_calls']).submit(args.request_hash,agent_id=args.agent_id)
    else: result=resume(root)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
