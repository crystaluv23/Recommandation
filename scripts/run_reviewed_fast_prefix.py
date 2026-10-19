#!/usr/bin/env python3
"""Freeze and resume the native blind prefix, stopping before any outcome read."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime
import fcntl
import json
import hashlib
import shutil
import subprocess
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
    AgentStep, EvolutionControlFlow, InformationPlan, RuntimeLimits, default_information_plan,
    execute_information_plan, project_basic_info_bundle, runtime_termination_view,
)
from stock_opportunity_agent.research.evolution_control import _parallel_decision_roles
from stock_opportunity_agent.research.evolution_plan_roles import LLMResearchController
from stock_opportunity_agent.research.evolution_signal_roles import StructuredLLMSignalRunner
from stock_opportunity_agent.research.evolution_transport import StructuredRoleClient, ExternalAttemptLedger
from stock_opportunity_agent.research.local_role_exchange import LocalRoleExchange, LocalRoleRequestPending, LocalRoleBudgetExhausted
from stock_opportunity_agent.signal_library import SignalRegistry, SignalExecutor, SignalBatchResult

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


def prepare(root: Path, expectations: Path, *, parent_root: Path | None = None, parent_commit: str | None = None):
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
    if parent_root is not None or parent_commit is not None:
        if parent_root is None or parent_commit is None:
            raise ValidationError('continuation requires parent root and immutable commit')
        lineage=_validate_parent(parent_root.resolve(),parent_commit,inputs,contract,expected,preflight)
        for row in lineage['copied_files']:
            destination=root/row['relative_path']
            destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(row['path'],destination)
            binding(destination,row['sha256'])
        manifest['continuation']=lineage
    manifest['manifest_hash']=canonical_json_hash(manifest)
    for name,value in (('inputs',inputs),('expectations',expected),('preflight',preflight),('contract',contract),('manifest',manifest)):
        atomic_write_json(root/(name+'.json'),value)
    return {'manifest_hash':manifest['manifest_hash'],'fixed_denominator':1,'role_answers':0}


def _verify(root):
    manifest=read_json(root/'manifest.json'); digest=manifest.pop('manifest_hash')
    if canonical_json_hash(manifest)!=digest: raise ValidationError('prefix manifest changed')
    for row in manifest['code_files']+manifest['originals']+manifest['registry_files']:
        binding(Path(row['path']),row['sha256'])
    if 'continuation' in manifest:
        lineage=manifest['continuation']
        if _immutable_artifacts(Path(lineage['parent_root']))!=lineage['parent_files']:
            raise ValidationError('continuation parent immutable inventory changed')
        for row in lineage['parent_files']:
            binding(Path(row['path']),row['sha256'])
        for row in lineage['copied_files']:
            binding(root/row['relative_path'],row['sha256'])
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


def _observation_record(result):
    """Serialize only native observed families without changing canonical names."""
    if isinstance(result,AgentStep):
        return {'value':_value(result.value),'metadata':dict(result.metadata),'usage':asdict(result.usage)}
    if isinstance(result,SignalBatchResult):
        return {'results':[item.to_dict() for item in result.results],
            'signal_calls':result.signal_calls,'usage':asdict(result.usage),
            'resolutions':[item.to_dict() for item in result.resolutions],
            'document_fingerprints':{ref:list(values) for ref,values in result.document_fingerprints.items()},
            'skipped_unchanged_refs':list(result.skipped_unchanged_refs)}
    raise ValidationError('unsupported native observation result family: '+type(result).__name__)


class _ContinuationExchange(LocalRoleExchange):
    """Reject changed inherited requests before authorizing any new dispatch."""
    def __init__(self,root,*,max_calls,inherited):
        super().__init__(root,max_calls=max_calls)
        self.inherited=tuple(inherited)
        self.position=0

    def receive(self,request,**kwargs):
        if self.position<len(self.inherited) and canonical_json_hash(request)!=self.inherited[self.position]:
            raise ValidationError('continuation changed an inherited production request')
        self.position+=1
        return super().receive(request,**kwargs)


def _validate_parent(parent,commit,inputs,contract,expected,preflight):
    """Bind the failed parent and verify its exact historical role responses."""
    if len(commit)!=40 or any(ch not in '0123456789abcdef' for ch in commit):
        raise ValidationError('parent commit must be an exact immutable 40-character SHA')
    try:
        resolved=subprocess.run(['git','rev-parse','--verify',commit+'^{commit}'],
            cwd=REPO,check=True,capture_output=True,text=True).stdout.strip()
    except subprocess.CalledProcessError as exc:
        raise ValidationError('parent commit is unavailable') from exc
    if resolved!=commit:
        raise ValidationError('parent commit does not resolve to the exact frozen SHA')
    manifest=read_json(parent/'manifest.json'); digest=manifest.pop('manifest_hash')
    if canonical_json_hash(manifest)!=digest:
        raise ValidationError('parent manifest changed')
    if (read_json(parent/'inputs.json')!=inputs or read_json(parent/'contract.json')!=contract
        or read_json(parent/'expectations.json')!=expected or read_json(parent/'preflight.json')!=preflight
        or canonical_json_hash(contract)!=manifest['contract_hash']):
        raise ValidationError('continuation must retain exact parent inputs/oracle/limits/contract')
    failure=read_json(parent/'failure.json')
    if failure!={'error_type':'AttributeError','error':"'SignalBatchResult' object has no attribute 'to_dict'"}:
        raise ValidationError('continuation is restricted to the recorded observation failure')
    allowed={Path(__file__).resolve(),(REPO/'spec/scripts/run_reviewed_fast_prefix.md').resolve()}
    for row in manifest['code_files']:
        path=Path(row['path']).resolve()
        try:
            relative=path.relative_to(REPO)
            original=subprocess.run(['git','show',f'{commit}:{relative}'],cwd=REPO,check=True,capture_output=True).stdout
        except (ValueError,subprocess.CalledProcessError) as exc:
            raise ValidationError('cannot verify parent source from immutable Git commit') from exc
        if hashlib.sha256(original).hexdigest()!=row['sha256']:
            raise ValidationError('parent commit does not reproduce frozen source')
        if path not in allowed:
            binding(path,row['sha256'])
    for row in manifest['originals']+manifest['registry_files']:
        binding(Path(row['path']),row['sha256'])
    exchange=LocalRoleExchange(parent/'exchange',max_calls=contract['max_local_calls'])
    from stock_opportunity_agent.research.evolution_transport import _parse_json_object_envelope
    answered,undispatched_rows=_request_inventory(parent)
    hashes=[]; undispatched=[row['request_hash'] for row in undispatched_rows]
    for record in answered:
        request=record['request']; request_hash=record['request_hash']
        reservation=len(json.dumps(request['messages'],ensure_ascii=False,sort_keys=True,
            separators=(',',':')).encode('utf-8'))+request['max_output_tokens']
        raw,usage=exchange.receive(request,accounting_tokens=reservation,allow_dispatch=False)
        parsed,normalization=_parse_json_object_envelope(raw)
        cached={'request_hash':request_hash,'response_id':'local-'+request_hash,'model':'independent-subagent',
            'json_output':parsed,'usage':usage,'raw_output':raw,'decision_token_scores':None}
        if normalization is not None:
            cached['structured_output_normalization']=normalization
        if canonical_json_hash(read_json(parent/'cache/responses'/f'{request_hash}.json'))!=canonical_json_hash(cached):
            raise ValidationError('parent cache differs from verified original response')
        hashes.append(request_hash)
    order=[]
    for path in sorted((parent/'observations').glob('*.json')):
        for digest_row in read_json(path)['request_hashes']:
            if digest_row not in order: order.append(digest_row)
    if set(order)!=set(hashes) or len(order)!=len(hashes):
        raise ValidationError('parent accepted observations do not bind the exact reused request prefix')
    parent_files=_immutable_artifacts(parent)
    copied=[{**row,'relative_path':str(Path(row['path']).relative_to(parent))} for row in parent_files
            if Path(row['path']).relative_to(parent).parts[0] in {'requests','cache','exchange','observations'}]
    return {'parent_root':str(parent),'parent_commit':commit,'parent_manifest_hash':digest,
        'parent_failure':binding(parent/'failure.json'),'parent_files':parent_files,
        'copied_files':copied,'inherited_request_hashes':order,'inherited_receipts':len(hashes),
        'undispatched_request_hashes':undispatched,
        'total_request_ceiling':contract['max_local_calls'],
        'maximum_new_requests':contract['max_local_calls']-len(hashes),
        'historical_exact_reuse_not_fresh_model_behavior':True}


def _observe(instance, method, name, root, client):
    original=getattr(instance,method); counter=0
    def call(*args,**kwargs):
        nonlocal counter
        position=counter; counter+=1; start=len(client.request_hash_trace)
        result=original(*args,**kwargs)
        record=_observation_record(result)
        record['request_hashes']=client.request_hash_trace[start:]
        _save_exact(root/'observations'/f'{name}_{position:02}.json',record)
        return result
    setattr(instance,method,call)


def _request_inventory(root):
    """Classify journals separately from complete or forbidden partial dispatches."""
    answered=[]; undispatched=[]
    for path in sorted((root/'requests').glob('*.json')):
        record=read_json(path)
        request=record.get('request'); digest=record.get('request_hash')
        if not isinstance(request,dict) or canonical_json_hash(request)!=digest or path.stem!=digest:
            raise ValidationError('request journal hash changed')
        present=[(root/directory/(digest+suffix)).is_file() for directory,suffix in (
            ('exchange/inbox','.json'),('exchange/outbox','.txt'),
            ('exchange/receipts','.json'),('cache/responses','.json'))]
        if any(present) and not all(present):
            raise ValidationError('request has partial or orphan response artifacts')
        (answered if all(present) else undispatched).append(record)
    expected={record['request_hash'] for record in answered}
    for directory,suffix in (('exchange/inbox','json'),('exchange/outbox','txt'),
                             ('exchange/receipts','json'),('cache/responses','json')):
        if {path.stem for path in (root/directory).glob('*.'+suffix)}!=expected:
            raise ValidationError('request/response inventory contains orphan artifacts')
    return answered,undispatched


def _completed_restore(root,manifest_hash,contract):
    completion=read_json(root/'completion.json'); digest=completion.pop('completion_hash')
    if (canonical_json_hash(completion)!=digest or completion['manifest_hash']!=manifest_hash
        or completion['immutable_artifacts']!=_immutable_artifacts(root)):
        raise ValidationError('completed blind-prefix artifacts changed or missing')
    exchange=LocalRoleExchange(root/'exchange',max_calls=contract['max_local_calls'])
    answered,_undispatched=_request_inventory(root)
    for record in answered:
        exchange.receive(record['request'],accounting_tokens=0,allow_dispatch=False)
    return {**completion['result'],'restored_without_execution':True,'immutable_artifacts_unchanged':True}


def _execute(root,manifest_hash,inputs,contract,store,registry):
    if (root/'completion.json').exists(): return _completed_restore(root,manifest_hash,contract)
    sample=inputs['sample']; expected_preflight=read_json(root/'preflight.json')
    if _bootstrap(store,sample)!=expected_preflight: raise ValidationError('native bootstrap changed')
    lineage=read_json(root/'manifest.json').get('continuation',{})
    exchange=_ContinuationExchange(root/'exchange',max_calls=contract['max_local_calls'],
        inherited=lineage.get('inherited_request_hashes',()))
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
    result={'historical_reused_role_responses':len(lineage.get('inherited_request_hashes',())),
        'fixed_denominator':1,'sample_id':'s01','pending':[], 'external_llm_calls':0,
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
        result['new_role_receipts']=result['independent_receipts']-result['historical_reused_role_responses']
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
    result['new_role_receipts']=result['independent_receipts']-result['historical_reused_role_responses']
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
    parser.add_argument('--parent-root',type=Path); parser.add_argument('--parent-commit')
    modes=parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--prepare',action='store_true'); modes.add_argument('--resume',action='store_true')
    modes.add_argument('--submit',action='store_true'); args=parser.parse_args(); root=args.root.resolve()
    def forbidden(*_args,**_kwargs): raise AssertionError('network forbidden in reviewed blind prefix')
    socket.socket=forbidden
    if args.prepare:
        if args.expectations is None: parser.error('--prepare requires --expectations')
        value=prepare(root,args.expectations.resolve(),parent_root=args.parent_root,parent_commit=args.parent_commit)
    elif args.submit:
        if not args.request_hash or not args.agent_id: parser.error('--submit requires request hash and actual agent id')
        _digest,_inputs,contract,_store,_registry=_verify(root)
        value=LocalRoleExchange(root/'exchange',max_calls=contract['max_local_calls']).submit(args.request_hash,agent_id=args.agent_id)
    else: value=resume(root)
    print(json.dumps(value,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
