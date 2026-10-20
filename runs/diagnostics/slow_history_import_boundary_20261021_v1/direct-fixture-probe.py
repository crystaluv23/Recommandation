"""Native auditor's two exact published synthetic fixtures and identity-only controls.

No history builder, knowledge profile, source Store, promotion or real case reads.
An internal single-ref batch is allowed only during the actual fixture auditor.
"""
from contextlib import ExitStack
from copy import deepcopy
from functools import wraps
import hashlib
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
from time import monotonic
from unittest.mock import patch

from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.cases.label_store import LabelStore
from stock_opportunity_agent.data.raw_info import RawInfoStore
from stock_opportunity_agent.research.evolution_transport import StructuredRoleClient
from stock_opportunity_agent import signal_library as lib
import run_minimal_rounds

REPO=Path(__file__).resolve().parents[3]
ROOT=Path(__file__).resolve().parent
SOURCE=REPO/'runs/cold_start/minimal_rounds_v182_integrated/signals/financial'


def binding(path):return {'path':str(Path(path).resolve()),'sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest()}
def write(path,value):
    with path.open('x')as handle:
        json.dump(value,handle,sort_keys=True,indent=2);handle.write('\n');handle.flush();os.fsync(handle.fileno())


def main():
    result_path=ROOT/'direct-fixture-result.json'
    if result_path.exists():raise RuntimeError('direct fixture slice already terminal')
    start=monotonic()
    sources=[SOURCE/identity/'versions'/('v'+str(version))/name
        for identity,version in (('cash_reserves',2),('revenue_growth_yoy',3))
        for name in ('spec.json','tests.json')]
    before=[binding(p)for p in sources]
    code=[binding(REPO/'src/stock_opportunity_agent/signal_library.py'),
        binding(REPO/'src/stock_opportunity_agent/data/raw_info.py'),
        binding(REPO/'src/stock_opportunity_agent/data/sec_company_facts.py'),binding(__file__)]
    write(ROOT/'direct-fixture-command.json',{'python':sys.executable,'argv':sys.argv,'pid':os.getpid(),
        'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()})
    counts={'audits':0,'fixture_internal_batches':0,'native_functions':0,'forbidden':0}
    depth=0;current=None;rows=[]
    real_audit=lib._audit_deterministic_fixture
    real_batch=lib.SignalExecutor.execute_batch
    real_init=RawInfoStore.__init__;real_append=RawInfoStore.append
    real_map=lib.default_deterministic_signal_functions
    def forbid(*a,**kw):counts['forbidden']+=1;raise RuntimeError('forbidden non-fixture operation')
    def memory_init(self,root=None,documents=()):
        if root is not None:forbid()
        return real_init(self,documents=documents)
    def memory_append(self,doc):
        if self.root is not None:forbid()
        return real_append(self,doc)
    def batch(self,refs,**kwargs):
        refs=tuple(refs)
        if depth!=1 or len(refs)!=1 or self.raw_info_store.root is not None or self.llm_runner is not None or kwargs.get('company_id')!='capability_fixture':forbid()
        counts['fixture_internal_batches']+=1
        actual=real_batch(self,refs,**kwargs)
        current['actual_native_batch']={'signal_calls_result_count':actual.signal_calls,
            'results':[r.to_dict()for r in actual.results],
            'resolutions':[r.to_dict()for r in actual.resolutions],
            'document_fingerprints':dict(actual.document_fingerprints)}
        return actual
    def function_map():
        output={}
        for name,function in real_map().items():
            @wraps(function)
            def observed(*args,_name=name,_function=function,**kwargs):
                if depth!=1:forbid()
                counts['native_functions']+=1
                current.setdefault('function_calls',[]).append(_name)
                return _function(*args,**kwargs)
            output[name]=observed
        return output
    def audit(spec,fixture,label):
        nonlocal depth,current
        current={'signal_ref':spec.ref,'case':label,'fixture_name':fixture.get('name'),
            'expected':fixture['expected'],'fixture_hash':canonical_json_hash(fixture)}
        counts['audits']+=1;depth+=1
        try:
            real_audit(spec,fixture,index=0)
            current['audit_status']='passed'
        except Exception as exc:current.update(audit_status='rejected',error_type=type(exc).__name__,error=str(exc))
        finally:depth-=1;rows.append(current)
        return current
    with ExitStack()as stack:
        for owner,name in ((socket,'socket'),(socket,'create_connection'),(LabelStore,'__init__'),
                (LabelStore,'load'),(LabelStore,'record'),(LabelStore,'ground_truth'),
                (lib.SignalRegistry,'__init__'),(lib.SignalRegistry,'freeze'),
                (lib.SignalRegistry,'promote_validated_batch'),(run_minimal_rounds,'prepare')):
            stack.enter_context(patch.object(owner,name,forbid))
        for name in ('complete_json','complete_json_with_token_scores','complete_binary_token_with_scores'):
            stack.enter_context(patch.object(StructuredRoleClient,name,forbid))
        for owner,name,replacement in ((RawInfoStore,'__init__',memory_init),(RawInfoStore,'append',memory_append),
                (lib.SignalExecutor,'execute_batch',batch),(lib,'default_deterministic_signal_functions',function_map)):
            stack.enter_context(patch.object(owner,name,replacement))
        for identity,version in (('cash_reserves',2),('revenue_growth_yoy',3)):
            directory=SOURCE/identity/'versions'/('v'+str(version))
            spec=lib.SignalSpec.from_dict(json.loads((directory/'spec.json').read_text()))
            original=json.loads((directory/'tests.json').read_text())['tests'][0]
            old=audit(spec,original,'exact_published_positive')
            execution=old.get('actual_native_batch',{}).get('results',[{}])[0].get('execution',{})
            if execution.get('status')!='validation_failed' or not any(word in execution.get('error_message','').casefold()for word in ('issuer','cik')):
                old['stop']='Original did not fail for proven issuer/CIK reason; no counterfactual or further tuning.'
                break
            corrected=deepcopy(original);preservation=[]
            for doc in corrected['documents']:
                content=doc['content'];parsed=json.loads(content)
                if 'cik'in parsed or 'cik'in doc.get('metadata',{}):raise RuntimeError('identity-only control precondition differs')
                position=content.index('{')+1;addition='"cik":"0000000001",'
                doc['content']=content[:position]+addition+content[position:]
                doc['metadata']={**doc.get('metadata',{}),'cik':'0000000001'}
                changed=json.loads(doc['content']);changed.pop('cik')
                preservation.append({'body_without_added_cik_exact_json_equal':canonical_json_hash(changed)==canonical_json_hash(parsed),
                    'original_body_bytes_recovered_by_removing_only_added_cik':doc['content'][:position]+doc['content'][position+len(addition):]==content,
                    'body_original_sha256':hashlib.sha256(content.encode()).hexdigest()})
            new=audit(spec,corrected,'memory_only_consistent_synthetic_CIK')
            new['preservation']=preservation
            without=deepcopy(corrected)
            for doc,orig in zip(without['documents'],original['documents'],strict=True):
                doc['content']=orig['content']
                if 'metadata'in orig:doc['metadata']=deepcopy(orig['metadata'])
                else:doc.pop('metadata',None)
            new['all_non_identity_fixture_fields_preserved']=canonical_json_hash(without)==canonical_json_hash(original)
    after=[binding(p)for p in sources]
    result={'rows':rows,'counts':counts,'source_bindings_before':before,'source_bindings_after':after,
        'original_source_bytes_unchanged':before==after,'code_bindings':code,
        'code_bytes_unchanged':code==[binding(p['path'])for p in code],
        'scope':'Four native audits at most. Only exact published synthetic fixtures and identity-only memory copies; no real financial/source or outcome reads.',
        'history_entry_status':'Original builder slice remains stopped before auditor due absent knowledge checkpoint in minimal copy. This direct slice does not prove full history entry readiness or prescribe relaxing its gate.',
        'wall_seconds':monotonic()-start}
    result['confirmed_fixture_identity_defect']=len(rows)==4 and all(
        row['audit_status']==('rejected'if row['case']=='exact_published_positive'else'passed')for row in rows)
    write(result_path,result)
    print(json.dumps({'confirmed_fixture_identity_defect':result['confirmed_fixture_identity_defect'],
        'rows':[{'ref':r['signal_ref'],'case':r['case'],'status':r['audit_status'],
            'execution':r.get('actual_native_batch',{}).get('results',[{}])[0].get('execution')}for r in rows],
        'counts':counts,'source_unchanged':result['original_source_bytes_unchanged'],
        'code_unchanged':result['code_bytes_unchanged'],'wall_seconds':result['wall_seconds']},indent=2))


if __name__=='__main__':main()
