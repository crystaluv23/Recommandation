"""Temporary-only destination/freeze/retained-source counterexamples, not actual stage prep."""
from pathlib import Path
from copy import deepcopy
from contextlib import ExitStack
import hashlib,json,sys,types,tempfile
from unittest.mock import patch
import diagnose_reviewed_gpre_capture_snapshot as d
from tests.test_reviewed_gpre_capture_snapshot import CaptureStageFixture
from stock_opportunity_agent.models import ValidationError
HERE=Path(__file__).resolve().parent
OLD=HERE/'original-before-destination-guard.py.txt'
def bind(p):p=Path(p).resolve();return {'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
def tree(p):return [(str(x.relative_to(p)),bind(x)['sha256']) for x in sorted(Path(p).rglob('*')) if x.is_file()]
def rejected(fn):
 try:fn()
 except (d.ReviewedSourceRejected,FileNotFoundError):return True
 return False
assert bind(OLD)['sha256']=='88e80eab0e4e9f875a1475da0c90c10515f60f82ee82c668ada97f925f849e92'
old=types.ModuleType('original_gpre_marker_boundary');old.__file__=str(Path(d.__file__).resolve());sys.modules[old.__name__]=old
exec(compile(OLD.read_text(),str(OLD),'exec'),old.__dict__)
checks=[]
with tempfile.TemporaryDirectory() as td:
 base=Path(td).resolve();f=CaptureStageFixture(base/'old-prepare')
 protected=f.fixture.oracle;output=protected/'new-child';before=tree(protected)
 with patch.object(old,'_authorities',side_effect=d.ReviewedSourceRejected('new diagnostic overlaps a retained source root')):
  assert rejected(lambda:old.prepare(output))
 after=tree(protected);added=[p for p,h in after if p not in {x[0] for x in before}]
 assert added==['new-child/preparation-failure.json','new-child/preparation-start.json'],added
 checks.append({'case':'old_prepare_overlap_rejection','protected_files_added':added,'provenance':'Exact archived original prepare; actual authority rejection replaced by its overlap exception only, avoiding real old-stage reads.'})
 f=CaptureStageFixture(base/'old-execute');protected=f.base;before=tree(protected)
 assert rejected(lambda:old.execute(protected,'not-a-plan'))
 added=[p for p,h in tree(protected) if p not in {x[0] for x in before}]
 assert added==['execution-start.json','failure.json'],added
 checks.append({'case':'old_execute_missing_plan','protected_files_added':added})
 f=CaptureStageFixture(base/'new-destination')
 for label,target in [('oracle_child',f.fixture.oracle/'forbidden'),('old_stage_child',f.base/'forbidden'),('old_diagnosis_child',f.diagnosis.parent/'forbidden'),('old_view_child',Path(f.view['root'])/'forbidden')]:
  before=tree(f.root)
  with f.context():assert rejected(lambda:d.prepare(target))
  assert before==tree(f.root) and not target.exists()
  checks.append({'case':'new_prepare_'+label,'protected_tree_unchanged':True})
 for label,target in [('protected_old_stage',f.base),('unprepared_outside',f.root/'missing-new-stage')]:
  before=tree(f.root)
  with f.context():assert rejected(lambda:d.execute(target,'wrong'))
  assert before==tree(f.root)
  checks.append({'case':'new_execute_'+label,'tree_unchanged_no_marker':True})
 # Real temp prepare: only historical source authority is a small fixture; normalization/profile remain native.
 with f.context():plan=d.prepare(f.output)
 relocated=f.root/'relocated';relocated.mkdir();(relocated/'plan.json').write_text(json.dumps(plan));before=tree(f.root)
 with f.context():assert rejected(lambda:d.execute(relocated,plan['plan_hash']))
 assert before==tree(f.root)
 checks.append({'case':'new_execute_relocated_plan','tree_unchanged_no_marker':True})
 protected=f.fixture.oracle/'forged-stage';protected.mkdir();forged=deepcopy(plan);forged['output']=str(protected);forged['plan_hash']=d.canonical_json_hash({k:v for k,v in forged.items() if k!='plan_hash'});(protected/'plan.json').write_text(json.dumps(forged));before=tree(f.root)
 with f.context():assert rejected(lambda:d.execute(protected,forged['plan_hash']))
 assert before==tree(f.root)
 checks.append({'case':'new_execute_selfconsistent_protected_output','protected_tree_unchanged_no_marker':True})
 # Changed canonical record in retained row, even with a newly hashed binding, must not replace the53-equivalent branch.
 wrong=deepcopy(f.review);entry=wrong['records'][0];record=d._read_bound(entry['original_record'])[1];record['metadata']['requires_primary_filing_audit']=1
 bad=f.root/'wrong-retained-record.json';bad.write_text(json.dumps(record));entry['original_record']=bind(bad)
 with f.context():assert rejected(lambda:d._derive(f.case,wrong,f.fixture.oracle))
 checks.append({'case':'retained_legacy_fullrecord_type_drift','rehash_rejected':True})
 # Actual _code_bindings against temporary dependency paths, then verify each drift fails before re-derivation.
 f=CaptureStageFixture(base/'freeze')
 fake=f.root/'fake-repo';helper=f.root/'preappend-helper.py';helper.write_text('fixture frozen helper\n')
 rels=['scripts/run_reviewed_posthoc_stage.py','spec/scripts/run_reviewed_posthoc_stage.md','spec/scripts/diagnose_reviewed_frozen_source_snapshot.md',
       'spec/src/stock_opportunity_agent/data/raw_info.md','spec/src/stock_opportunity_agent/data/reviewed_companyfacts_profile.md','spec/src/stock_opportunity_agent/data/sec_company_facts.md']
 for rel in rels:
  q=fake/rel;q.parent.mkdir(parents=True,exist_ok=True);q.write_text('fixture frozen dependency\n')
 with f.context(),patch.object(d,'REPO',fake),patch.object(d.preappend,'__file__',str(helper)):
  plan=d.prepare(f.output)
  for target in [helper,fake/rels[1],fake/rels[2]]:
   assert bind(target) in plan['code_bindings'];raw=target.read_bytes();target.write_bytes(raw+b'drift')
   with patch.object(d,'_authorities',side_effect=AssertionError('code drift must reject before source rederivation')):
    assert rejected(lambda:d._verify_plan(f.output,plan['plan_hash']))
   target.write_bytes(raw)
   checks.append({'case':'frozen_dependency_drift','path_suffix':target.name,'rejected_before_authorities':True})
out={'verdict':'PASS_bounded_preflight','new_script_binding':bind(d.__file__),'new_spec_binding':bind(d.SPEC),'new_test_binding':bind(Path('tests/test_reviewed_gpre_capture_snapshot.py')),
 'old_script_binding':bind(OLD),'controls':checks,
 'scope':'Temporary fixtures only. Native normalizer/profile retained in positives; small count constants and historical-authority fixture only. No actual prepare/append/GET/models/LabelStore/LockedTest/fullprepare or actual old source-tree mutation.',
 'limits':['Actual global before inventory/four inserts/1780view/Q1 consumer values are future execution evidence, not established by this preflight.','Driver9 native controls cover full temporary execute/36resolutions/4BasicInfo; this audit does not rerun that entire set.']}
(HERE/'boundary-results.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
