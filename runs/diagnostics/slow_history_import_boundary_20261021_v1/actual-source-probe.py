"""One real-source history preflight; all source/global writes forbidden.

Only pointer-bound round1 retrospective records and native Registry/knowledge
reads are authorized. Freeze success immediately stops before history export.
"""
import builtins
from contextlib import ExitStack
from functools import wraps
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import monotonic
from unittest.mock import patch

from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent import artifacts, signal_library as lib
from stock_opportunity_agent.cases.label_store import LabelStore
from stock_opportunity_agent.data.raw_info import RawInfoStore
from stock_opportunity_agent.memory import knowledge
from stock_opportunity_agent.research import evolution_control as control
from stock_opportunity_agent.research.evolution_transport import StructuredRoleClient
import run_minimal_rounds

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[2]
SOURCE=REPO/'runs/cold_start/minimal_rounds_v182_integrated'
GLOBAL=REPO/'runs/cold_start/data'
real_open=builtins.open


def digest(path):
    with real_open(path,'rb')as handle:return hashlib.sha256(handle.read()).hexdigest()

def write(path,value):
    with real_open(path,'x')as handle:
        json.dump(value,handle,sort_keys=True,indent=2);handle.write('\n');handle.flush();os.fsync(handle.fileno())

class BoundaryStop(BaseException):pass


