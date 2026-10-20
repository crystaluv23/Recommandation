"""Freeze one historical seed, then run fresh native Reflect and blind Predictor."""
from __future__ import annotations

import argparse
from contextlib import contextmanager, ExitStack
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime
import fcntl
import hashlib
import json
from pathlib import Path
import socket
from unittest.mock import patch

import run_minimal_rounds as minimal
import run_reviewed_fast_prefix as prefix
from run_reviewed_posthoc_stage import _historical_code_check, _parent_snapshot, _verified_responses
from diagnose_executed_answer_scope import StageContract
from stock_opportunity_agent.artifacts import atomic_write_json, canonical_json_hash as digest
from stock_opportunity_agent.cases.label_store import LabelStore
from stock_opportunity_agent.data.raw_info import RawInfoStore
from stock_opportunity_agent.data.reviewed_snapshot import open_raw_info_store
from stock_opportunity_agent.llm import get_model
from stock_opportunity_agent.models import ValidationError
from stock_opportunity_agent.research.evolution_core import (
    InformationPlan, ResearchState, ResearchDecision, RuntimeStopReason, RuntimeBudgetExceeded,
    SignalRound, SignalSelectionDecision, _assemble_final_context, _research_state_delta,
)
from stock_opportunity_agent.research.evolution_plan_roles import LLMResearchController, LLMBlindPredictor
from stock_opportunity_agent.research.evolution_research_validation import _validate_research_state_refs, validate_need_dispositions
from stock_opportunity_agent.research.evolution_transport import StructuredRoleClient, ExternalAttemptLedger
from stock_opportunity_agent.research.local_role_exchange import LocalRoleExchange, LocalRoleRequestPending, LocalRoleBudgetExhausted
from stock_opportunity_agent.signal_library import SignalExecutor

REPO = Path(__file__).resolve().parents[1]
SPEC = REPO/'spec/scripts/run_reviewed_owned_partial_stage.md'
SEED = REPO/'runs/diagnostics/reviewed_fast_prefix_20261020_v1'
VIEW_DOCUMENTS = 1776
CAPTURE_SOURCE_PROFILE = 'gpre_capture_1780'
CAPTURE_SOURCE_COMMIT = '263d16ab18b8712f91a11c121b125f951dbbb05f'
CONTROL_SEED_COMMIT = 'ddeae204566d2d9f9cce29de1ab535902ef46bd5'
CONTROL_PROFILE = 'owned_partial_temporal_controls'
CONTROL_NEEDS = {
    'p01': 'What did annual and subsequent disclosures available by prediction time establish about operating cash flow, capital expenditure, debt balances and maturities, covenants, tax-related cash obligations and prospective equity dilution? Direct annual-report coverage remains unverified.',
    'p02': 'By prediction time, what financial covenant terms and compliance through the six months ended June 30, 2025 and afterwards had been disclosed?',
    'p03': 'By prediction time, what revolving credit availability at June 30, 2025 and covenant compliance during the six months then ended had been disclosed?',
}
LIMITS = {'max_request_tokens':131072,'max_case_tokens':512000,'max_case_llm_calls':6,
    'max_structured_corrections':1,'structured_reasoning_token_reserve':0,'finalization_reserve':64000}
EXCLUDED = {'progress.json','completion.json','.stage.lock','exchange/.dispatch.lock'}


def read(path):
    """Read JSON from a Path or a serialized binding's string path."""
    return prefix.read_json(Path(path))


def binding(path):
    """Stream an exact local binding without decoding unrelated contents."""
    path=Path(path).resolve(); h=hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda:handle.read(1024*1024),b''): h.update(block)
    return {'path':str(path),'sha256':h.hexdigest()}


def _nested(value):
    if isinstance(value,dict):
        if set(value)>={'path','sha256'}: yield {'path':value['path'],'sha256':value['sha256']}
        else:
            for child in value.values(): yield from _nested(child)
    elif isinstance(value,list):
        for child in value: yield from _nested(child)


