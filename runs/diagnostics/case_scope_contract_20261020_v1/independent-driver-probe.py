"""Bounded temp-only review; forbid real mixed origin and LabelStore files."""
from pathlib import Path
from copy import deepcopy
from tempfile import TemporaryDirectory
from unittest.mock import patch
import contextlib,hashlib,io,json,sys
sys.path[:0]=['scripts','.']
import diagnose_reviewed_frozen_case_inputs as d
from tests.test_reviewed_frozen_case_inputs import FrozenCaseInputTests
ROOT=Path.cwd(); OUT=ROOT/'runs/diagnostics/case_scope_contract_20261020_v1'
checks=[]
class Secret(dict):
 def __getitem__(self,k):
  if k in {'ground_truth','basic_info','prose'}:raise AssertionError('forbidden field accessed')
  return super().__getitem__(k)
def check(name, f, rejection=False):
 try:f()
 except d.ReviewedSourceRejected as e:
  assert rejection, (name,str(e));checks.append({'name':name,'result':'rejected','reason':str(e)})
 else:
  assert not rejection, name+' was accepted';checks.append({'name':name,'result':'passed'})
def make():
 splits={};companies=[];n=0
 for split in ['evolution_validation','discovery','anchor']:
  rows=[]
  for i in range(d.COUNTS[split]):
   n+=1;c='cik_'+str(n).zfill(10)
   timestamp=['2025-01-01T08:00:00+08:00','2024-12-31T19:00:00-05:00','2025-01-01T00:00:00Z'][n%3]
   rows.append(Secret(case_id=c+':20250101',company_id=c,prediction_time=timestamp,ground_truth='TRUTH-SENTINEL',basic_info='PROSE-SENTINEL'))
   companies.append({'company_id':c,'cik':c[4:],'symbol':'TMP'+str(n),'company_name':'NOT-EXPORTED'})
  splits[split]=rows
 opaque='a'*64
 return ({'schema_version':'diagnostic-development-subset-v1','selection_seed':42,'selection_before_model_calls':True,'approved_manifest_hash':d.APPROVED_SHA,'locked_test_hash':opaque,'splits':splits}, {'companies':companies,'outcome_fields_included':False,'split_ownership_included':False}, {'approval_status':'human_approved','locked_test_sealed':True,'artifacts':{'locked_test':{'sha256':opaque}}})
realopen=Path.open
forbidden_origin=d.ORIGIN.resolve()
def guarded_open(self,*a,**kw):
 p=self.resolve()
 if p==forbidden_origin or '/outcome-label-store' in str(p) or p.name=='locked_test.json': raise AssertionError('forbidden real source opened: '+str(p))
 return realopen(self,*a,**kw)