def main():
    output=ROOT/'actual-source-preflight.json'
    if output.exists():raise RuntimeError('one-shot real-source preflight already terminal')
    started=monotonic();reads={};write_attempts=[];denied_reads=[];existing_mkdir=[]
    counts={'freeze':0,'auditor':0,'fixture_internal_batches':0,'native_functions':0,'forbidden_operations':0}
    audit_rows=[];batch_rows=[];function_counts={};depth=0
    # Metadata whitelist authority; no case/outcome values are emitted.
    contract_path=SOURCE/'run_contract.json'
    with real_open(contract_path)as handle:envelope=json.load(handle)
    contract=envelope['contract']
    allowed={SOURCE/name for name in ('run_contract.json','state.json','cycle_state.json')}
    checkpoint=SOURCE/'experiments/round-0001/checkpoint.json'
    allowed.add(checkpoint)
    with real_open(checkpoint)as handle:cp=json.load(handle)
    if cp['round_id']!=1:raise RuntimeError('source committed round differs')
    for plan_id in cp['plan_ids']:
        path=SOURCE/'plans'/plan_id/'record.json';allowed.add(path)
        with real_open(path)as handle:record=json.load(handle)
        if record.get('round_id')!=1 or record.get('plan_id')!=plan_id:raise RuntimeError('record is outside committed round1')
        allowed.add(SOURCE/'knowledge/observations'/(canonical_json_hash(record)+'.json'))
    for kind in ('slow_history','slow_bootstrap'):
        if contract.get(kind+'_manifest_hash'):allowed.add(SOURCE/kind/'manifest.json')
    for path in allowed:
        if path.is_file():reads[str(path.resolve())]={'sha256_before':digest(path),'open_count':0,'scope':'pointer_bound_metadata_or_knowledge'}
    codepaths=[Path(__file__),REPO/'src/stock_opportunity_agent/research/evolution_control.py',
        REPO/'src/stock_opportunity_agent/signal_library.py',REPO/'src/stock_opportunity_agent/memory/knowledge.py']
    code_before={str(p):digest(p)for p in codepaths}
    write(ROOT/'actual-source-command.json',{'python':sys.executable,'argv':sys.argv,'pid':os.getpid(),
        'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
        'scope':'One actual source builder/freeze; S1 committed retrospective outcomes authorized, no blind role input.'})
    def forbidden(*args,**kwargs):counts['forbidden_operations']+=1;raise RuntimeError('forbidden model/network/label/persistent-store/promotion/fullprepare')
    def path_of(value):
        if isinstance(value,int):return None
        return Path(os.fsdecode(value)).resolve()
    def guard_read(value):
        path=path_of(value)
        if path is None:return
        if path.is_relative_to(GLOBAL)or 'locked_test'in path.name.casefold()or 'label-store'in str(path):
            denied_reads.append(str(path));raise BoundaryStop('Forbidden label/global source read')
        if path.is_relative_to(SOURCE):
            registry=path.is_relative_to(SOURCE/'signals')
            if path not in allowed and not registry:
                denied_reads.append(str(path));raise BoundaryStop('Source read outside committed authorized prefix: '+str(path.relative_to(SOURCE)))
            row=reads.setdefault(str(path),{'sha256_before':digest(path),'open_count':0,'scope':'native_registry'if registry else'pointer_bound_committed'})
            row['open_count']+=1
    def guard_write(value):
        path=path_of(value)
        if path is None:return
        if not path.is_relative_to(ROOT):
            write_attempts.append(str(path));raise BoundaryStop('Read-only source/global write blocked: '+str(path))
    old_io_open=io.open;old_os_open=os.open;old_mkdir=os.mkdir
    def opened(file,mode='r',*args,**kwargs):
        (guard_write if any(c in mode for c in 'wax+')else guard_read)(file)
        return real_open(file,mode,*args,**kwargs)
    def io_opened(file,mode='r',*args,**kwargs):
        (guard_write if any(c in mode for c in 'wax+')else guard_read)(file)
        return old_io_open(file,mode,*args,**kwargs)
    def os_opened(file,flags,*args,**kwargs):
        (guard_write if flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND)else guard_read)(file)
        return old_os_open(file,flags,*args,**kwargs)
    def mkdir(path,*args,**kwargs):
        resolved=path_of(path)
        if resolved is not None and not resolved.is_relative_to(ROOT)and resolved.is_dir():
            existing_mkdir.append(str(resolved));raise FileExistsError(str(resolved))
        guard_write(path);return old_mkdir(path,*args,**kwargs)
    real_init=RawInfoStore.__init__;real_append=RawInfoStore.append
    real_audit=lib._audit_deterministic_fixture;real_batch=lib.SignalExecutor.execute_batch
    real_functions=lib.default_deterministic_signal_functions;real_freeze=lib.SignalRegistry.freeze
    def memory_init(self,root=None,documents=()):
        if root is not None:forbidden()
        return real_init(self,documents=documents)
    def memory_append(self,doc):
        if self.root is not None:forbidden()
        return real_append(self,doc)
    def audit(spec,fixture,*,index):
        nonlocal depth
        counts['auditor']+=1;row={'signal_ref':spec.ref,'index':index};depth+=1
        try:
            result=real_audit(spec,fixture,index=index);row['status']='passed';return result
        except Exception as exc:row.update(status='rejected',error_type=type(exc).__name__,error=str(exc));raise
        finally:depth-=1;audit_rows.append(row)
    def batch(self,refs,**kwargs):
        refs=tuple(refs)
        if depth!=1 or len(refs)!=1 or self.raw_info_store.root is not None or self.llm_runner is not None or kwargs.get('company_id')!='capability_fixture':forbidden()
        counts['fixture_internal_batches']+=1;result=real_batch(self,refs,**kwargs)
        batch_rows.append({'signal_ref':refs[0],'results':[r.to_dict()for r in result.results]})
        return result
    def functions():
        result={}
        for name,function in real_functions().items():
            @wraps(function)
            def observed(*args,_name=name,_function=function,**kwargs):
                if depth!=1:forbidden()
                counts['native_functions']+=1;function_counts[_name]=function_counts.get(_name,0)+1
                return _function(*args,**kwargs)
            result[name]=observed
        return result
    freeze_record={}
    def freeze(self,*args,**kwargs):
        counts['freeze']+=1
        if counts['freeze']!=1:raise BoundaryStop('One freeze limit')
        try:result=real_freeze(self,*args,**kwargs)
        except Exception as exc:freeze_record.update(status='rejected',error_type=type(exc).__name__,error=str(exc));raise
        freeze_record.update(status='success_stopped_before_export',version=result.version,registry_hash=result.registry_hash)
        raise BoundaryStop('Freeze succeeded; no history export allowed')
    with TemporaryDirectory(prefix='actual-source-target-',dir=ROOT)as temp,ExitStack()as stack:
        for owner,name in ((builtins,'open'),(io,'open'),(os,'open'),(os,'mkdir')):
            stack.enter_context(patch.object(owner,name,{'open':opened if owner is builtins else io_opened if owner is io else os_opened,'mkdir':mkdir}[name]))
        for name in ('rename','replace','unlink','remove','rmdir'):
            original=getattr(os,name)
            def guarded(*args,_name=name,_original=original,**kwargs):
                for value in args[:2]if _name in ('rename','replace')else args[:1]:guard_write(value)
                return _original(*args,**kwargs)
            stack.enter_context(patch.object(os,name,guarded))
        for owner,name in ((artifacts,'atomic_write_json'),(knowledge,'atomic_write_json'),(lib,'_atomic_write_json')):
            original=getattr(owner,name)
            def atomic(path,*args,_original=original,**kwargs):guard_write(path);return _original(path,*args,**kwargs)
            stack.enter_context(patch.object(owner,name,atomic))
        for owner,name in ((socket,'socket'),(socket,'create_connection'),(LabelStore,'__init__'),(LabelStore,'load'),
                (LabelStore,'record'),(LabelStore,'ground_truth'),(run_minimal_rounds,'prepare'),(lib.SignalRegistry,'promote_validated_batch')):
            stack.enter_context(patch.object(owner,name,forbidden))
        for name in ('complete_json','complete_json_with_token_scores','complete_binary_token_with_scores'):
            stack.enter_context(patch.object(StructuredRoleClient,name,forbidden))
        for owner,name,replacement in ((RawInfoStore,'__init__',memory_init),(RawInfoStore,'append',memory_append),
                (lib,'_audit_deterministic_fixture',audit),(lib.SignalExecutor,'execute_batch',batch),
                (lib,'default_deterministic_signal_functions',functions),(lib.SignalRegistry,'freeze',freeze)):
            stack.enter_context(patch.object(owner,name,replacement))
        try:
            control.build_slow_history_manifest(workspace=Path(temp)/'new-history',source_workspace=SOURCE,
                dataset_manifest_hash=contract['dataset_manifest_hash'])
            entry={'status':'unexpected_return'}
        except BoundaryStop as exc:entry={'status':'boundary_stopped','error_type':type(exc).__name__,'error':str(exc)}
        except Exception as exc:entry={'status':'rejected','error_type':type(exc).__name__,'error':str(exc)}
        manifest_exists=(Path(temp)/'new-history/slow_history/manifest.json').exists()
    for path,row in reads.items():row['sha256_after']=digest(path);row['unchanged']=row['sha256_before']==row['sha256_after']
    result={'entry':entry,'native_freeze':freeze_record,'counts':counts,'native_function_counts':function_counts,
        'audit_rows':audit_rows,'fixture_internal_batch_results':batch_rows,'source_reads':reads,
        'all_actual_source_read_bytes_unchanged':all(r['unchanged']for r in reads.values()),
        'source_write_tripwire':write_attempts,'source_read_scope_denials':denied_reads,'existing_mkdir_no_content_change':existing_mkdir,
        'code_bindings':code_before,'code_unchanged':all(digest(p)==sha for p,sha in code_before.items()),
        'history_manifest_created':manifest_exists,'wall_seconds':monotonic()-started,
        'source_policy':'Read only pointer-bound committed round1 records/knowledge and frozen contract-authorized history manifest. Retrospective outcomes allowed in S1, not blind role input. LockedTest/LabelStore/global source reads forbidden.',
        'scope':'One native builder/freeze attempt only; original fixture auditor/knowledge validator unchanged; no product repair or claim of usable history import.'}
    write(output,result)
    print(json.dumps({k:result[k]for k in ('entry','native_freeze','counts','all_actual_source_read_bytes_unchanged',
        'source_write_tripwire','source_read_scope_denials','code_unchanged','history_manifest_created','wall_seconds')},indent=2))


if __name__=='__main__':main()
