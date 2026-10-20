"""Read-only actual GPRE plan freeze audit; no store or stage-function invocation."""
from pathlib import Path
from datetime import datetime
import hashlib,json,time
from stock_opportunity_agent.artifacts import canonical_json_hash as digest
from stock_opportunity_agent.data.raw_info import capture_document_id
from run_reviewed_posthoc_stage import _historical_code_check
R=Path('/Users/l/Project/Recommandation');P=R/'runs/diagnostics/reviewed_gpre_capture_snapshot_20261021_v1/stage';O=R/'runs/diagnostics/reviewed_gpre_capture_preflight_20261021_v1/independent';B=R/'runs/diagnostics/reviewed_frozen_source_completion_20261020_v1/stage'
def read(p):return json.loads(Path(p).read_text())
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
 return h.hexdigest()
def bind(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
start=time.monotonic();plan=read(P/'plan.json');summary_path=P.parent/'driver-prepare-v1/prepare-summary.json';summary=read(summary_path)
assert sha(P/'plan.json')=='e82e93a5fae343890c04c95c4c8794b2860ce06c261484c3c922b31a26ff042c'
assert plan['plan_hash']=='b5b6002f65216e0ea36c6d8e6e23258a060ac360cc722b7e956ab344758bef3e'==digest({k:v for k,v in plan.items() if k!='plan_hash'})
assert summary['exit_code']==0 and summary['execute_started'] is False and sha(summary_path)=='9d3013554bb41ed173493971cd0714505539646c183ad16a665e36f33206818f'
assert len(plan['source_bindings'])==5869 and len(plan['code_bindings'])==116
assert len(summary['stage_files'])==62 and len(plan['products'])==57
inventory=read(plan['global_before']['path']);assert len(inventory)==16493
bindings=plan['source_bindings']+plan['code_bindings']+inventory+summary['stage_files']
by_path={}
for b in bindings:
 assert set(b)=={'path','sha256'}
 assert b['path'] not in by_path or by_path[b['path']]==b['sha256']
 by_path[b['path']]=b['sha256']
for path,h in by_path.items():assert sha(path)==h,path
assert {b['path'] for b in summary['stage_files']}=={str(p.resolve()) for p in P.rglob('*') if p.is_file()}
assert {b['path'] for b in inventory}=={str(p.resolve()) for p in Path(plan['oracle_root']).rglob('*') if p.is_file()}
assert len(list((P/'products').glob('*.json')))==57
assert plan['output']==str(P) and [plan[k] for k in ('products_count','new_capture_count','retained_count','base_documents','base_review_rows')]==[57,4,53,1776,1781]
for flag in ('network_allowed','models_allowed','labels_allowed','apply_allowed','full_prepare_allowed'):assert plan[flag] is False
assert not any((P/name).exists() for name in ('execution-start.json','append-receipts','result.json','snapshot','failure.json'))
source=read(B/'result.json');inputs=read(B/'input_manifest.json');oldplan=read(B/'plan.json');oldreview=read(plan['old_review']['path'])
assert source['status']=='completed' and source['plan_hash']==oldplan['plan_hash'] and oldplan['plan_hash']==digest({k:v for k,v in oldplan.items() if k!='plan_hash'})
assert source['source_review']==inputs['source_review']==plan['old_review'] and source['reviewed_source_snapshot']==inputs['reviewed_source_snapshot']==plan['old_view']
assert plan['groups']==oldplan['groups']==inputs['groups']
assert [(g['name'],g['version'],len(g['refs'])) for g in plan['groups']]==[('default_v6',6,18),('latest_v12',12,18)]
_historical_code_check(oldplan['code_bindings'],'c9ad66e80f9b4f72438f5be93496dbaaa9410e92')
assert len(oldreview['records'])==1781 and sum(r['verdict']=='admitted' for r in oldreview['records'])==1776
v=read(Path(plan['old_view']['root'])/'reviewed_snapshot.json');assert len(v['documents'])==1776 and sha(Path(plan['old_view']['root'])/'reviewed_snapshot.json')==plan['old_view']['manifest_sha256']
norm=read(plan['normalization']['path']);mapping=read(plan['mapping']['path']);assert len(mapping)==57 and sum(r['selected'] is True for r in mapping)==4
assert [r['capture_id'] for r in mapping if r['selected']] == plan['selected_ids']
assert norm['schema_version']=='sec-companyfacts-normalization-v2' and norm['normalizer_profile']=='sec_companyfacts_capture_filed_next_utc_day_v1' and norm['identity_policy']=='raw-info-capture-v1'
oldbase=R/'runs/diagnostics/reviewed_frozen_source_snapshot_20261020_v1/stage/cases/cik_0001309402:20250530';oldnorm=read(oldbase/'normalization.json')
assert {k:v for k,v in norm.items() if k not in ('schema_version','normalizer_profile','identity_policy','expected_products')}=={k:v for k,v in oldnorm.items() if k not in ('schema_version','normalizer_profile','expected_products')}
assert len(norm['expected_products'])==57
oldrows={r['document_id']:r for r in oldreview['records']};selected_legacy=[];identities=[]
for b,m in zip(plan['products'],mapping,strict=True):
 doc=read(b['path']);old=read(oldbase/'products'/(m['legacy_id']+'.json'))
 assert capture_document_id(doc)==doc['document_id']==m['capture_id'] and m['content_hash']==doc['content_hash']
 assert {k:v for k,v in doc.items() if k!='document_id'}=={k:v for k,v in old.items() if k!='document_id'}
 assert doc['published_at']==old['published_at'] and doc['available_at']==old['available_at']
 assert datetime.fromisoformat(doc['available_at'])<=datetime.fromisoformat(plan['case']['prediction_time'])
 identities.append({'document_id':doc['document_id'],'content_hash':doc['content_hash'],'canonical_record_hash':digest(doc)})
 if m['selected']:
  assert m['legacy_id'] not in oldrows;selected_legacy.append(m['legacy_id'])
  same_ids=[q for q in inventory if Path(q['path']).name==m['capture_id']+'.json'];assert same_ids==[]
  legacy_orig=[q for q in inventory if Path(q['path']).name==m['legacy_id']+'.json'];assert len(legacy_orig)==1
  original=read(legacy_orig[0]['path']);assert original['content']==old['content'] and original['published_at']==old['published_at'] and original['available_at']==old['available_at'] and digest(original)!=digest(old)
 else:
  row=oldrows[m['legacy_id']];assert row['verdict']=='admitted' and digest(read(row['original_record']['path']))==digest(old)
assert norm['expected_products']==identities
assert len(selected_legacy)==4
# Exact old raw proof/cache remain bound; no body rewrite or new retrieval clock.
for key in ('raw_response','source_cache'):assert norm[key]==oldnorm[key] and bind(norm[key]['path'])==norm[key]
assert plan['case']['case_id']=='cik_0001309402:20250530' and plan['case']['prediction_time']=='2025-05-30T00:00:00+00:00' and plan['identity']=={'cik':'0001309402','ticker':'GPRE'}
required=[R/'scripts/diagnose_reviewed_frozen_source_snapshot.py',R/'spec/scripts/diagnose_reviewed_frozen_source_snapshot.md',R/'spec/scripts/run_reviewed_posthoc_stage.md']
assert all(bind(p) in plan['code_bindings'] for p in required)
out={'verdict':'PASS_actual_frozen_plan_only','plan':bind(P/'plan.json'),'plan_hash':plan['plan_hash'],'prepare_summary':bind(summary_path),
 'stage_files_verified':62,'source_bindings':5869,'code_bindings':116,'global_before_files_membership_and_SHA_verified':16493,'unique_all_binding_paths_verified':len(by_path),
 'historical_source_code_checked_against_git':'c9ad66e80f9b4f72438f5be93496dbaaa9410e92','full_products':57,'selected_new_capture_ids':plan['selected_ids'],'selected_legacy_ids':selected_legacy,'retained_exact_legacy_admitted':53,
 'new_capture_all_records_except_ID_equal_frozen_legacy':True,'public_times_and_normalization_clock_unchanged':True,'expected_product_full_set_matches_all57':True,'old_raw_proof_reused_exact':norm['raw_response'],
 'old_view_documents':1776,'old_review_rows':1781,'group_versions_and_denominators':[(g['name'],g['version'],len(g['refs']),g['registry_hash']) for g in plan['groups']],
 'no_execution_marker_or_append_or_newview':True,'qualify_evidence_scope':'Actual frozen code calls the complete native profile on all57 before plan creation; frozen v2 expected set/cache/raw/item/selection/provenance/clock all match this prior independently verified actual57 temporary profile. No Store or stage helper/materializer was rerun in this audit.',
 'elapsed_seconds':round(time.monotonic()-start,6),'limits':['This is a prepare-only freeze, not actual4 insertion/1780view or consumer-Q1 selection success.','No Store/append/prepare/execute/GET/models/LabelStore/LockedTest or old-stage resume.','The first metadata-only inspection mistakenly requested registry_version instead of actual version and raised KeyError; no audit success was inferred and no frozen file was written.']}
(O/'frozen-plan-independent-review.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps(out,ensure_ascii=False,indent=2))
