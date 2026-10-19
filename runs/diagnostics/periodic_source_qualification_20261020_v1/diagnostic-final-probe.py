"""Independent temporary preappend caller/actual prohibited-entrypoint checks."""
import ast,copy,hashlib,json,tempfile
from pathlib import Path
import diagnose_reviewed_periodic_operating_snapshot as m
R=Path(__file__).resolve().parents[3]
fixture_source=R/'runs/diagnostics/sec_response_profile_boundary_20261020_v1/probe.py'
tree=ast.parse(fixture_source.read_text());nodes=[]
for n in tree.body:
 if isinstance(n,(ast.Import,ast.ImportFrom,ast.FunctionDef,ast.ClassDef)):nodes.append(n)
 elif isinstance(n,ast.Assign) and all(isinstance(t,ast.Name) and t.id in {'D','R'} for t in n.targets):nodes.append(n)
ns={'__file__':str(fixture_source)};exec(compile(ast.Module(body=nodes,type_ignores=[]),'own-isolated-source-fixture','exec'),ns)
script=Path(m.__file__);before=hashlib.sha256(script.read_bytes()).hexdigest();assert before=='3dc7c3fb1a3e9e9113da48193f7b02f7d1616a3dbfd25a19faf09f002b17f188'
results={}
with tempfile.TemporaryDirectory() as tmp:
 for name in ('valid_primary','valid_exhibit','wrongSHA','duplicate_proof_kind','unknown_profile'):
  exhibit=name=='valid_exhibit';f=ns['Fixture'](Path(tmp)/name,exhibit=exhibit);f.save();proofs=copy.deepcopy(f.proofs)
  if name=='wrongSHA':proofs[0]['artifact']['sha256']='0'*64
  if name=='duplicate_proof_kind':proofs.append(copy.deepcopy(proofs[0]))
  profile='sec_filing_exhibit_response_v1' if exhibit else 'sec_filing_response_acceptance_v1'
  if name=='unknown_profile':profile='unknown-profile'
  candidate={'document':f.record,'proofs':proofs,'proof_profile':profile}
  try:
   with m._source_only():m._qualify([candidate],[{'company_id':f.company,'cutoff':'2025-07-31T00:00:00Z'}])
   result={'accepted':True}
  except Exception as e:result={'accepted':False,'type':type(e).__name__,'message':str(e)}
  assert result['accepted']==name.startswith('valid_'),(name,result)
  if not name.startswith('valid_'):assert result['type']=='ReviewedSourceRejected'
  results[name]=result
 targets=[(m.socket,'socket'),(m.socket,'create_connection'),(m.LabelStore,'load'),(m.LabelStore,'ground_truth'),(m.run_minimal_rounds,'prepare'),(m.StructuredRoleClient,'complete_json'),(m.StructuredRoleClient,'complete_json_with_token_scores'),(m.StructuredRoleClient,'complete_binary_token_with_scores'),(m.SignalExecutor,'execute_batch')]
 saved=[getattr(t,n) for t,n in targets];out=[]
 with m._source_only():
  for t,n in targets:
   try:getattr(t,n)();blocked=False
   except m.ReviewedSourceRejected:blocked=True
   assert blocked;out.append({'target':t.__name__+'.'+n,'blocked':blocked})
 results['actual_prohibition_entrypoints']=out
 results['tripwires_restored']=all(getattr(t,n)==v for (t,n),v in zip(targets,saved));assert results['tripwires_restored']
assert before==hashlib.sha256(script.read_bytes()).hexdigest()
result={'scope':'Independent actual native profile through preappend caller on own temporary primary/exhibit fixtures, plus actual9 patched methods; no publicprepare/execute/realcase/global/network/model/labels/apply','script_sha256':before,'results':results,'production_stage_exists':m.DEFAULT_OUTPUT.exists()}
p=Path(__file__).with_name('diagnostic-final-probe-results.json');p.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
