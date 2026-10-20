"""One temporary native history-import/auditor boundary probe, no real source runs.

The sole allowed Signal batches are native synthetic-fixture auditor internals:
empty/pure-memory store, one ref, capability_fixture issuer, no LLM runner.
Successful freeze raises BoundaryStop immediately, before history extraction.
"""
from contextlib import ExitStack
from datetime import datetime, timezone
from functools import wraps
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import monotonic
from unittest.mock import patch

from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.cases.label_store import LabelStore
from stock_opportunity_agent.data.raw_info import RawInfoStore
from stock_opportunity_agent.research import evolution_control as control
from stock_opportunity_agent.research.evolution_transport import StructuredRoleClient
from stock_opportunity_agent import signal_library as library
import run_minimal_rounds

REPO=Path(__file__).resolve().parents[3]
ROOT=Path(__file__).resolve().parent
SOURCE=REPO/'runs/cold_start/minimal_rounds_v182_integrated'
GROUP_PATH=REPO/'runs/diagnostics/current_financial_apply_20261021_v1/oracle/definitions.json'
NAMED={'cash_reserves:v2','revenue_growth_yoy:v3'}


def read(path):return json.loads(Path(path).read_text())

def binding(path):
    path=Path(path).resolve()
    return {'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}


def write(path,value):
    with Path(path).open('x')as handle:
        json.dump(value,handle,sort_keys=True,indent=2);handle.write('\n')
        handle.flush();os.fsync(handle.fileno())


class BoundaryStop(BaseException):pass


def main():
    if (ROOT/'result.json').exists():raise RuntimeError('diagnosis already terminal')
    start=monotonic()
    definitions=[]
    for path in sorted((SOURCE/'signals').rglob('*')):
        if not path.is_file():continue
        rel=path.relative_to(SOURCE/'signals')
        if rel.name in {'events.jsonl','profile.json','stats.json'} or 'learning'in rel.parts or rel.parts[0]=='.transitions':continue
        definitions.append(path)
    originals=[SOURCE/name for name in ('run_contract.json','state.json','cycle_state.json')]+definitions+[GROUP_PATH]
    before=[binding(p)for p in originals]
    code=[binding(REPO/name)for name in (
        'src/stock_opportunity_agent/research/evolution_control.py',
        'src/stock_opportunity_agent/signal_library.py',
        'src/stock_opportunity_agent/data/raw_info.py',
        'src/stock_opportunity_agent/data/sec_company_facts.py')]
    code.append(binding(__file__))
    write(ROOT/'command.json',{'command':sys.argv,'python':sys.executable,'pid':os.getpid(),
        'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
        'started_at':datetime.now(timezone.utc).isoformat(),'guard':'Only native synthetic-fixture internal batch exception; no production batch.'})
    counts={'freeze':0,'fixture_audit':0,'fixture_internal_batches':0,'native_functions':0,'forbidden_calls':0}
    audits=[];batches=[];functions={};freeze_record={};reads=[]
    fixture_depth=0
    original_freeze=library.SignalRegistry.freeze
    original_audit=library._audit_deterministic_fixture
    original_batch=library.SignalExecutor.execute_batch
    original_store_init=RawInfoStore.__init__
    original_append=RawInfoStore.append
    original_functions=library.default_deterministic_signal_functions
    original_control_read=control._read_json

    def forbidden(*args,**kwargs):
        counts['forbidden_calls']+=1
        raise RuntimeError('forbidden network/model/label/persistent-store/promotion/fullprepare')

    def memory_init(self,root=None,documents=()):
        if root is not None:forbidden()
        return original_store_init(self,documents=documents)

    def memory_append(self,document):
        if self.root is not None:forbidden()
        return original_append(self,document)

    def fixture_audit(spec,fixture,*,index):
        nonlocal fixture_depth
        counts['fixture_audit']+=1
        row={'signal_ref':spec.ref,'index':index}
        fixture_depth+=1
        try:
            result=original_audit(spec,fixture,index=index)
            row['status']='passed'
            return result
        except Exception as exc:
            row.update(status='rejected',error_type=type(exc).__name__,error=str(exc))
            raise
        finally:
            fixture_depth-=1;audits.append(row)

    def batch(self,refs,**kwargs):
        refs=tuple(refs)
        if (fixture_depth!=1 or self.raw_info_store.root is not None or len(refs)!=1
                or self.llm_runner is not None or kwargs.get('company_id')!='capability_fixture'):
            forbidden()
        counts['fixture_internal_batches']+=1
        actual=original_batch(self,refs,**kwargs)
        row={'signal_ref':refs[0],'result_count':len(actual.results),
            'execution':[r.execution_status.value for r in actual.results]}
        if refs[0]in NAMED:row['actual_results']=[r.to_dict()for r in actual.results]
        batches.append(row)
        return actual

    def function_map():
        result={}
        for name,function in original_functions().items():
            @wraps(function)
            def observed(*args,_name=name,_function=function,**kwargs):
                if fixture_depth!=1:forbidden()
                counts['native_functions']+=1;functions[_name]=functions.get(_name,0)+1
                return _function(*args,**kwargs)
            result[name]=observed
        return result

    def freeze(self,*args,**kwargs):
        counts['freeze']+=1
        try:actual=original_freeze(self,*args,**kwargs)
        except Exception as exc:
            freeze_record.update(status='rejected',error_type=type(exc).__name__,error=str(exc))
            raise
        freeze_record.update(status='unexpected_success',version=actual.version,registry_hash=actual.registry_hash)
        raise BoundaryStop('Native freeze succeeded; stop before any history extraction')

    with TemporaryDirectory(prefix='temporary-source-',dir=ROOT)as temporary:
        temp=Path(temporary).resolve();source=temp/'source';target=temp/'new-import'
        for original in originals[:-1]:
            destination=source/original.relative_to(SOURCE)
            destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(original,destination)
        copied=[{'source':binding(p),'copy':binding(source/p.relative_to(SOURCE))}for p in originals[:-1]]
        if any(row['source']['sha256']!=row['copy']['sha256']for row in copied):raise RuntimeError('copy differs')
        permitted_control_reads={source/name for name in ('run_contract.json','state.json','cycle_state.json')}
        def bounded_read(path):
            path=Path(path).resolve()
            if path not in permitted_control_reads:raise BoundaryStop('Stop before non-metadata history read: '+str(path))
            reads.append(str(path.relative_to(source)))
            return original_control_read(path)
        with ExitStack()as stack:
            for owner,name in ((socket,'socket'),(socket,'create_connection'),
                    (LabelStore,'__init__'),(LabelStore,'load'),(LabelStore,'record'),(LabelStore,'ground_truth'),
                    (run_minimal_rounds,'prepare'),(library.SignalRegistry,'promote_validated_batch'),
                    (library.SignalRegistry,'register_stable'),(library.SignalRegistry,'install_catalog')):
                stack.enter_context(patch.object(owner,name,forbidden))
            for name in ('complete_json','complete_json_with_token_scores','complete_binary_token_with_scores'):
                stack.enter_context(patch.object(StructuredRoleClient,name,forbidden))
            for owner,name,replacement in ((RawInfoStore,'__init__',memory_init),(RawInfoStore,'append',memory_append),
                    (library.SignalExecutor,'execute_batch',batch),
                    (library,'_audit_deterministic_fixture',fixture_audit),
                    (library,'default_deterministic_signal_functions',function_map),
                    (library.SignalRegistry,'freeze',freeze),(control,'_read_json',bounded_read)):
                stack.enter_context(patch.object(owner,name,replacement))
            contract=control.EvolutionRunContract.load_frozen(source/'run_contract.json')
            try:
                control.build_slow_history_manifest(workspace=target,source_workspace=source,
                    dataset_manifest_hash=contract.dataset_manifest_hash)
                entry={'status':'unexpected_return'}
            except BoundaryStop as exc:entry={'status':'boundary_stopped','error_type':type(exc).__name__,'error':str(exc)}
            except Exception as exc:entry={'status':'rejected','error_type':type(exc).__name__,'error':str(exc)}
            group=read(GROUP_PATH)['group']
            # This pure-definition control deliberately cannot stand in for learned profiles.
            registry=library.SignalRegistry(source/'signals',candidate_root=temp/'pure-candidates')
            prior_counts=dict(counts)
            snapshot=registry.snapshot_from_refs(group['version'],tuple(group['refs']))
            pure={'version':snapshot.version,'registry_hash':snapshot.registry_hash,
                'exact_v12_hash':snapshot.registry_hash==group['registry_hash'],'refs':tuple(s.ref for s in snapshot.specs)==tuple(group['refs']),
                'count':len(snapshot.specs),'no_new_fixture_or_batch_or_function_calls':counts==prior_counts,
                'profile_scope':'Pure definitions/skills only; learned profiles/import cutoffs/committed events not reconstructed. Not a freeze/import replacement.'}
        shapes=[]
        for ref in sorted(NAMED):
            signal_id,version=ref.split(':v')
            path=source/'signals/financial'/signal_id/'versions'/('v'+version)/'tests.json'
            for fixture in read(path)['tests']:
                docs=[]
                for doc in fixture['documents']:
                    try:body=json.loads(doc['content'])
                    except Exception:body={}
                    docs.append({'source_type':doc['source_type'],'metadata_cik':doc.get('metadata',{}).get('cik'),
                        'body_cik':body.get('cik')if isinstance(body,dict)else None,
                        'content_sha256':hashlib.sha256(doc['content'].encode()).hexdigest()})
                shapes.append({'signal_ref':ref,'name':fixture.get('name'),'expected':fixture['expected'],'documents':docs})
        result={'status':'diagnosed','actual_entry':entry,'native_freeze':freeze_record,'counts':counts,
            'native_function_counts':functions,'audit_rows':audits,'fixture_batches':batches,
            'named_fixture_shapes':shapes,'pure_definition_control':pure,'copied_definition_files':len(definitions),
            'copy_sha_equal':all(row['source']['sha256']==row['copy']['sha256']for row in copied),
            'history_manifest_created':(target/'slow_history/manifest.json').exists(),
            'original_contract_pointer_reads':reads,'copy_bindings':copied,
            'original_source_bindings_before':before,'code_bindings_before':code,
            'guard_semantics':'Native auditor and its functions are unchanged; observation wrappers permit only fixture-depth1, memory store, capability_fixture, one ref, no LLM runner. All other batches/real stores/labels/HTTP/promotion forbidden.',
            'LLM':0,'GET':0,'LabelStore_or_LockedTest':0,'real_case_outcome_reads':0,
            'source_stage_or_global_writes':0,'wall_seconds':monotonic()-start}
    after=[binding(p)for p in originals]
    result['original_source_bindings_after']=after
    result['original_source_all_bytes_unchanged']=before==after
    result['code_unchanged']=code==[binding(row['path'])for row in code]
    named=[r for r in batches if r['signal_ref']in NAMED]
    result['conclusion']=('confirmed_history_identity_gate_coupled_to_current_synthetic_fixture_issuer_audit'
        if freeze_record.get('status')=='rejected' and len(named)==2 and all(
            row['actual_results'][0]['execution']['status']=='validation_failed' and
            'issuer' in row['actual_results'][0]['execution'].get('error_message','').lower() for row in named)
        else 'counterevidence_or_unresolved_do_not_repair_from_metadata_inference')
    write(ROOT/'result.json',result)
    print(json.dumps({key:result[key]for key in ('conclusion','counts','pure_definition_control',
        'history_manifest_created','original_source_all_bytes_unchanged','code_unchanged','wall_seconds')},indent=2))


if __name__=='__main__':main()
