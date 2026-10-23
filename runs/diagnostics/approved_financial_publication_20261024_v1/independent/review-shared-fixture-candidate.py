"""Independent generic fixture regression review, with original Registry and real GPRE execution forbidden."""
from contextlib import ExitStack
from copy import deepcopy
from dataclasses import replace
from datetime import datetime,timezone
import ast,hashlib,json,subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from stock_opportunity_agent import signal_library as lib
from stock_opportunity_agent import models
from stock_opportunity_agent.research import signal_evolution as ev
from stock_opportunity_agent.llm.agent import AgentUsage
from stock_opportunity_agent.cases.label_store import LabelStore

ROOT=Path(__file__).resolve().parents[4];BASE=Path(__file__).resolve().parents[1];OUT=Path(__file__).resolve().parent
EXPECTED={'src/stock_opportunity_agent/signal_library.py':'d7490eb612baeb01e65a7db5a734dd14b19abd5fb492096ba82c51401e89ade6','src/stock_opportunity_agent/research/signal_evolution.py':'2d01548090c0338b1655bb8a757534ec06577890fdcefd31e2106fa7b6103e35'}
bindings={}
def read(path):
 p=Path(path);raw=p.read_bytes();bindings[str(p.resolve())]=hashlib.sha256(raw).hexdigest();return json.loads(raw)
def bind(path):
 p=Path(path);raw=p.read_bytes();bindings[str(p.resolve())]=hashlib.sha256(raw).hexdigest();return raw.decode()
for path,h in EXPECTED.items():assert hashlib.sha256(bind(ROOT/path).encode()).hexdigest()==h
bind(ROOT/'spec/src/stock_opportunity_agent/signal_library.md');bind(ROOT/'spec/src/stock_opportunity_agent/research/signal_evolution.md')
# The exact original candidate materializer remains an independent compatibility reference.
before=subprocess.check_output(['git','show','HEAD:src/stock_opportunity_agent/research/signal_evolution.py'],cwd=ROOT,text=True)
tree=ast.parse(before);cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='SignalCandidateValidator');method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='_execute_fixture');assert len(method.body)>5
module=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),method],type_ignores=[]);ast.fix_missing_locations(module);namespace=dict(ev.__dict__);exec(compile(module,'git:HEAD:original_candidate_fixture','exec'),namespace);old_execute=namespace['_execute_fixture']
base_spec=lib.SignalSpec(signal_id='independent_cash_fixture',version=1,category='financial',description='Measure latest cash reserves.',execution_type=lib.SignalExecutionType.DETERMINISTIC,function='financial.cash_reserves',source_types=('financials',),modality=lib.SignalModality.STRUCTURED,parameters={'positive_min':50,'negative_max':0},retrieval_policy=lib.SignalRetrievalPolicy(query_terms=('cash balance',)))
body=dict(schema_version='sec-company-facts-document-v1',cik='0000000001',filing_date='2025-05-08',form='10-Q',facts=[dict(tag='CashAndCashEquivalentsAtCarryingValue',start=None,end='2025-03-31',value=100,unit='USD')])
fixture=dict(name='independent-explicit-cash',company_id='cik_0000000001',as_of='2025-05-30T00:00:00+00:00',expected='positive',documents=[dict(source_type='sec_company_facts',published_at='2025-05-08T00:00:00+00:00',available_at='2025-05-09T00:00:00+00:00',metadata={'cik':'0000000001'},content=json.dumps(body,sort_keys=True,separators=(',',':')))])
validator=ev.SignalCandidateValidator(SimpleNamespace(),llm_runner=None)
rows=[];dispatches=[];audit_results=[]
original_execute_batch=lib.SignalExecutor.execute_batch;original_append=lib.RawInfoStore.append;original_register=lib.SignalRegistry.register_stable;original_audit=lib.SignalRegistry.audit_capabilities