def _check(rows):
    for row in rows:
        if binding(row['path'])!=row: raise ValidationError('bound stage source/code changed')


def _unique(rows):
    found={}
    for row in rows:
        path=str(Path(row['path']).resolve())
        if path in found and found[path]!=row['sha256']: raise ValidationError('conflicting binding')
        found[path]=row['sha256']
    return [{'path':p,'sha256':s} for p,s in sorted(found.items())]


def _files(root):
    return [binding(p) for p in sorted(root.rglob('*')) if p.is_file() and p.relative_to(root).as_posix() not in EXCLUDED]


@contextmanager
def _guard():
    def forbidden(*args,**kwargs): raise ValidationError('network/label/source-write/Signal/fullprepare forbidden')
    with ExitStack() as stack:
        for target,name in ((socket,'socket'),(socket,'create_connection'),(LabelStore,'load'),
            (LabelStore,'ground_truth'),(LabelStore,'record'),(RawInfoStore,'append'),(SignalExecutor,'execute_batch'),(minimal,'prepare')):
            stack.enter_context(patch.object(target,name,forbidden))
        yield


def _seed(commit):
    lineage=_parent_snapshot(SEED,commit)
    old=read(SEED/'inputs.json'); sample=old['sample']
    prior=read(SEED/'observations/initialize_00.json')['value']
    selections=read(SEED/'observations/routing_00.json')['value']
    results={row['signal_id']+':v'+str(row['version']):row
        for name in ('signal_group_00.json','signal_group_01.json')
        for row in read(SEED/'observations'/name)['results']}
    # This envelope is a source-owner read. Its old prediction is never exported.
    metrics=read(SEED/'prediction.json')['final_context']['computed_metrics']
    bootstrap=read(SEED/'preflight.json')['model_context']
    wire=read(SEED/'requests'/ (read(SEED/'observations/reflect_00.json')['request_hashes'][0]+'.json'))['request']
    payload=json.loads(wire['messages'][1]['content'])
    if (len(prior['next_information_needs'])!=5 or [s['signal_ref'] for s in selections]!=
            ['financing_listing_action:v5','operating_cash_flow_margin:v2']):
        raise ValidationError('fixed historical seed portfolio/prior differs')
    exported={k:sample[k] for k in ('company_id','identity','prediction_time','plan')}
    exported.update(sample_id='p01',prior_state=prior,selections=selections,results=[results[s['signal_ref']] for s in selections],
        basic_info=bootstrap,prediction_baseline=payload['evaluation_anchor'],
        computed_metrics=metrics,evaluation_anchor=payload['evaluation_anchor'],
        signal_research_status=payload['signal_research_status'])
    return exported,_unique([*lineage['files'],*lineage['external_files'],*_nested(old.get('accepted_plan_source',{}))])


def _source(path):
    result=read(path); parent=path.parent; inputs=read(parent/'input_manifest.json')
    plan=read(inputs['plan']['path']); view=result['reviewed_source_snapshot']
    if (result['status']!='completed' or result['fixed_cases']!=40 or result['per_group_inputs']!=720
            or result['labels'] is not False or result['models']!=0 or result['GETs']!=0
            or result['plan_hash']!=plan['plan_hash'] or view!=inputs['reviewed_source_snapshot']):
        raise ValidationError('completed fixed40 source view differs')
    review=read(result['source_review']['path'])
    rows=[binding(path),binding(parent/'input_manifest.json'),*_nested(inputs),*_nested(review),
        *plan['source_bindings'],*plan['code_bindings'],
        *[binding(p) for p in sorted(Path(view['root']).rglob('*')) if p.is_file()]]
    return view,_unique(rows)


