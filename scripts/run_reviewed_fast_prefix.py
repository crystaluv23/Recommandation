#!/usr/bin/env python3
"""Freeze and resume the native blind prefix, stopping before any outcome read."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime
import fcntl
import json
from pathlib import Path
import socket
from types import SimpleNamespace

from diagnose_executed_answer_scope import StageContract, binding, read_json
from run_reviewed_signal_stage import REPO, REGISTRY, COMPANY, IDENTITY, _save_exact
from stock_opportunity_agent.artifacts import atomic_write_json, canonical_json_hash
from stock_opportunity_agent.data.reviewed_snapshot import open_raw_info_store
from stock_opportunity_agent.data.resolution import EvidenceResolver
from stock_opportunity_agent.llm import get_model
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_core import (
    EvolutionControlFlow, InformationPlan, RuntimeLimits, default_information_plan,
    execute_information_plan, project_basic_info_bundle, runtime_termination_view,
)
from stock_opportunity_agent.research.evolution_control import _parallel_decision_roles
from stock_opportunity_agent.research.evolution_plan_roles import LLMResearchController
from stock_opportunity_agent.research.evolution_signal_roles import StructuredLLMSignalRunner
from stock_opportunity_agent.research.evolution_transport import StructuredRoleClient, ExternalAttemptLedger
from stock_opportunity_agent.research.local_role_exchange import LocalRoleExchange, LocalRoleRequestPending, LocalRoleBudgetExhausted
from stock_opportunity_agent.signal_library import SignalRegistry, SignalExecutor

SOURCE_INPUTS = REPO / 'runs/diagnostics/reviewed_market_snapshot_20261019_v4/input_manifest.json'
LIMITS = RuntimeLimits(max_signal_rounds=2,max_signal_calls=4,max_llm_calls=24,max_tokens=256000,
    finalization_token_reserve=64000,max_signals_per_round=4,max_llm_signals_per_round=2)
NON_RUNTIME_FILES = {'progress.json','completion.json','execution_summary.json','independent-review.json',
                     '.prefix.lock','.dispatch.lock'}


class BlindPrefixBoundaryReached(EvolutionControlFlow):
    """The native sink succeeded; no ground truth was read or returned."""


def _code_bindings():
    return [binding(path) for path in sorted([*(REPO/'src').rglob('*.py'),Path(__file__),
        REPO/'scripts/run_reviewed_signal_stage.py', REPO/'scripts/diagnose_executed_answer_scope.py',
        REPO/'spec/scripts/run_reviewed_fast_prefix.md'])]


def _bootstrap(store, sample):
    bundle = EvidenceResolver(store.snapshot()).resolve_basic_info(
        InformationPlan.from_dict(sample['plan']).basic_info_policy.requests,
        company_id=sample['company_id'],identity=sample['identity'],as_of=datetime.fromisoformat(sample['prediction_time']))
    model,lineage=project_basic_info_bundle(bundle)
    return {'bundle':bundle.to_dict(),'model_context':model,'lineage':lineage}


def prepare(root: Path, expectations: Path):
    """Freeze exact native inputs and an isolated predeclared acceptance oracle."""
    if root.exists(): raise ValidationError('prefix destination must be new')
    source=read_json(SOURCE_INPUTS)['reviewed_source_snapshot']
    store=open_raw_info_store(source['root'],reviewed_snapshot=source)
    registry=SignalRegistry(REGISTRY).freeze()
    sample={'sample_id':'s01','company_id':COMPANY,'identity':IDENTITY,
        'prediction_time':'2025-09-30T00:00:00+00:00','plan':default_information_plan().to_dict()}
    expected=read_json(expectations)
    if expected.get('fixed_denominator')!=1 or expected.get('sample',{}).get('sample_id')!='s01':
        raise ValidationError('independent oracle must retain one neutral sample')
    inputs={'sample':sample,'reviewed_source_snapshot':source,'registry_root':str(REGISTRY),
        'registry_version':registry.version,'registry_hash':registry.registry_hash,
        'learning_hash':registry.learning_hash,'registry_refs':[spec.ref for spec in registry.specs]}
    preflight=_bootstrap(store,sample)
    contract={'schema_version':'reviewed-native-blind-prefix-v1','backend':'independent-subagent',
        'scope':'native execute_information_plan through durable prediction_sink, before outcome read',
        'fixed_denominator':1,'max_local_calls':32,'parallel_jev_decisions':False,
        'runtime_limits':LIMITS.to_dict(),'external_llm_calls_authorized':0,'readonly_data_requests_authorized':0,
        'actual_model_version':None,'model_selection':'inherited_host_default_precise_version_unknown',
        'actual_host_tokens':None,'actual_host_cost':None,
        'cost_guard_note':'native accounting guard is not paid authorization; actual host cost unknown',
        'input_hash':canonical_json_hash(inputs),'expectations_hash':canonical_json_hash(expected),
        'preflight_hash':canonical_json_hash(preflight),'limits':{'max_request_tokens':131072,
            'max_structured_corrections':1,'max_local_role_calls':32,'structured_reasoning_token_reserve':0}}
    manifest={'schema_version':'reviewed-native-blind-prefix-freeze-v1','contract_hash':canonical_json_hash(contract),
        'code_files':_code_bindings(),'originals':[binding(SOURCE_INPUTS),binding(expectations)],
        'registry_files':[binding(path) for path in sorted(REGISTRY.rglob('*')) if path.is_file()],
        'completed_fast_round':False,'full_dataset_readiness_proven':False}
    manifest['manifest_hash']=canonical_json_hash(manifest)
    for name,value in (('inputs',inputs),('expectations',expected),('preflight',preflight),('contract',contract),('manifest',manifest)):
        atomic_write_json(root/(name+'.json'),value)
    return {'manifest_hash':manifest['manifest_hash'],'fixed_denominator':1,'role_answers':0}


def _verify(root):
    manifest=read_json(root/'manifest.json'); digest=manifest.pop('manifest_hash')
    if canonical_json_hash(manifest)!=digest: raise ValidationError('prefix manifest changed')
    for row in manifest['code_files']+manifest['originals']+manifest['registry_files']:
        binding(Path(row['path']),row['sha256'])
    inputs,contract=read_json(root/'inputs.json'),read_json(root/'contract.json')
    if (canonical_json_hash(contract)!=manifest['contract_hash']
        or canonical_json_hash(inputs)!=contract['input_hash']
        or canonical_json_hash(read_json(root/'expectations.json'))!=contract['expectations_hash']
        or canonical_json_hash(read_json(root/'preflight.json'))!=contract['preflight_hash']):
        raise ValidationError('prefix frozen input/contract/oracle/preflight changed')
    source=inputs['reviewed_source_snapshot']
    store=open_raw_info_store(source['root'],reviewed_snapshot=source)
    registry=SignalRegistry(inputs['registry_root']).freeze()
    if (registry.registry_hash!=inputs['registry_hash'] or registry.learning_hash!=inputs['learning_hash']
        or registry.version!=inputs['registry_version'] or [spec.ref for spec in registry.specs]!=inputs['registry_refs']):
        raise ValidationError('prefix Registry specs/learning identity changed')
    return digest,inputs,contract,store,registry


def _immutable_artifacts(root):
    return [binding(path) for path in sorted(root.rglob('*'))
            if path.is_file() and path.name not in NON_RUNTIME_FILES]


def _value(value):
    if hasattr(value,'to_dict'): return value.to_dict()
    if isinstance(value,(list,tuple)): return [_value(item) for item in value]
    return value


def _observe(instance, method, name, root, client):
    original=getattr(instance,method); counter=0
    def call(*args,**kwargs):
        nonlocal counter
        position=counter; counter+=1; start=len(client.request_hash_trace)
        result=original(*args,**kwargs)
        if hasattr(result,'usage') and hasattr(result,'value'):
            record={'value':_value(result.value),'metadata':dict(result.metadata),'usage':asdict(result.usage)}
        else:
            record=result.to_dict()
        record['request_hashes']=client.request_hash_trace[start:]
        _save_exact(root/'observations'/f'{name}_{position:02}.json',record)
        return result
    setattr(instance,method,call)


def _completed_restore(root,manifest_hash,contract):
    completion=read_json(root/'completion.json'); digest=completion.pop('completion_hash')
    if (canonical_json_hash(completion)!=digest or completion['manifest_hash']!=manifest_hash
        or completion['immutable_artifacts']!=_immutable_artifacts(root)):
        raise ValidationError('completed blind-prefix artifacts changed or missing')
    exchange=LocalRoleExchange(root/'exchange',max_calls=contract['max_local_calls'])
    for path in sorted((root/'requests').glob('*.json')):
        record=read_json(path)
        if canonical_json_hash(record['request'])!=record['request_hash']:
            raise ValidationError('completed request hash changed')
        exchange.receive(record['request'],accounting_tokens=0,allow_dispatch=False)
    return {**completion['result'],'restored_without_execution':True,'immutable_artifacts_unchanged':True}


def _execute(root,manifest_hash,inputs,contract,store,registry):
    if (root/'completion.json').exists(): return _completed_restore(root,manifest_hash,contract)
    sample=inputs['sample']; expected_preflight=read_json(root/'preflight.json')
    if _bootstrap(store,sample)!=expected_preflight: raise ValidationError('native bootstrap changed')
    exchange=LocalRoleExchange(root/'exchange',max_calls=contract['max_local_calls'])
    client=StructuredRoleClient(registration=get_model('independent-subagent'),contract=StageContract(contract),
        workspace=root,local_role_exchange=exchange,
        ledger=ExternalAttemptLedger(root/'unused_external_attempts.json',max_attempts=1,max_total_cost=0.01),
        allow_external=False,environ={})
    controller=LLMResearchController(client)
    selector,predictor=_parallel_decision_roles(client,parallel_jev_decisions=False,environ={})
    runner=StructuredLLMSignalRunner(client)
    runner.set_identity_cases((SimpleNamespace(case_id='s01',company_id=sample['company_id'],basic_info=sample['identity']),))
    executor=SignalExecutor(registry,store.snapshot(),resolver=EvidenceResolver(store.snapshot()),llm_runner=runner)
    for instance,method,name in ((controller,'initialize','initialize'),(controller,'reflect','reflect'),
        (selector,'select','routing'),(executor,'execute_batch','signal_group'),(predictor,'predict','prediction')):
        _observe(instance,method,name,root,client)
    saved=None
    def sink(company,instant,context,prediction):
        nonlocal saved
        runtime_termination_view(context,require_ready=True)
        record={'company_id':company,'prediction_time':instant.isoformat(),
                'final_context':dict(context),'prediction':prediction.to_dict()}
        _save_exact(root/'prediction.json',record)
        if read_json(root/'prediction.json')!=record: raise ValidationError('prediction sink readback mismatch')
        saved=record
        return str((root/'prediction.json').resolve())
    def before_outcomes(company):
        if saved is None or read_json(root/'prediction.json')!=saved:
            raise ValidationError('ground-truth boundary preceded durable prediction')
        raise BlindPrefixBoundaryReached('durable prediction verified; no ground truth read or returned')
    result={'fixed_denominator':1,'sample_id':'s01','pending':[], 'external_llm_calls':0,
        'readonly_data_requests':0,'actual_host_tokens':None,'actual_host_cost':None,
        'completed_fast_round':False,'completed_trajectory':False,'engineering_mvp_closed':False}
    try:
        with client.anonymous_case(aliases=tuple(sample['identity']['identity_aliases']),
            company_id=sample['company_id'],ticker=sample['identity']['ticker']):
            execute_information_plan(plan=InformationPlan.from_dict(sample['plan']),company_id=sample['company_id'],
                case_id=sample['sample_id'],company_basic_source=sample['identity'],
                prediction_time=datetime.fromisoformat(sample['prediction_time']),signal_registry=registry,
                signal_executor=executor,controller=controller,signal_agent=selector,predictor=predictor,
                prediction_sink=sink,ground_truth_provider=before_outcomes,limits=RuntimeLimits(**contract['runtime_limits']))
        raise AssertionError('blind prefix must stop before any GroundTruth return')
    except BlindPrefixBoundaryReached:
        result.update(status='prediction_persisted_before_labels_requires_independent_review',
            prediction_ref=str((root/'prediction.json').resolve()),ground_truth_reads=0,
            apply_executed=any((root/'observations').glob('signal_group_*.json')),
            reflect_executed=any((root/'observations').glob('reflect_*.json')))
        result['independent_receipts']=len(list((root/'exchange/receipts').glob('*.json')))
        completion={'manifest_hash':manifest_hash,'result':result,'immutable_artifacts':_immutable_artifacts(root)}
        completion['completion_hash']=canonical_json_hash(completion)
        atomic_write_json(root/'completion.json',completion)
    except LocalRoleRequestPending as exc:
        result.update(status='pending_independent_role',pending=[{'sample_id':'s01',**exc.pending}])
    except LocalRoleBudgetExhausted as exc:
        result.update(status='control_budget_stopped',error=str(exc))
    except EvolutionControlFlow as exc:
        result.update(status='control_rejected',error_type=type(exc).__name__,error=str(exc))
    except Exception as exc:
        failure={'error_type':type(exc).__name__,'error':str(exc)}
        _save_exact(root/'failure.json',failure)
        result.update(status='prefix_failed',**failure)
    result['independent_receipts']=len(list((root/'exchange/receipts').glob('*.json')))
    atomic_write_json(root/'progress.json',result)
    return result


def resume(root: Path):
    """Serial native re-entry; a completed checkpoint restores without execution."""
    with (root/'.prefix.lock').open('a+') as lock:
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX)
        return _execute(root,*_verify(root))


def main():
    """Prepare, resume or submit the same public exchange without network access."""
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True); parser.add_argument('--expectations',type=Path)
    parser.add_argument('--request-hash'); parser.add_argument('--agent-id')
    modes=parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--prepare',action='store_true'); modes.add_argument('--resume',action='store_true')
    modes.add_argument('--submit',action='store_true'); args=parser.parse_args(); root=args.root.resolve()
    def forbidden(*_args,**_kwargs): raise AssertionError('network forbidden in reviewed blind prefix')
    socket.socket=forbidden
    if args.prepare:
        if args.expectations is None: parser.error('--prepare requires --expectations')
        value=prepare(root,args.expectations.resolve())
    elif args.submit:
        if not args.request_hash or not args.agent_id: parser.error('--submit requires request hash and actual agent id')
        _digest,_inputs,contract,_store,_registry=_verify(root)
        value=LocalRoleExchange(root/'exchange',max_calls=contract['max_local_calls']).submit(args.request_hash,agent_id=args.agent_id)
    else: value=resume(root)
    print(json.dumps(value,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
