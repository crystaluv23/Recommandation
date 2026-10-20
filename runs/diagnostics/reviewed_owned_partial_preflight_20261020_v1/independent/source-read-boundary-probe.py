"""Temporary metadata chain only; no formal prepare or actual reviewed-store open."""
import ast,json,hashlib,tempfile
from pathlib import Path
from unittest.mock import patch
import run_reviewed_owned_partial_stage as s
from test_reviewed_owned_partial_stage import ReviewedOwnedPartialStageTests
HERE=Path(__file__).resolve().parent
OLD=HERE.parent/'formal-prepare-string-path-failure-candidate.py'
def b(p):return {'path':str(Path(p).resolve()),'sha256':hashlib.sha256(Path(p).read_bytes()).hexdigest()}
def ast_without_reader(path):
 tree=ast.parse(Path(path).read_text())
 tree.body=[n for n in tree.body if not (isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name=='read') and not (
  isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='read' for t in n.targets))]
 return ast.dump(tree,include_attributes=False)
assert b(OLD)['sha256']=='b417da2c5150f5486c78745198b889a768ada308eaf695410133dd9c265239b7'
assert ast_without_reader(OLD)==ast_without_reader(s.__file__),'source changed beyond read boundary; review separately'
f=ReviewedOwnedPartialStageTests();f.setUp();base=f.base
try:
 source=base/'completed-source';source.mkdir(exist_ok=True)
 snapshot=base/'readonly-snapshot';snapshot.mkdir();doc=snapshot/'document.json';f.write(doc,{'temporary':'bound canonical body placeholder'})
 view={'root':str(snapshot),'manifest_sha256':'temporary','store_type':'reviewed'}
 proof=source/'proof.json';f.write(proof,{'local':'source metadata fixture, not admission proof'})
 review=source/'source-review.json';f.write(review,{'proof':b(proof),'document':b(doc)})
 plan=source/'plan.json';f.write(plan,{'plan_hash':'temporary-plan','source_bindings':[b(proof)],'code_bindings':[b(f.code)]})
 f.write(source/'input_manifest.json',{'plan':b(plan),'source_review':b(review),'reviewed_source_snapshot':view})
 result=source/'result.json';f.write(result,{'status':'completed','fixed_cases':40,'per_group_inputs':720,
  'labels':False,'models':0,'GETs':0,'plan_hash':'temporary-plan','reviewed_source_snapshot':view,'source_review':b(review)})
 expected=json.loads(f.oracle.read_text());expected['bindings']['completed_source_result']=b(result)
 expected['bindings'].update(source_review=b(review),actual_cited_body=b(doc));f.write(f.oracle,expected)
 out={'source_bindings_all_serialized_strings':True,'original_failures':[],'public_temp_prepare':[]}
 # Archived original function body, isolated with its unchanged original reader.
 oldtree=ast.parse(OLD.read_text());fn=next(n for n in oldtree.body if isinstance(n,ast.FunctionDef) and n.name=='_source')
 globals_={'read':s.prefix.read_json,'binding':s.binding,'_nested':s._nested,'_unique':s._unique,'Path':Path,'ValidationError':s.ValidationError}
 exec(compile(ast.Module(body=[fn],type_ignores=[]),str(OLD),'exec'),globals_)
 try:globals_['_source'](result)
 except AttributeError as exc:out['original_failures'].append({'where':'serialized plan path','type':type(exc).__name__,'message':str(exc)})
 else:raise AssertionError('old full source unexpectedly accepted')
 def partial_read(path):return s.prefix.read_json(Path(path) if str(path)==str(plan) else path)
 globals_['read']=partial_read
 try:globals_['_source'](result)
 except AttributeError as exc:out['original_failures'].append({'where':'serialized review path after only plan conversion','type':type(exc).__name__,'message':str(exc)})
 else:raise AssertionError('old partial plan-only fix unexpectedly accepted review string')
 with s._guard():
  loaded,files=s._source(result)
  assert loaded==view
  for x in (plan,review,proof,doc,result,source/'input_manifest.json'):assert b(x) in files,(x,files)
  s._check(files)
  assert s.read(str(proof))==s.read(proof)
 # Public entry only: seed provenance and source qualification stubbed; source JSON chain/read remain real.
 for kind,arg in [('Path',result),('str',str(result))]:
  dest=base/('temporary-stage-'+kind)
  with patch.object(s,'SEED',f.seed),patch.object(s,'_seed',return_value=(f.sample,[b(f.seed/'inputs.json'),b(f.seed/'completion.json')])), \
    patch.object(s,'_preflight',return_value={'temporary_metadata_probe':True}), \
    patch.object(s.prefix,'_code_bindings',return_value=[b(f.code)]), \
    patch.object(s,'open_raw_info_store',side_effect=AssertionError('no actual store allowed')):
   s.prepare(dest,f.oracle,arg,'a'*40)
   assert not (dest/'exchange').exists()
   s._verify(dest)
   for changed in (plan,review,proof):
    before=changed.read_bytes();changed.write_bytes(before+b' ')
    try:s._verify(dest)
    except s.ValidationError:pass
    else:raise AssertionError('bound path drift accepted')
    changed.write_bytes(before)
  out['public_temp_prepare'].append({'source_argument':kind,'status':'accepted_temp_metadata_chain','frozen_plan_review_proof_drift_rejected':True,'exchange_exists':False})
 out.update(status='PASS_bounded_read_boundary',old_source_binding=b(OLD),new_code_bindings=[b(s.__file__),b(s.SPEC),b(Path('tests/test_reviewed_owned_partial_stage.py'))],
  unchanged_module_AST_except_read_boundary=True,unchanged_budget_and_BasicInfo_AST=True,
  limits='Temporary metadata only. _seed and _preflight qualification intentionally stubbed, but _source/read not stubbed. No actual source-store open, formal prepare, model, GET, labels or production-stage mutation. Does not establish fresh-model behavior or complete source admission.')
 (HERE/'source-read-boundary-results.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
finally:f.doCleanups()