def _capture_source(path,commit):
    """Bind completed capture data and its exact historical execution code separately."""
    if commit!=CAPTURE_SOURCE_COMMIT:
        raise ValidationError('capture source requires its exact execution commit')
    result=read(path);parent=path.parent;inputs=read(parent/'input_manifest.json')
    _check([inputs['plan'],result['source_review']])
    plan=read(inputs['plan']['path']);view=result['reviewed_source_snapshot']
    if (result.get('status')!='completed' or result.get('products')!=57
            or result.get('new_capture_versions')!=4 or result.get('retained_legacy_products')!=53
            or any(result.get(key) is not False for key in ('labels','Signal_apply','fullprepare'))
            or any(type(result.get(key)) is not int or result[key]!=0 for key in ('models','GETs'))
            or result.get('old_global_bytes_preserved') is not True
            or result.get('old_review_rows_preserved') is not True
            or result.get('snapshot_reopen_canonical_equal') is not True
            or result['plan_hash']!=plan['plan_hash']
            or digest({k:v for k,v in plan.items() if k!='plan_hash'})!=plan['plan_hash']
            or plan.get('schema_version')!='gpre-capture-source-plan-v1'
            or view!=inputs['reviewed_source_snapshot'] or result['source_review']!=inputs['source_review']):
        raise ValidationError('completed capture source scope/plan differs')
    _historical_code_check([inputs['plan'],*plan['code_bindings']],commit)
    review=read(result['source_review']['path'])
    if (len(review['records'])!=1785
            or sum(row['verdict']=='admitted' for row in review['records'])!=1780):
        raise ValidationError('completed capture source membership differs')
    rows=[binding(path),binding(parent/'input_manifest.json'),*_nested(inputs),*_nested(review),
        *plan['source_bindings'],*[binding(p) for p in sorted(Path(view['root']).rglob('*')) if p.is_file()]]
    return view,_unique(rows),{'commit':commit,'plan':inputs['plan'],'code_files':plan['code_bindings']}


def _control_set(expected,root,sample_id,source_profile,source_commit):
    """Freeze three distinct destinations with non-transferable native case ceilings."""
    roots=expected.get('stage_roots',{})
    total={'max_local_calls':18,'max_case_tokens':1536000}
    if (expected.get('profile')!=CONTROL_PROFILE or type(expected.get('fixed_denominator')) is not int
            or expected['fixed_denominator']!=3 or expected.get('sample_ids')!=list(CONTROL_NEEDS)
            or expected.get('questions')!=CONTROL_NEEDS or set(roots)!=set(CONTROL_NEEDS)
            or source_profile!=CAPTURE_SOURCE_PROFILE or expected.get('source_profile')!=source_profile
            or source_commit!=CAPTURE_SOURCE_COMMIT or expected.get('source_commit')!=source_commit
            or digest(expected.get('limits'))!=digest({'max_local_calls':6,**LIMITS})
            or digest(expected.get('total_limits'))!=digest(total)
            or sample_id not in CONTROL_NEEDS):
        raise ValidationError('temporal control oracle scope/limits differ')
    paths=[]
    for name in CONTROL_NEEDS:
        value=roots[name]
        if not isinstance(value,str) or str(Path(value).resolve())!=value:
            raise ValidationError('temporal control roots must be exact absolute paths')
        paths.append(Path(value))
    if (len(set(paths))!=3 or str(root)!=roots[sample_id]
            or any(a.is_relative_to(b) or b.is_relative_to(a)
                   for i,a in enumerate(paths) for b in paths[i+1:])):
        raise ValidationError('temporal control destination differs or overlaps')
    return {'sample_ids':list(CONTROL_NEEDS),'stage_roots':roots,
            'per_case_limits':{'max_local_calls':6,**LIMITS},'total_limits':total}


