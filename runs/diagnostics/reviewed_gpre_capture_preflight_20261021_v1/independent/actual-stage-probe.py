"""File-only GPRE actual-stage audit; no store, execution, labels or network."""
from pathlib import Path
from datetime import datetime
import hashlib,json,time
from stock_opportunity_agent.artifacts import canonical_json_hash as digest
from stock_opportunity_agent.data.raw_info import capture_document_id
from stock_opportunity_agent.data.resolution import BasicInfoBundle
from stock_opportunity_agent.research.evolution_core import project_basic_info_bundle
R=Path('/Users/l/Project/Recommandation')
P=R/'runs/diagnostics/reviewed_gpre_capture_snapshot_20261021_v1/stage'
O=R/'runs/diagnostics/reviewed_gpre_capture_preflight_20261021_v1/independent'
def read(p):
 p=Path(p)
 assert 'minimal_rounds_v182_integrated' not in str(p), 'Mixed origin JSON access forbidden'
 return json.loads(p.read_text())
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def binding(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
start=time.monotonic();plan=read(P/'plan.json');result=read(P/'result.json')
assert sha(P/'result.json')=='2c6e706bad8a63742f3f50b812d6e9aca6a4a27b7d557734ce2609c2e6580cfb'
assert sha(P/'plan.json')=='e82e93a5fae343890c04c95c4c8794b2860ce06c261484c3c922b31a26ff042c'
assert plan['plan_hash']==result['plan_hash']==digest({k:v for k,v in plan.items() if k!='plan_hash'})
assert result['status']=='completed' and not (P/'failure.json').exists()
assert result['GETs']==result['models']==0 and all(result[k] is False for k in ['labels','Signal_apply','fullprepare','MVP_closed'])
summary_path=P.parent/'driver-execute-v1/execution-summary.json';summary=read(summary_path)
prepared_path=P.parent/'driver-prepare-v1/prepare-summary.json';prepared=read(prepared_path)
assert summary['exit_code']==0 and summary['failure'] is None
assert len(summary['stage_files'])==1857 and len(prepared['stage_files'])==62
before=read(plan['global_before']['path']);assert len(before)==16493
assert len(plan['source_bindings'])==5869 and len(plan['code_bindings'])==116
bindings=plan['source_bindings']+plan['code_bindings']+before+prepared['stage_files']+summary['stage_files']
checks={}
for b in bindings:
 assert set(b)=={'path','sha256'}
 assert b['path'] not in checks or checks[b['path']]==b['sha256'],b['path']
 checks[b['path']]=b['sha256']
for path,h in checks.items():assert sha(path)==h,path
assert {b['path'] for b in summary['stage_files']}=={str(p.resolve()) for p in P.rglob('*') if p.is_file()}
assert binding(P/'result.json')==summary['result']
print('PASS frozen sources/code, original62, terminal1857 and all16493 prior global SHA',flush=True)
# Compare actual global membership and typed canonical contents, not flags alone.
receipts=result['append_receipts'];assert len(receipts)==4
assert [x['document_id'] for x in receipts]==plan['selected_ids']
assert all(x['inserted'] is True and x['same_capture_replay_inserted'] is False and x['canonical_load_equal'] is True for x in receipts)
added={x['original_record']['path']:x['original_record']['sha256'] for x in receipts}
assert {x['path']:x['sha256'] for x in result['global_additions']}==added
current={str(p.resolve()) for p in Path(plan['oracle_root']).rglob('*') if p.is_file()}
assert current=={b['path'] for b in before}|set(added)
products={read(b['path'])['document_id']:read(b['path']) for b in plan['products']}
assert len(products)==57
for x in receipts:
 b=x['original_record'];assert binding(b['path'])==b
 doc=read(b['path']);assert digest(doc)==digest(products[x['document_id']])
 assert capture_document_id(doc)==x['document_id']
 assert digest(read(P/'append-receipts'/(x['document_id']+'.json')))==digest(x)
print('PASS only4 global additions and complete canonical append receipts/readback',flush=True)
oldreview=read(plan['old_review']['path']);review=read(result['source_review']['path'])
assert binding(result['source_review']['path'])==result['source_review']
assert len(oldreview['records'])==1781 and len(review['records'])==1785
assert digest(review['records'][:1781])==digest(oldreview['records'])
assert review['manifest_hash']==digest({k:v for k,v in review.items() if k!='manifest_hash'})
assert [r['document_id'] for r in review['records'][1781:]]==plan['selected_ids']
assert all(r['verdict']=='admitted' and r['proof_profile']=='sec_companyfacts_capture_filed_next_utc_day_v1' for r in review['records'][1781:])
viewroot=Path(result['reviewed_source_snapshot']['root']);view=read(viewroot/'reviewed_snapshot.json')
assert sha(viewroot/'reviewed_snapshot.json')==result['reviewed_source_snapshot']['manifest_sha256']
oldview=read(Path(plan['old_view']['root'])/'reviewed_snapshot.json')
assert len(view['documents'])==1780 and len(oldview['documents'])==1776
assert [d['document_id'] for d in view['documents'][:1776]]==[d['document_id'] for d in oldview['documents']]
rows={r['document_id']:r for r in review['records'] if r['verdict']=='admitted'}
assert len(rows)==1780
assert set(rows)=={x['document_id'] for x in view['documents']}
docs={}
for b in view['documents']:
 path=viewroot/b['path'];assert sha(path)==b['sha256']
 doc=read(path);row=rows[b['document_id']];assert doc['document_id']==row['document_id']
 original=read(row['original_record']['path']);assert binding(row['original_record']['path'])==row['original_record']
 assert digest(doc)==digest(original)
 assert hashlib.sha256(doc['content'].encode()).hexdigest()==doc['content_hash']==row['content_hash']
 docs[doc['document_id']]=doc
assert set(plan['selected_ids'])<=set(docs)
manifest=read(P/'input_manifest.json')
assert manifest['groups']==plan['groups'] and manifest['case']==plan['case']
assert manifest['plan']==binding(P/'plan.json') and manifest['source_review']==result['source_review'] and manifest['reviewed_source_snapshot']==result['reviewed_source_snapshot']
print('PASS old1781 rows,1776 view prefix, full1780 original/view canonical equality',flush=True)
cutoff=datetime.fromisoformat(plan['case']['prediction_time']);latest='2025-03-31'
selections=read(P/'consumer-selection-evidence.json');group_report={}
def check_resolution(r):
 assert r['request']['request_id']
 selected=[]
 for ref in r['documents']:
  doc=docs[ref['document_id']]
  assert doc['company_id']==plan['case']['company_id'] and datetime.fromisoformat(doc['available_at'])<=cutoff
  assert ref['content_hash']==doc['content_hash'] and ref['available_at']==doc['available_at']
  facts=[]
  if doc['source_type']=='sec_company_facts':
   facts=[{k:f.get(k) for k in ('taxonomy','tag','start','end','unit')} for f in json.loads(doc['content']).get('facts',[])]
  selected.append({'document_id':doc['document_id'],'content_hash':doc['content_hash'],'facts':facts})
 for span in r['context_spans']:
  doc=docs[span['document_id']]
  assert span['content_hash']==doc['content_hash'] and span['available_at']==doc['available_at']
  assert doc['content'][span['start']:span['end']]==span['exact_text']
 return selected
for group in plan['groups']:
 name=group['name'];g=read(P/(name+'.json'));assert digest(g['registry'])==digest(group)
 assert [r['signal_ref'] for r in g['resolutions']]==group['refs'] and len(g['resolutions'])==18
 assert len(selections[name])==18
 report=[]
 for item,s in zip(g['resolutions'],selections[name],strict=True):
  r=item['resolution'];selected=check_resolution(r)
  assert r['request']['request_id']=='signal:'+item['signal_ref']
  assert s['signal_ref']==item['signal_ref'] and s['request_id']==r['request']['request_id']
  assert digest(s['selected_documents'])==digest(selected) and s['resolution_status']==r['status'] and digest(s['coverage'])==digest(r['coverage'])
  q1=[x['document_id'] for x in selected if any(f['end']==latest and f['tag'] and f['unit'] for f in x['facts'])]
  assert q1==s['latest_q1_source_ids']
  narrative=[x['document_id'] for x in selected if x['document_id']=='sec:cik_0001309402:000130940225000089']
  if s['financial_source_request']:
   assert s['status']==('latest_q1_selected' if q1 else 'gap_latest_q1_not_selected')
   report.append({'signal_ref':item['signal_ref'],'typed_q1_selected':bool(q1),'typed_q1_source_ids':q1,'latest_q1_narrative_selected':bool(narrative),
    'selected_typed_period_ends':sorted({f['end'] for x in selected for f in x['facts'] if f['end']}),
    'selected_typed_units':sorted({f['unit'] for x in selected for f in x['facts'] if f['unit']})})
 resolved=sum(x['resolution']['status']=='resolved' for x in g['resolutions'])
 assert resolved==17 and result['groups'][name]=={'resolved':resolved,'denominator':18}
 assert len(report)==9 and sum(r['typed_q1_selected'] for r in report)==2
 group_report[name]={'exact_registry_version':group['version'],'registry_hash':group['registry_hash'],'exact_refs':group['refs'],'input_resolved':17,'input_denominator':18,'typed_q1_financial_requests':2,'financial_request_denominator':9,'financial_selection_details':report,
  'unresolved':[x['signal_ref'] for x in g['resolutions'] if x['resolution']['status']!='resolved']}
print('PASS both exact18 input resolutions, document identity/PIT and actual facts/periods/units; typed Q1 2/9 each',flush=True)
bi=read(P/'basic-info.json');bi_report=[]
assert len(bi['bundle']['requests'])==len(bi['model']['requests'])==len(selections['basic_info'])==4
for r,m,s in zip(bi['bundle']['requests'],bi['model']['requests'],selections['basic_info'],strict=True):
 selected=check_resolution(r);assert digest(selected)==digest(s['selected_documents'])
 assert m['request']==r['request'] and m['status']==r['status']
 q1=[x['document_id'] for x in selected if any(f['end']==latest and f['tag'] and f['unit'] for f in x['facts'])]
 assert q1==s['latest_q1_source_ids']
 bi_report.append({'request_id':r['request']['request_id'],'status':r['status'],'selected_document_ids':[x['document_id'] for x in selected],
  'typed_q1_source_ids':q1,'projections':len(m['projections']),'projection_status':m['projection_status'],
  'source_context_truncated':m['source_context_truncated'],'projection_context_truncated':m['projection_context_truncated'],
  'omitted_markers':m['omitted_context_markers'],'available_projection_count':m['available_projection_count'],'omitted_projection_count':m['omitted_projection_count']})
# Pure projection reconstruction of persisted bundle; no resolver or Store.
model,lineage=project_basic_info_bundle(BasicInfoBundle.from_dict(bi['bundle']),max_chars=bi['model']['max_normalized_characters'])
assert digest(model)==digest(bi['model']) and digest(lineage)==digest(bi['lineage'])
assert sum(len(m['projections']) for m in model['requests'])==17
finmodel=next(m for m in model['requests'] if m['request']['request_id']=='orientation.v1.financial_facts')
assert len(finmodel['projections'])==1 and finmodel['projections'][0]['document_id']==plan['selected_ids'][-1]
text=finmodel['projections'][0]['exact_text']
assert '"end":"2025-03-31"' in text and '"tag":"AccountsPayableCurrent"' in text and '"unit":"USD"' in text
assert finmodel['source_context_truncated'] is True and finmodel['projection_status']=='partial_context_budget'
vis=read(P/'visible-financial-scope.json');financial=[d for d in docs.values() if d['company_id']==plan['case']['company_id'] and d['source_type']=='sec_company_facts' and datetime.fromisoformat(d['available_at'])<=cutoff]
assert len(financial)==57 and len({d['content_hash'] for d in financial})==57
assert len(vis['documents'])==vis['independent_content_units']==57 and vis['duplicate_ids']==[]
assert {r['document_id'] for r in vis['documents']}=={d['document_id'] for d in financial}
for r in vis['documents']:
 doc=docs[r['document_id']];assert r['content_hash']==doc['content_hash']
 assert digest(r['facts'])==digest([{k:f.get(k) for k in ('tag','unit','end','filed')} for f in json.loads(doc['content'])['facts']])
assert vis['q1_source_ids']==[plan['selected_ids'][-1]]
# Complete terminal file membership and current bytes still match after audit.
for b in summary['stage_files']:assert sha(b['path'])==b['sha256'],b['path']
print('PASS BasicInfo4 original spans and pure model/lineage reconstruction17; financial Q1 partial1999 chars; visible57 distinct content',flush=True)
out={'verdict':'PASS_bounded_actual_capture_source_stage_with_consumer_recency_limits','result':binding(P/'result.json'),'plan':binding(P/'plan.json'),'plan_hash':plan['plan_hash'],'execution_summary':binding(summary_path),
 'counts':{'original_prepared_files':62,'source_bindings':5869,'code_bindings':116,'old_global_files_byte_preserved':16493,'new_global_files_only':4,'terminal_stage_files':1857,'unique_SHA_paths_checked':len(checks),'canonical_products':57,'new_capture_versions_inserted':4,'retained_legacy_products':53,'old_review_rows_prefix':1781,'new_review_rows':1785,'old_view_documents':1776,'new_view_documents':1780},
 'all_current_original_and_view_records_canonical_equal':True,'capture_replay_receipts_all_false':True,'replay_evidence_limit':'Replay false and worker snapshot/reopen were executed by the sole native executor and are preserved in receipts/code/result. This auditor independently verifies their artifacts and all actual canonical files, but did not repeat append, construct a Store, or simulate an OS crash.',
 'groups':group_report,'basic_info':bi_report,'pure_projection_reconstruction_exact':True,'basic_info_projection_count':17,
 'basic_info_financial_model':{'latest_q1_capture_selected':True,'visible_characters':len(text),'Q1_AccountsPayableCurrent_USD_literal_visible':True,'partial_source_omissions_retained':True},
 'visible_financial':{'documents':57,'distinct_content_hashes':57,'provenance_duplicates':0,'q1_source_ids':vis['q1_source_ids']},
 'forbidden_activity':{'audit_store_constructions':0,'audit_append_prepare_execute_resume':0,'GETs_models_LabelStore_LockedTest':0,'mixed_origin_JSON_reads':0,'mixed_origin_stream_SHA_only_if_plan_bound':True},
 'limits':['Input resolution 17/18 is not executed financial measurement or correctness. Each group helper detects typed Q1 in 2/9 financial requests; some other requests select the latest Q1 narrative, so the seven typed gaps do not prove latest information entirely absent or a measurement failure.',
 'BasicInfo selects the Q1 typed document, but the financial model projection is partial and cannot establish full Q1 fact visibility. Operating and market projections also retain context-budget omissions; news remains unresolved, not negative evidence.',
 '57 distinct retained contents do not establish 57 independent corroborating facts; capture metadata/version counts are not research gain. Historical old source qualification limits (current extraction/filed-next-day and primary audit limitations) remain.',
 'No new native model behavior, full forty-case rerun, Signal apply, score, label truth, whole F4/F5/F7/MVP closure or independent investment benefit is established. Snapshot/reopen is not OS interruption recovery.'],
 'elapsed_seconds':round(time.monotonic()-start,6),'audit_script':binding(__file__)}
(O/'actual-stage-review.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'verdict':out['verdict'],'counts':out['counts'],'elapsed_seconds':out['elapsed_seconds'],'review':binding(O/'actual-stage-review.json')},ensure_ascii=False,indent=2))