def forbid(*args,**kwargs):raise AssertionError('forbidden real data / publication / labels / network')
def safe_execute(self,*args,**kwargs):
 assert kwargs.get('company_id')!='cik_0001309402'
 for doc in self.raw_info_store.documents:
  assert doc.company_id!='cik_0001309402' and str(doc.metadata.get('cik','')).zfill(10)!='0001309402'
  assert not doc.document_id.startswith(('rawcap:','secfacts:'))
 batch=original_execute_batch(self,*args,**kwargs)
 dispatches.append(dict(refs=list(args[0]) if args else [],company_id=kwargs.get('company_id'),result_values=[r.value.value for r in batch.results],execution_statuses=[r.execution_status.value for r in batch.results]))
 return batch
def safe_append(self,doc):
 assert self.root is None,'persistent Raw Info append forbidden';return original_append(self,doc)
def scratch_register(self,*args,**kwargs):
 assert Path(self.root).resolve().is_relative_to(OUT.resolve()),'original stable write forbidden';return original_register(self,*args,**kwargs)
def audit_spy(self,*args,**kwargs):
 r=original_audit(self,*args,**kwargs);audit_results.append(dict(root=str(self.root),audit=r.to_dict()));return r

def call(fn):
 try:fn()
 except Exception as exc:return dict(accepted=False,type=type(exc).__name__,error=str(exc))
 return dict(accepted=True)
def both(name,fx,*,want=True,spec=base_spec,runner=None,override=None):
 v=ev.SignalCandidateValidator(SimpleNamespace(),llm_runner=runner,deterministic_functions=override)
 a=call(lambda:v._execute_fixture(spec,None,fx,index=0));b=call(lambda:lib._audit_deterministic_fixture(spec,fx,index=0));old=call(lambda:old_execute(v,spec,None,fx,index=0))
 errors=[]
 if a['accepted']!=want or b['accepted']!=want:errors.append('candidate/stable expected acceptance mismatch')
 if a!=b:errors.append('candidate and stable differ')
 if a!=old:errors.append('original candidate behavior drift')
 rows.append(dict(name=name,candidate=a,stable=b,original_candidate=old,failures=errors))