def _preflight(sample,view,*,expected_documents=VIEW_DOCUMENTS):
    store=open_raw_info_store(view['root'],reviewed_snapshot=view)
    if len(store.documents)!=expected_documents: raise ValidationError('completed source membership differs')
    prior=ResearchState.from_dict(sample['prior_state']); plan=InformationPlan.from_dict(sample['plan'])
    round_row=SignalRound.from_dict({'information_needs':list(prior.next_information_needs),
        'selections':sample['selections'],'batch':{'results':sample['results'],'signal_calls':2}})
    controller=LLMResearchController(None);controller.set_evaluation_context(datetime.fromisoformat(sample['prediction_time']))
    _validate_research_state_refs(prior,phase='reflect',previous_state=prior,basic_info=sample['basic_info'],
        need_dispositions=[],evaluation_context=controller.evaluation_context)
    for result in round_row.batch.results:
        for evidence in (*result.supporting_evidence,*result.counter_evidence):
            document=store.load(evidence.document_id,as_of=datetime.fromisoformat(sample['prediction_time']))
            if evidence.exact_span not in document.content: raise ValidationError('historical seed quote not in admitted original')
    return {'historical_seed_not_new_F6':True,'source_documents':len(store.documents),'prior_hash':digest(prior.to_dict()),
        'plan_hash':digest(plan.to_dict()),'source_batch_hash':digest(sample['results'])}


def prepare(root,expectations,source_result,seed_commit,*,sample_id='p01',source_profile=None,source_commit=None):
    """Freeze one seed and current completed source view without model dispatch."""
    root=Path(root).resolve()
    with _guard():
        if root.exists(): raise ValidationError('owned partial destination must be new')
        expected=read(expectations)
        controls=None;history=None
        if expected.get('profile')==CONTROL_PROFILE:
            controls=_control_set(expected,root,sample_id,source_profile,source_commit)
            if seed_commit!=CONTROL_SEED_COMMIT:
                raise ValidationError('temporal controls require the exact historical seed commit')
        elif (sample_id!='p01' or source_profile is not None or source_commit is not None
                or expected.get('profile')!='owned_partial_historical_seed' or expected.get('fixed_denominator')!=1
                or expected.get('sample_id')!='p01' or expected.get('limits')!={'max_local_calls':6,**LIMITS}):
            raise ValidationError('independent oracle scope/limits differ')
        oracle_bindings=list(_nested(expected['bindings']));_check(oracle_bindings)
        authorities={'completed_source_result':binding(source_result),'historical_prefix_inputs':binding(SEED/'inputs.json'),
            'historical_prefix_completion':binding(SEED/'completion.json')}
        if any(expected['bindings'].get(key)!=value for key,value in authorities.items()):
            raise ValidationError('independent oracle source/seed authority differs')
        sample,old_files=_seed(seed_commit)
        if controls is None:
            view,source_files=_source(Path(source_result).resolve())
        else:
            view,source_files,history=_capture_source(Path(source_result).resolve(),source_commit)
            if sample['prior_state']['next_information_needs'][4]!=CONTROL_NEEDS['p01']:
                raise ValidationError('historical original need differs')
            sample=deepcopy(sample);sample['sample_id']=sample_id
            sample['prior_state']['next_information_needs'][4]=CONTROL_NEEDS[sample_id]
        for key in ('source_review','actual_cited_body'):
            if key in expected['bindings'] and expected['bindings'][key] not in source_files:
                raise ValidationError('independent oracle body/review not in completed source inventory')
        protected=[SEED,Path(source_result).resolve().parent,Path(view['root']),
            *[Path(b['path']).parent for b in source_files if Path(b['path']).name=='oracle.json']]
        destinations=[root] if controls is None else [Path(p) for p in controls['stage_roots'].values()]
        if any(d.is_relative_to(p) or p.is_relative_to(d) for p in protected for d in destinations):
            raise ValidationError('new stage overlaps historical/source oracle or view')
        preflight=(_preflight(sample,view) if controls is None
                   else _preflight(sample,view,expected_documents=1780))
        inputs={'sample':sample,'reviewed_source_snapshot':view,'historical_seed_not_new_F6':True}
        contract={'schema_version':'reviewed-owned-partial-stage-v1','backend':'independent-subagent','actual_model_version':None,
            'fixed_denominator':1,'max_local_calls':6,'max_external_api_calls':0,'limits':LIMITS,
            'input_hash':digest(inputs),'expectations_hash':digest(expected),'preflight_hash':digest(preflight)}
        if controls is not None:
            contract.update(fixed_denominator=3,control_set=controls,source_profile=source_profile)
        code=_unique([*prefix._code_bindings(),binding(__file__),binding(SPEC),
            binding(REPO/'scripts/run_reviewed_posthoc_stage.py'),binding(REPO/'spec/scripts/run_reviewed_posthoc_stage.md')])
        originals=_unique([binding(expectations),*oracle_bindings,*old_files,*source_files]);_check(code+originals)
        manifest={'root':str(root),'contract_hash':digest(contract),'code_files':code,'originals':originals,'seed_commit':seed_commit}
        if history is not None:manifest['historical_source_code']=history
        manifest['manifest_hash']=digest(manifest)
        for name,value in (('inputs',inputs),('expectations',expected),('contract',contract),('preflight',preflight),('manifest',manifest)):
            atomic_write_json(root/(name+'.json'),value)
        return {'manifest_hash':manifest['manifest_hash'],'fixed_denominator':contract['fixed_denominator'],'role_dispatches':0}