with patch.object(Path,'open',guarded_open), TemporaryDirectory() as tmp:
 envelope,scope,approved=make();origin=Path(tmp)/'synthetic-envelope.json'
 origin.write_text(json.dumps(envelope));binding=d._stream_binding(origin)
 proj=d._project_cases(envelope,scope,approved,binding)
 expected=[(s,i,r['case_id'],r['company_id'],r['prediction_time']) for s,rows in envelope['splits'].items() for i,r in enumerate(rows)]
 assert [(r['split'],r['split_case_index'],r['case_id'],r['company_id'],r['prediction_time']) for r in proj['cases']]==expected
 assert proj['split_order']==list(envelope['splits']) and len(proj['cases'])==40
 assert all(x not in json.dumps(proj) for x in ('ground_truth','basic_info','TRUTH-SENTINEL','PROSE-SENTINEL','company_name','NOT-EXPORTED'))
 checks.append({'name':'original40 split/order/aware offset strings exact, secret fields not accessed or copied','result':'passed'})
 mutations=[('extra row field',lambda x:x['cases'][0].update(basic_info={})),('extra control prose',lambda x:x['origin_control'].update(prose='bad')),('count39',lambda x:x['cases'].pop()),('naive time',lambda x:x['cases'][0].update(prediction_time='2025-01-01T00:00:00')),('bool ordinal',lambda x:x['cases'][0].update(order=False)),('swapped rows',lambda x:x['cases'].__setitem__(slice(0,2),list(reversed(x['cases'][:2])))),('duplicate ID',lambda x:x['cases'][1].update(case_id=x['cases'][0]['case_id'])),('identity extra prose',lambda x:next(iter(x['identities'].values())).update(prose='bad'))]
 for name,mutate in mutations:
  v=deepcopy(proj);mutate(v);check(name,lambda v=v:d._validate_projection(v),True)
 for name,alter in [('seed bool',lambda e,s:e.update(selection_seed=True)),('wrong CIK',lambda e,s:s['companies'][0].update(cik='0000999999')),('missing company',lambda e,s:s['companies'].pop(0))]:
  e,s,a=make();alter(e,s);check(name,lambda:d._project_cases(e,s,a,binding),True)
 for name,version in [('default_v6',999),('latest_v12',6),('unknown_group',12)]:
  group={'name':name,'root':tmp,'version':version,'registry_hash':d.DEFAULT_HASH if name=='default_v6' else d.LATEST_HASH,'refs':list(d.DEFAULT_REFS)}
  with patch.object(d,'SignalRegistry') as registry:
   check('unknown Registry '+name+'/'+str(version),lambda:d._snapshot(group,Path(tmp)/'output'),True);registry.assert_not_called()
 # Reuse the existing *temp* actual-consumer wiring test. Real definition files
 # are copied; no real origin/source/LabelStore/approved splits are opened.
 with contextlib.redirect_stdout(io.StringIO()) as captured:
  t=FrozenCaseInputTests();t.test_execute_streams_origin_only_and_preserves_missing_source_40x18_twice()
 checks.append({'name':'actual temp execute:40BasicInfo+720v6+720v12 allgap,originJSON forbidden,terminal rerun rejected','result':'passed','saved_progress_lines':len(captured.getvalue().splitlines())})
 # Verify actual wrapper, not a synthetic replacement guard, and restoration.
 p=d.periodic
 targets=[(p.socket,'socket'),(p.socket,'create_connection'),(d.LabelStore,'load'),(d.LabelStore,'ground_truth'),(p.run_minimal_rounds,'prepare')]+[(p.StructuredRoleClient,n) for n in ('complete_json','complete_json_with_token_scores','complete_binary_token_with_scores')]+[(d.SignalExecutor,'execute_batch')]+[(d.LabelStore,n) for n in ('record','keys','label_contract','__len__')]
 originals=[getattr(o,n) for o,n in targets]
 with d._source_only():
  for o,n in targets:check('source-only '+n,lambda o=o,n=n:getattr(o,n)(),True)
 assert all(getattr(o,n)==v for (o,n),v in zip(targets,originals))
 checks.append({'name':'all actual wrappers restored','result':'passed'})
paths=['scripts/diagnose_reviewed_frozen_case_inputs.py','spec/scripts/diagnose_reviewed_frozen_case_inputs.md','tests/test_reviewed_frozen_case_inputs.py']
report={'scope':'Independent bounded temp-only projection and actual source-only consumer review. No actual origin/LabelStore/LockedTest or real prepare/execute opened; temp actual execute empty store is deterministic wiring only.','bindings':[{'path':str(ROOT/x),'sha256':hashlib.sha256((ROOT/x).read_bytes()).hexdigest()} for x in paths],'checks':checks,'all_passed':True,'limits':['Projection authenticity relies on the authorized source-owner freeze and exact projection/plan hashes; no signature claim against a wholly forged self-consistent graph.','Real40 cohort/source statuses and653 view were not executed in this independent temp review.','No numeric Signal validity, model behavior, fitness, or benefit established.']}
p=OUT/'driver-independent-review.json';p.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'all_passed':True,'checks':len(checks),'review_sha256':hashlib.sha256(p.read_bytes()).hexdigest()}))
