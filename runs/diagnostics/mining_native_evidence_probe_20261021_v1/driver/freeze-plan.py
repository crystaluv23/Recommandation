"""Bind exact existing sources/control inputs without executing native helpers."""
import ast,hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];REPO=ROOT.parents[2]
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
read=lambda p:json.loads(Path(p).read_text())
exact=ROOT/'oracle/exact-inputs.json';expectations=ROOT/'oracle/source-expectations-v2.json'
assert sha(exact)=='9e7b5674c344dd26043d1978a0b62b56d6badb1bb878427720434dd2d9f77e63'
assert sha(expectations)=='27e5b72f16f710d9d04dfb242d4a281e4ca3c939b6a521e059c7511b0e1f3355'
snapshot=REPO/'runs/diagnostics/reviewed_gpre_capture_snapshot_20261021_v1/stage/snapshot'
review=read(snapshot/'reviewed_snapshot.json')['source_review']
paths={ROOT/'probe.py',ROOT/'spec.md',exact,expectations,ROOT/'oracle/source-expectations.json',REPO/'runs/diagnostics/mining_positive_frontier_20261021_v1/oracle/preflight-diagnosis.json',REPO/'runs/diagnostics/mining_positive_frontier_20261021_v1/oracle/static-inventory.json'}
paths.update((REPO/'src/stock_opportunity_agent').rglob('*.py'))
for name in ['signal_mining_agent','evolution_core','stage_contracts']:
 paths.add(REPO/f'spec/src/stock_opportunity_agent/research/{name}.md')
for name in ['raw_info','reviewed_snapshot']:
 paths.add(REPO/f'spec/src/stock_opportunity_agent/data/{name}.md')
paths.update(p for p in snapshot.rglob('*') if p.is_file())
def addbindings(value):
 if isinstance(value,dict):
  if isinstance(value.get('path'),str) and isinstance(value.get('sha256'),str):
   p=Path(value['path']);p=p if p.is_absolute() else REPO/p
   assert sha(p)==value['sha256'],str(p)
   paths.add(p.resolve())
  for child in value.values():addbindings(child)
 elif isinstance(value,list):
  for child in value:addbindings(child)
addbindings(review);addbindings(read(review['path']))
# Parse syntax only: this preparation never imports or calls the probe/native code.
ast.parse((ROOT/'probe.py').read_text())
plan={'schema_version':'bounded-native-evidence-probe-v1','prepared_on_revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
 'output_root':str(ROOT.resolve()),'execution_root':str((ROOT/'execution').resolve()),
 'exact_inputs':{'path':str(exact.resolve()),'sha256':sha(exact)},
 'expectations':{'path':str(expectations.resolve()),'sha256':sha(expectations)},
 'reviewed_binding':{'root':str(snapshot.resolve()),'manifest_sha256':sha(snapshot/'reviewed_snapshot.json'),'store_type':'reviewed'},
 'controls':['O1-original-selection','O2-original-context-and-projection','L1-legacy-val-positive','T1-small-typed-value','R1-role-unit-conflict','P1-document-selection-and-PIT','P2-row-PIT'],
 'native_helper_call_upper_bounds':{'external_fetch_case_evidence':3,'external_company_facts_context':5,'external_project_facts_from_documents':7,'external_build_same_concept_relations':2,'external_compute_statistic':6,'including_nested_context_calls':15},
 'forbidden':{'LLM':0,'Signal':0,'GET':0,'labels':0,'source_append':0,'full_Engine_or_case_reconstruction':0},
 'expectation_policy':'V2 source-only fixed diagnostic expectations; preserve all native mismatches/outputs, no all-green demand or rerun. V1 retained as original wording provenance.',
 'bindings':[{'path':str(p.resolve()),'sha256':sha(p)} for p in sorted(paths)]}
with (ROOT/'plan.json').open('x') as out:json.dump(plan,out,indent=2,sort_keys=True);out.write('\n')
summary={'plan_sha256':sha(ROOT/'plan.json'),'script_sha256':sha(ROOT/'probe.py'),'spec_sha256':sha(ROOT/'spec.md'),'source_binding_count':len(plan['bindings']),'control_count':7,'native_probe_executions':0,'native_helper_calls':0,'execution_directory_exists':(ROOT/'execution').exists()}
with (ROOT/'driver/freeze-summary.json').open('x') as out:json.dump(summary,out,indent=2,sort_keys=True);out.write('\n')
print(json.dumps(summary))