def _verify(root):
    manifest=read(root/'manifest.json'); h=manifest.pop('manifest_hash');inputs=read(root/'inputs.json');contract=read(root/'contract.json')
    if (manifest['root']!=str(root) or digest(manifest)!=h or digest(contract)!=manifest['contract_hash'] or digest(inputs)!=contract['input_hash']
            or digest(read(root/'expectations.json'))!=contract['expectations_hash'] or digest(read(root/'preflight.json'))!=contract['preflight_hash']):
        raise ValidationError('owned partial frozen inputs changed')
    _check(manifest['code_files']+manifest['originals'])
    if 'historical_source_code' in manifest:
        history=manifest['historical_source_code']
        controls=_control_set(read(root/'expectations.json'),root,inputs['sample']['sample_id'],
            contract.get('source_profile'),history['commit'])
        if controls!=contract.get('control_set') or contract.get('fixed_denominator')!=3:
            raise ValidationError('frozen temporal control set differs')
        if manifest['seed_commit']!=CONTROL_SEED_COMMIT:
            raise ValidationError('temporal control seed lineage changed')
        _historical_code_check([history['plan'],*history['code_files']],CAPTURE_SOURCE_COMMIT)
    elif 'control_set' in contract:
        raise ValidationError('temporal control source lineage missing')
    return h,inputs,contract


def _save(path,value):
    if path.exists():
        if digest(read(path))!=digest(value): raise ValidationError('accepted stage artifact changed on reentry')
    else: atomic_write_json(path,value)