with ExitStack() as stack:
 for owner,name in [(lib.SignalExecutor,'execute_batch'),(lib.RawInfoStore,'append'),(lib.SignalRegistry,'register_stable'),(lib.SignalRegistry,'audit_capabilities')]:
  replacement={'execute_batch':safe_execute,'append':safe_append,'register_stable':scratch_register,'audit_capabilities':audit_spy}[name];stack.enter_context(patch.object(owner,name,replacement))
 for target in ('socket.socket','socket.create_connection'):stack.enter_context(patch(target,forbid))
 for name in ('__init__','load','record','ground_truth'):stack.enter_context(patch.object(LabelStore,name,forbid))
 stack.enter_context(patch.object(lib.SignalRegistry,'promote_validated_batch',forbid))
 both('typed_source_alias',fixture)
 canonical=deepcopy(fixture);canonical['documents'][0]['metadata']={};canonical['documents'][0]['source_type']='financials';both('canonical_fixture_company_no_metadata',canonical)
 mismatch=deepcopy(fixture);badbody=deepcopy(body);badbody['cik']='0000000002';mismatch['documents'][0]['content']=json.dumps(badbody,sort_keys=True,separators=(',',':'));mismatch['documents'][0]['metadata']={'cik':'0000000002'};mismatch['expected']='unavailable';both('metadata_and_body_cannot_hide_wrong_declared_company',mismatch,want=False)
 for val in ({'facts':[]},['not text'],None,123):
  x=deepcopy(fixture);x['documents'][0]['content']=val;x['expected']='unavailable';both('nonstring_'+type(val).__name__,x,want=False)
 opaque=deepcopy(fixture);opaque.pop('company_id');both('opaque_default_with_explicit_body_and_metadata',opaque)
 missing=deepcopy(opaque);missing['documents'][0]['metadata']={};both('opaque_missing_metadata',missing,want=False)
 missing=deepcopy(opaque);bad=deepcopy(body);bad.pop('cik');missing['documents'][0]['content']=json.dumps(bad,sort_keys=True,separators=(',',':'));both('body_CIK_missing',missing,want=False)
 for name,mutate in [('name_missing',lambda x:x.pop('name')),('documents_empty',lambda x:x.update(documents=[])),('naive_cutoff',lambda x:x.update(as_of='2025-05-30T00:00:00')),('naive_source_clock',lambda x:x['documents'][0].update(available_at='2025-05-09T00:00:00')),('bad_company_id',lambda x:x.update(company_id='BAD ID')),('unrelated_source',lambda x:x['documents'][0].update(source_type='market_data'))]:
  x=deepcopy(fixture);mutate(x);both(name,x,want=False)
 future=deepcopy(fixture);future['documents'][0].update(published_at='2025-06-01T00:00:00+00:00',available_at='2025-06-02T00:00:00+00:00');future['expected']='unavailable';before_count=len(dispatches);both('closed_all_future_unavailable',future);assert len(dispatches)==before_count
 future_positive=deepcopy(future);future_positive['expected']='positive';before_count=len(dispatches);both('closed_all_future_positive_rejected',future_positive,want=False);assert len(dispatches)==before_count
 mixed=deepcopy(fixture);late=deepcopy(future['documents'][0]);latebody=deepcopy(body);latebody['facts'][0]['value']=-100;late['content']=json.dumps(latebody,sort_keys=True,separators=(',',':'));mixed['documents'].append(late);both('visible_positive_future_negative_cannot_replace',mixed)
 filed=deepcopy(fixture);latebody=deepcopy(body);latebody['filing_date']='2025-05-30';filed['documents'][0]['content']=json.dumps(latebody,sort_keys=True,separators=(',',':'));filed['expected']='unavailable';both('body_filing_conservative_PIT_not_visible',filed)
 # Every actual independently approved fixture passes both real generic executor paths.
 approved=read(ROOT/'runs/diagnostics/financial_period_policy_20261023_v1/independent/new-version-specs.json');generic=read(ROOT/'runs/diagnostics/financial_period_policy_20261023_v1/independent/lineage-fixtures.json');approved_checks=[]
 for obj in approved['specs']:
  s=lib.SignalSpec.from_dict(obj)
  for i,fx in enumerate(generic['by_ref'][s.ref]):
   a=call(lambda:validator._execute_fixture(s,None,fx,index=i));b=call(lambda:lib._audit_deterministic_fixture(s,fx,index=i));assert a['accepted'] and b['accepted'],(s.ref,fx['name'],a,b);approved_checks.append(dict(ref=s.ref,name=fx['name'],candidate=a,stable=b))
 # Fresh corrected source seed: ordinary init and freeze in a disposable synthetic review registry.
 seedpath=ROOT/'configs/signals_v1.json';seed=read(seedpath);scratch=OUT/'fixture-audit-candidate-seed-control-v2';assert not scratch.exists();seedreg=lib.SignalRegistry(scratch/'signals',candidate_root=scratch/'candidates');installed=seedreg.install_catalog(seedpath);seed_snapshot=seedreg.freeze();assert installed==len(seed_snapshot.specs)==14
 # Read-only old full18 registry object: constructor not called and no files written.
 authority=read(ROOT/'runs/diagnostics/current_financial_apply_20261021_v1/native/stage/plan.json')['group'];oldroot=Path(authority['root']);legacy=lib.SignalRegistry.__new__(lib.SignalRegistry);legacy.root=oldroot;legacy.knowledge_workspace_root=oldroot.parent;legacy.candidate_root=OUT/'unused-original-candidate-path';legacy._transition_recovery_active=False;legacy._fault_injector=None
 before_files={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in oldroot.rglob('*') if p.is_file()};old_outcome=call(legacy.freeze);assert not old_outcome['accepted'];legacy_audit=audit_results[-1]['audit'];assert len(legacy_audit['disabled'])==9 and len(legacy_audit['enabled_refs'])==9
 after_files={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in oldroot.rglob('*') if p.is_file()};assert before_files==after_files
 for ref,reasons in legacy_audit['disabled'].items():assert 'issuer' in str(reasons) or 'CIK' in str(reasons),(ref,reasons)
 # Explicit current callable override is preserved for candidate execution; stable audit intentionally uses stable default table.
 def override(s,docs,asof):
  d=docs[0];return lib.SignalResult(signal_id=s.signal_id,version=s.version,value=lib.SignalValue.NEGATIVE,confidence=1,interpretation='Scripted override control.',supporting_evidence=(lib.SignalEvidence(document_id=d.document_id,exact_span=d.content,timestamp=d.available_at),))
 ov=ev.SignalCandidateValidator(SimpleNamespace(),llm_runner=None,deterministic_functions={base_spec.function:override});ovfx=deepcopy(fixture);ovfx['expected']='negative';override_current=call(lambda:ov._execute_fixture(base_spec,None,ovfx,index=0));override_old=call(lambda:old_execute(ov,base_spec,None,ovfx,index=0));override_stable=call(lambda:lib._audit_deterministic_fixture(base_spec,ovfx,index=0));assert override_current==override_old=={'accepted':True} and not override_stable['accepted']
 # Scripted LLM fixture runner verifies forwarding only; it is not a real role/API.
 class Runner:
  def __init__(self,failed=False):self.calls=[];self.failed=failed
  def execute(self,s,documents,skill,asof):
   self.calls.append(dict(ref=s.ref,skill=skill,company_ids=[d.company_id for d in documents]))
   if self.failed:r=lib.signal_execution_failure_result(s,status=lib.SignalExecutionStatus.VALIDATION_FAILED,error_code='scripted_control',error_message='scripted failure')
   else:
    d=documents[0];r=lib.SignalResult(signal_id=s.signal_id,version=s.version,value=lib.SignalValue.POSITIVE,confidence=1,interpretation='Synthetic narrative control.',supporting_evidence=(lib.SignalEvidence(document_id=d.document_id,exact_span=d.content,timestamp=d.available_at),))
   return r,AgentUsage(llm_calls=1)
 narrative=lib.SignalSpec(signal_id='independent_narrative',version=1,category='orders',description='Measure a synthetic disclosed condition.',execution_type=lib.SignalExecutionType.LLM,skill_file='skill.md',source_types=('news',),modality=lib.SignalModality.NARRATIVE,retrieval_policy=lib.SignalRetrievalPolicy(query_terms=('synthetic condition',)))
 nfx=dict(name='scripted-narrative',company_id='synthetic_company',as_of=fixture['as_of'],expected='positive',documents=[dict(source_type='company_news',published_at='2025-05-08T00:00:00+00:00',available_at='2025-05-09T00:00:00+00:00',content='The synthetic condition was disclosed.')]);skill='Full synthetic skill. '*1000;runner=Runner();nv=ev.SignalCandidateValidator(SimpleNamespace(),llm_runner=runner);nr=call(lambda:nv._execute_fixture(narrative,skill,nfx,index=0));no=call(lambda:old_execute(nv,narrative,skill,nfx,index=0));assert nr==no=={'accepted':True} and all(c['skill']==skill for c in runner.calls)
 unavailable_narrative=deepcopy(nfx);unavailable_narrative['expected']='unavailable';bad_runner=Runner(failed=True);bv=ev.SignalCandidateValidator(SimpleNamespace(),llm_runner=bad_runner);bad_now=call(lambda:bv._execute_fixture(narrative,skill,unavailable_narrative,index=0));bad_old=call(lambda:old_execute(bv,narrative,skill,unavailable_narrative,index=0));assert bad_now==bad_old and not bad_now['accepted'] and 'technical execution failure' in bad_now['error']
 future_narrative=deepcopy(unavailable_narrative);future_narrative['documents'][0]['available_at']='2025-06-02T00:00:00+00:00';count=len(runner.calls);future_narrative_result=call(lambda:nv._execute_fixture(narrative,skill,future_narrative,index=0));assert future_narrative_result=={'accepted':True} and len(runner.calls)==count
 # Pure kernel and unrelated lifecycle bodies must stay unchanged from HEAD after adapter extraction.
 oldtree=ast.parse(subprocess.check_output(['git','show','HEAD:src/stock_opportunity_agent/signal_library.py'],cwd=ROOT,text=True));newtree=ast.parse((ROOT/'src/stock_opportunity_agent/signal_library.py').read_text());oldnodes={n.name:n for n in oldtree.body if isinstance(n,ast.FunctionDef)};newnodes={n.name:n for n in newtree.body if isinstance(n,ast.FunctionDef)}
 unchanged=[]
 for name in ['_revenue_acceleration_signal','_gross_margin_change_signal','_revenue_acceleration_adjacent_signal','_gross_margin_change_yoy_signal','_numeric_result','_sec_facts','_liquidity_runway_months_signal']:
  assert ast.dump(oldnodes[name],include_attributes=False)==ast.dump(newnodes[name],include_attributes=False),name;unchanged.append(name)

