"""Read/stream-hash only the frozen source-completion plan, never execute it."""
from pathlib import Path
from collections import Counter
import hashlib,json
from stock_opportunity_agent.artifacts import canonical_json_hash
P=Path(__file__).resolve().parent;path=P/'stage/plan.json';raw=path.read_bytes();file_sha=hashlib.sha256(raw).hexdigest();assert file_sha=='b099d0af1ecc3720faaa23b884cb810122408c2b7470d494a81b7e4195987761';plan=json.loads(raw)
assert plan['plan_hash']==canonical_json_hash({k:v for k,v in plan.items() if k!='plan_hash'})=='114a50b2b037409e36eee1439ca1497d94d183df8d342ba984b3f6b8e2ffeb50'
assert plan['schema_version']=='frozen40-source-completion-plan-v1' and plan['output']==str((P/'stage').resolve())
assert type(plan['fixed_cases']) is int and plan['fixed_cases']==40 and plan['per_group_inputs']==720 and plan['basic_info_cases']==40
flags=['network_allowed','models_allowed','labels_allowed','apply_allowed','full_prepare_allowed'];assert all(plan[k] is False for k in flags)
assert len(plan['source_bindings'])==3230 and len(plan['code_bindings'])==114
seen={};total=0;scopes={};forbidden=[]
for group in ['source_bindings','code_bindings']:
 scopes[group]=[]
 for binding in plan[group]:
  p=Path(binding['path']).resolve();assert p.is_file()
  if p.name=='input_manifest.json' and 'minimal_rounds_v182_integrated' in str(p):forbidden.append(str(p))
  key=str(p)
  if key in seen:assert seen[key]==binding['sha256']
  else:
   digest=hashlib.sha256()
   with p.open('rb') as h:
    for chunk in iter(lambda:h.read(1024*1024),b''):digest.update(chunk)
   assert digest.hexdigest()==binding['sha256'],str(p);seen[key]=binding['sha256']
  scopes[group].append(binding);total+=1
assert not forbidden
bundle_binding=plan['bundle'];br=Path(bundle_binding['path']).read_bytes();assert hashlib.sha256(br).hexdigest()==bundle_binding['sha256']=='47406a0dd8e31eb35ae7ae6bfe7660f0669f8cbddcfe40b3cac171744d01a345';bundle=json.loads(br)
sourcepaths={b['path'] for b in plan['source_bindings']};code={b['path']:b['sha256'] for b in plan['code_bindings']}
actualids=[]
for c in bundle['candidates']:
 dr=Path(c['document']['path']).read_bytes();assert hashlib.sha256(dr).hexdigest()==c['document']['sha256'];actualids.append(json.loads(dr)['document_id'])
assert len(actualids)==len(set(actualids))==1123 and sorted(actualids)==plan['qualified_ids']
oldplan=json.loads(Path(bundle['original40_plan']['path']).read_bytes());assert plan['groups']==oldplan['groups']
projection=json.loads(Path(bundle['projection']['path']).read_bytes());assert len(projection['cases'])==40
assert Counter(c['split'] for c in projection['cases'])=={'anchor':16,'evolution_validation':8,'discovery':16}
groups=plan['groups'];assert [g['name'] for g in groups]==['default_v6','latest_v12'] and [g['version'] for g in groups]==[6,12]
assert [g['registry_hash'] for g in groups]==['ced3882945003998224b6b9a3c206e4bfc2f01eec6fc8857864350848a08be24','40a451c051b0bfbdf424121a5362405f2fae6672c2be7b0f51e8072e8bd4ae8d']
for g in groups:assert len(g['refs'])==len(set(g['refs']))==18 and 40*len(g['refs'])==720
for rel in ['scripts/diagnose_reviewed_frozen_source_snapshot.py','spec/scripts/diagnose_reviewed_frozen_source_snapshot.md','spec/src/stock_opportunity_agent/data/reviewed_market_profile.md']:
 assert str((Path.cwd()/rel).resolve()) in code
assert code[str(Path('scripts/diagnose_reviewed_frozen_source_completion.py').resolve())]=='3771191d0df656526c77bfb8a75d6c62bbe50ebecf853c960a644892c81b9c7c'
base=json.loads(Path(bundle['base_inputs']['path']).read_bytes());oldreview=json.loads(Path(base['source_review']['path']).read_bytes());oracle=Path(oldreview['oracle_identity']['path']).resolve().parent
protected=[oracle,Path(base['reviewed_source_snapshot']['root']).resolve(),Path(bundle['preappend_result']['path']).resolve().parent]
assert all(not (Path(plan['output']).is_relative_to(root) or root.is_relative_to(Path(plan['output']))) for root in protected)
assert not(P/'stage/execution-start.json').exists() and not(P/'stage/result.json').exists()
assert hashlib.sha256(path.read_bytes()).hexdigest()==file_sha
result={'schema_version':'bounded-frozen-plan-independent-review-v1','plan':{'path':str(path.resolve()),'sha256':file_sha,'canonical_hash':plan['plan_hash']},'all_current_bindings_passed':True,'source_bindings':3230,'code_bindings':114,'total_declared_bindings':total,'unique_current_paths_hashed':len(seen),'binding_sets_canonical_sha256':{k:canonical_json_hash(v) for k,v in scopes.items()},'qualified_ids_exact_bundle':1123,'fixed_cases':40,'splits':dict(Counter(c['split'] for c in projection['cases'])),'registry_groups':[{'name':g['name'],'version':g['version'],'registry_hash':g['registry_hash'],'refs':g['refs'],'case_input_denominator':720} for g in groups],'explicit_prohibitions':{k:plan[k] for k in flags},'basic_info_denominator':40,'no_existing_stage_resumed':True,'output_protected_root_overlap':False,'actual_execution_not_started':True,'blocking_findings':[],'limits':['Original reviewer fixture expected split label validation rather than actual evolution_validation and failed after hash loop; preserved as harness error, no product defect.','Read/stream-hash and canonical scope audit only; no _load_bundle/prepare/execute/Store/materializer/nativeconsumer/GET/model/LabelStore/LockedTest.','No mixed origin JSON deserialization or direct mixedorigin binding present.','102previousauthorizedGET receipts are source evidence; this future dataonlystage has network disabled.','1123qualified IDs do not establish append/view/worker/2x720/defaultBasicInfo completion or measurement correctness.','Six unknown source targets and partial factual reading remain in bound bundle; no overall MVP readiness or benefit closure.']}
out=P/'frozen-plan-independent-review.json';out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'path':str(out),'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'checks_passed':True,'source':3230,'code':114,'unique_paths':len(seen)}))