class _Budget:
    def __init__(self,contract): self.limits=contract['limits'];self.calls=0;self.tokens=0
    def __call__(self,event):
        if event.get('event_type')!='request_ready': return
        request=read(Path(event['request_path']))['request'];stage=request['stage']
        if stage not in {'research_controller_reflect','research_controller_reflect_correction','research_controller_reflect_patch_mechanics_correction',
                'blind_predictor_predict','blind_predictor_predict_correction','blind_predictor_predict_patch_mechanics_correction'}:
            raise ValidationError('role outside owned partial stage')
        size=len(json.dumps(request['messages'],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode())+request['max_output_tokens']
        ceiling=self.limits['max_case_tokens']-(self.limits['finalization_reserve'] if stage.startswith('research_controller') else 0)
        if size>self.limits['max_request_tokens'] or self.tokens+size>ceiling or self.calls+1>6:
            raise RuntimeBudgetExceeded('owned partial frozen request/case ceiling')
        self.calls+=1;self.tokens+=size


def _reflect(client,sample,prior,batch,closure,budget):
    controller=LLMResearchController(client);controller.set_evaluation_context(datetime.fromisoformat(sample['prediction_time']))
    controller.set_evaluation_anchor(sample['evaluation_anchor']);controller.set_computed_metrics(sample['computed_metrics'])
    controller.set_signal_research_status(sample['signal_research_status'])
    selections=tuple(SignalSelectionDecision.from_dict(row) for row in sample['selections'])
    controller.set_reflection_runtime_context(selections=() if closure else selections,must_finalize=closure,
        termination_trigger=RuntimeStopReason.MAX_SIGNAL_ROUNDS if closure else None)
    controller.set_request_token_budget(512000-budget.tokens-64000)
    step=controller.reflect(InformationPlan.from_dict(sample['plan']),prior,batch)
    return step,controller


def _run(root,h,inputs,contract):
    if (root/'completion.json').exists():
        completed=read(root/'completion.json'); seal=completed.pop('completion_hash')
        if digest(completed)!=seal or completed['manifest_hash']!=h or completed['immutable_artifacts']!=_files(root):
            raise ValidationError('completed owned partial artifacts changed')
        _verified_responses(root,6)
        return {**completed['result'],'restored_without_execution':True}
    if (root/'failure.json').exists(): raise ValidationError('terminal owned partial failure cannot resume')
    exchange=LocalRoleExchange(root/'exchange',max_calls=6);budget=_Budget(contract)
    client=StructuredRoleClient(registration=get_model('independent-subagent'),contract=StageContract(contract),workspace=root,
        local_role_exchange=exchange,ledger=ExternalAttemptLedger(root/'unused_external_attempts.json',max_attempts=1,max_total_cost=.01),
        allow_external=False,environ={},on_progress=budget)
    sample=inputs['sample'];prior=ResearchState.from_dict(sample['prior_state']);plan=InformationPlan.from_dict(sample['plan'])
    round_row=SignalRound.from_dict({'information_needs':list(prior.next_information_needs),'selections':sample['selections'],
        'batch':{'results':sample['results'],'signal_calls':2}});batch=round_row.batch
    result={'fixed_denominator':contract['fixed_denominator'],'sample_id':sample['sample_id'],'external_api_calls':0,'labels_read':0,'new_Signal_apply':0,
        'historical_seed_not_new_F6':True,'actual_host_tokens':None,'actual_host_cost':None,'engineering_mvp_closed':False}
    try:
        with client.anonymous_case(aliases=tuple(sample['identity']['identity_aliases']),company_id=sample['company_id'],ticker=sample['identity']['ticker']):
            state=prior;deltas=[]
            for closure in (False,True):
                if closure and state.decision is ResearchDecision.FINALIZE: break
                before=state;start=len(client.request_hash_trace)
                step,controller=_reflect(client,sample,before,batch,closure,budget)
                name='closure' if closure else 'reflect'
                saved={'state':step.value.to_dict(),'metadata':dict(step.metadata),'request_hashes':client.request_hash_trace[start:]}
                _save(root/(name+'.json'),saved)
                if not (root/(name+'-usage.json')).exists():atomic_write_json(root/(name+'-usage.json'),asdict(step.usage))
                saved=read(root/(name+'.json'));state=ResearchState.from_dict(saved['state']);meta=saved['metadata']['need_dispositions']
                if meta['prior_state_hash']!=digest(before.to_dict()): raise ValidationError('saved disposition prior hash differs')
                rows=[{k:v for k,v in row.items() if k!='prior_need'} for row in meta['items']]
                _validate_research_state_refs(state,phase='reflect',previous_state=before,selections=() if closure else round_row.selections,
                    batch=batch,need_dispositions=rows,must_finalize=closure,evaluation_context=controller.evaluation_context)
                validate_need_dispositions(rows,previous_state=before,state=state,selections=() if closure else round_row.selections,batch=batch,
                    evaluation_context=controller.evaluation_context)
                deltas.append({'round':1,'delta':_research_state_delta(before,state),'need_dispositions':meta})
            context=_assemble_final_context(plan=plan,company_id=sample['company_id'],additional_identity_aliases=tuple(sample['identity']['identity_aliases']),
                basic_info=sample['basic_info'],state=state,rounds=(round_row,),prediction_time=datetime.fromisoformat(sample['prediction_time']),
                prediction_baseline=sample['prediction_baseline'],computed_metrics=sample['computed_metrics'],state_deltas=tuple(deltas),
                signal_research_status=sample['signal_research_status'],runtime_termination={'phase':'prediction_ready','stop_reason':'finalized',
                    'termination_trigger':'max_signal_rounds' if len(deltas)>1 else None})
            _save(root/'final-context.json',context);context=read(root/'final-context.json')
            predictor=LLMBlindPredictor(client);predictor.set_request_token_budget(512000-budget.tokens)
            step=predictor.predict(context)
            record={'company_id':sample['company_id'],'prediction_time':sample['prediction_time'],'final_context':context,'prediction':step.value.to_dict()}
            _save(root/'prediction.json',record)
            if digest(read(root/'prediction.json'))!=digest(record):raise ValidationError('prediction sink readback differs')
        answered,_=_verified_responses(root,6)
        mirror=False
        for row in answered:
            payload=json.loads(row['request']['messages'][1]['content'])
            obligations=(payload.get('validation_feedback') or {}).get('obligations',[])
            if any('residual_mirror_path' in item for item in obligations): mirror=True
        result.update(status='prediction_persisted_requires_independent_review',independent_receipts=len(answered),
            mirror_correction_branch='exercised_requires_independent_review' if mirror else 'not_exercised',
            prediction_ref=binding(root/'prediction.json'),logical_reservation=budget.tokens)
        _verify(root)
        completed={'manifest_hash':h,'result':result,'immutable_artifacts':_files(root)};completed['completion_hash']=digest(completed)
        atomic_write_json(root/'completion.json',completed)
    except LocalRoleRequestPending as error:result.update(status='pending_independent_role',pending=error.pending)
    except (RuntimeBudgetExceeded,LocalRoleBudgetExhausted) as error:
        result.update(status='control_budget_stopped',error_type=type(error).__name__)
        _save(root/'failure.json',result)
    except Exception as error:
        result.update(status='terminal_failed',error_type=type(error).__name__)
        _save(root/'failure.json',result)
    atomic_write_json(root/'progress.json',result)
    return result


def resume(root):
    """Reenter native cached calls serially, or verify a completed immutable stage."""
    root=Path(root).resolve()
    with _guard(),(root/'.stage.lock').open('a+') as lock:
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX)
        return _run(root,*_verify(root))