assert all(not row['failures'] for row in rows),[r for r in rows if r['failures']]
for p,h in EXPECTED.items():assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h
report=dict(status='shared_fixture_candidate_independent_review_passed_legacy_identity_block_remains',code_bindings=EXPECTED,original_four_families_and_extended_controls=rows,approved_generic_fixtures_both_entries=approved_checks,approved_fixture_count=len(approved_checks),fresh_seed_catalog=dict(source=str(seedpath),source_sha256=bindings[str(seedpath.resolve())],installed=installed,enabled=len(seed_snapshot.specs),snapshot_hash=seed_snapshot.registry_hash,audit=next(r['audit'] for r in audit_results if r['root']==str(scratch/'signals'))),original18=dict(fresh_freeze=old_outcome,audit=legacy_audit,all_original_file_bytes_and_members_unchanged=len(before_files)),override=dict(candidate_current=override_current,candidate_original=override_old,stable_default=override_stable,meaning='Candidate preserves explicit runtime override; stable capability audit correctly checks registered stable default, not caller override.'),LLM_scripted=dict(current=nr,original=no,full_skill_forwarded=True,scripted_runner_calls=len(runner.calls)+len(bad_runner.calls),technical_failure_unavailable_rejected=bad_now,all_future_short_circuit=future_narrative_result,production_role_calls=0),unchanged_algorithm_AST=unchanged,source_case_guard='Every fixture execute_batch denied real GPRE company/CIK and rawcap/secfacts source IDs; all outputs here are synthetic/source-catalog fixtures.',execution_counts=dict(generic_fixture_batches=len(dispatches),real_GPRE_Signal=0,real_roles=0,external_API=0,network=0,labels=0,publication=0,original_Registry_mutations=0),initialization_scope='Only disposable reviewed seed-catalog Registry initialized under independent/fixture-audit-candidate-seed-control. This is a generic positive control, not actual approved-version publication or repair of the original clone.',remaining_block='The original nine financial fixtures remain honestly missing body/meta CIK and the full18 clone cannot fresh-freeze. S7 original-clone stays stopped at preparation failure; no migration, hidden fixture edits or reset baseline is authorized by this repair.',prior_sentinel_evidence='fixture-audit-counterreview-v1.json and bindings remain unchanged; current execution supplements them.',reviewer_product_edits=0)
p=OUT/'fixture-audit-candidate-review.json';assert not p.exists();p.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n');bindings[str(Path(__file__).resolve())]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest();bindings[str(p.resolve())]=hashlib.sha256(p.read_bytes()).hexdigest();bp=OUT/'fixture-audit-candidate-review-bindings.json';assert not bp.exists();bp.write_text(json.dumps(bindings,indent=2)+'\n')
print(json.dumps(dict(status=report['status'],extended_controls=len(rows),approved_both_entries=len(approved_checks),seed_enabled=14,original18_enabled=9,original18_missing_identity=9,generic_fixture_batches=len(dispatches),actual_roles=0,real_GPRE_Signal=0,report_sha256=bindings[str(p.resolve())])))