def main():
    """Prepare, serially resume or bind one exact independently authored answer."""
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,required=True)
    modes=parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--prepare',action='store_true');modes.add_argument('--resume',action='store_true');modes.add_argument('--submit',action='store_true')
    parser.add_argument('--expectations',type=Path);parser.add_argument('--source-result',type=Path);parser.add_argument('--seed-commit')
    parser.add_argument('--sample-id',default='p01');parser.add_argument('--source-profile');parser.add_argument('--source-commit')
    parser.add_argument('--request-hash');parser.add_argument('--agent-id');args=parser.parse_args()
    if args.prepare:
        if not all((args.expectations,args.source_result,args.seed_commit)):parser.error('prepare needs expectations/source-result/seed-commit')
        value=prepare(args.root,args.expectations,args.source_result,args.seed_commit,
            sample_id=args.sample_id,source_profile=args.source_profile,source_commit=args.source_commit)
    elif args.submit:
        with _guard():
            _h,_inputs,contract=_verify(args.root.resolve())
            if (args.root/'completion.json').exists() or (args.root/'failure.json').exists(): raise ValidationError('terminal stage cannot submit')
            value=LocalRoleExchange(args.root/'exchange',max_calls=6).submit(args.request_hash,agent_id=args.agent_id)
    else:value=resume(args.root)
    print(json.dumps(value,indent=2,ensure_ascii=False))


if __name__=='__main__': main()
