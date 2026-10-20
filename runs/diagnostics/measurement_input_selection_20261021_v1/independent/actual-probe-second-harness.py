"""File-only terminal input-consumption audit; parser matching only, no Signal run."""
from pathlib import Path
from datetime import datetime,timedelta
import json,hashlib,time
from stock_opportunity_agent.artifacts import canonical_json_hash as digest
from stock_opportunity_agent.data.raw_info import RawInfoDocument
from stock_opportunity_agent.data.resolution import source_types_compatible,RawInfoRequest,_matches_source_type
from stock_opportunity_agent.signal_library import _sec_facts,_CASH_TAGS,SignalSpec
R=Path('/Users/l/Project/Recommandation');P=R/'runs/diagnostics/measurement_input_selection_20261021_v1';O=P/'independent';OLD=R/'runs/diagnostics/reviewed_gpre_capture_snapshot_20261021_v1/stage'
Q1='rawcap:v1:64c9e4f193885e37ae497a75841bec6dec372f9fddf1ef7649710c28c40fc902'
EXPECTED='9c9b5eafa9c33ea8ad465b0eed8ea663294bae2902e4234d7488a44e3f7faa69'
def read(path):
 path=Path(path);assert 'minimal_rounds_v182_integrated' not in str(path),'Mixed origin JSON forbidden'
 return json.loads(path.read_text())
def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for x in iter(lambda:f.read(1024*1024),b''):h.update(x)
 return h.hexdigest()
def b(path):return {'path':str(Path(path).resolve()),'sha256':sha(path)}
start=time.monotonic();plan=read(P/'plan.json');result=read(P/'result.json');started=read(P/'started.json')
assert plan['plan_hash']==started['plan_hash']==result['plan_hash']==EXPECTED
assert digest({k:v for k,v in plan.items() if k!='plan_hash'})==EXPECTED
assert plan['output_root']==str(P) and len(plan['bindings'])==4265
assert result['status']=='completed' and result['forbidden_calls']==[] and result['bindings_unchanged'] is True and result['reviewed_view_records_unchanged'] is True
assert not (P/'failure.json').exists() and len(list(P.glob('started.json')))==len(list(P.glob('result.json')))==1
assert [g['name'] for g in plan['groups']]==['default_v6','latest_v12']
assert [g['version'] for g in plan['groups']]==[6,12]
assert [g['registry_hash'] for g in plan['groups']]==['ced3882945003998224b6b9a3c206e4bfc2f01eec6fc8857864350848a08be24','40a451c051b0bfbdf424121a5362405f2fae6672c2be7b0f51e8072e8bd4ae8d']
by_path={}
for binding in plan['bindings']:
 assert set(binding)=={'path','sha256'}
 assert binding['path'] not in by_path or by_path[binding['path']]==binding['sha256']
 by_path[binding['path']]=binding['sha256']
assert len(by_path)==4265
for path,h in by_path.items():assert sha(path)==h,path
print('PASS all4265 frozen bindings at audit start, exact plan and terminal markers',flush=True)
oldresult=read(OLD/'result.json');oldplan=read(OLD/'plan.json')
assert sha(OLD/'result.json')=='2c6e706bad8a63742f3f50b812d6e9aca6a4a27b7d557734ce2609c2e6580cfb'
assert oldplan['plan_hash']==oldresult['plan_hash']==digest({k:v for k,v in oldplan.items() if k!='plan_hash'})
assert plan['groups']==oldplan['groups'] and plan['case']==oldplan['case'] and plan['identity']==oldplan['identity']
assert plan['reviewed_source_snapshot']==oldresult['reviewed_source_snapshot']
review=read(oldresult['source_review']['path']);assert b(oldresult['source_review']['path'])==oldresult['source_review']
viewroot=Path(plan['reviewed_source_snapshot']['root']);view=read(viewroot/'reviewed_snapshot.json')
assert sha(viewroot/'reviewed_snapshot.json')==plan['reviewed_source_snapshot']['manifest_sha256']
assert len(view['documents'])==1780
viewmap={x['document_id']:x for x in view['documents']};reviewmap={x['document_id']:x for x in review['records'] if x['verdict']=='admitted'}
assert set(viewmap)==set(reviewmap)
cutoff=datetime.fromisoformat(plan['case']['prediction_time']);loaded={};selected_records={}
def source_document(ref):
 key=ref['document_id']
 if key not in loaded:
  vb=viewmap[key];vp=viewroot/vb['path'];assert sha(vp)==vb['sha256']
  raw=read(vp);row=reviewmap[key];original=row['original_record'];assert b(original['path'])==original
  assert digest(raw)==digest(read(original['path'])) and raw['document_id']==key and raw['content_hash']==row['content_hash']
  assert hashlib.sha256(raw['content'].encode()).hexdigest()==raw['content_hash']
  loaded[key]=RawInfoDocument.from_dict(raw);selected_records[key]={'view':b(vp),'original':original,'source_type':raw['source_type'],'available_at':raw['available_at']}
 doc=loaded[key]
 assert doc.company_id==plan['case']['company_id'] and doc.available_at<=cutoff
 assert ref['content_hash']==doc.content_hash and datetime.fromisoformat(ref['available_at'])==doc.available_at
 return doc
report={};cash={}
for group in plan['groups']:
 name=group['name'];new=read(P/(name+'.json'));old=read(OLD/(name+'.json'))
 assert old['registry']==group and [x['signal_ref'] for x in new['rows']]==group['refs']
 assert len(new['rows'])==18 and len(old['resolutions'])==18
 rows=[];financial=[];deterministic=[];changed=0;resolved=0;unchanged_generic=[]
 oldrows={x['signal_ref']:x['resolution'] for x in old['resolutions']}
 for row in new['rows']:
  ref=row['signal_ref'];res=row['resolution'];oldres=oldrows[ref]
  specbinding=next(x for x in group['definition_bindings'] if x['path'].endswith('/'+ref.split(':')[0]+'/versions/'+ref.split(':')[1]+'/spec.json'))
  spec=SignalSpec.from_dict(read(specbinding['path']));function=spec.function;assert function==row['function']
  policy=spec.retrieval_policy
  expected_request=RawInfoRequest(request_id='signal:'+ref,description=spec.description,source_types=spec.source_types,lookback_days=policy.lookback_days,max_documents=10,query=policy.query,required_source_groups=policy.required_source_groups,minimum_distinct_periods=policy.minimum_distinct_periods,minimum_period_span_days=policy.minimum_period_span_days,minimum_observations=policy.minimum_observations)
  assert digest(res['request'])==digest(expected_request.to_dict())
  assert res['request']['request_id']=='signal:'+ref and len(res['documents'])<=10
  docs=tuple(source_document(x) for x in res['documents'])
  assert all(_matches_source_type(d,expected_request.source_types) for d in docs)
  assert expected_request.lookback_days is None or all(d.published_at>=cutoff-timedelta(days=expected_request.lookback_days) for d in docs)
  ids=[d.document_id for d in docs];oldids=[x['document_id'] for x in oldres['documents']]
  assert len(ids)==len(set(ids))
  for span in res['context_spans']:
   doc=source_document(span);assert doc.content[span['start']:span['end']]==span['exact_text']
  assert row['selected_set_changed']==(set(ids)!=set(oldids));changed+=row['selected_set_changed'];resolved+=res['status']=='resolved'
  is_financial=source_types_compatible(('sec_company_facts',),spec.source_types);assert is_financial==row['financial_source_request']
  assert row['typed_q1_selected']==(Q1 in ids)
  is_calculator=bool(function and function.startswith('financial.'))
  facts=_sec_facts(docs,cutoff) if is_calculator else ()
  assert row['latest_native_fact_period']==max((f.end for f in facts),default=None)
  assert row['latest_cash_period']==max((f.end for f in facts if f.tag in _CASH_TAGS and f.start is None),default=None)
  if not is_calculator:
   assert ids==oldids;unchanged_generic.append(ref)
  if is_financial:financial.append(row)
  if is_calculator:
   assert spec.execution_type.value=='deterministic';deterministic.append(row)
  if function=='financial.cash_reserves':
   olddocs=tuple(source_document(x) for x in oldres['documents']);oldfacts=_sec_facts(olddocs,cutoff)
   current=max((f for f in facts if f.tag in _CASH_TAGS and f.start is None),key=lambda f:(f.end,f.filed,f.document.document_id))
   previous=max((f for f in oldfacts if f.tag in _CASH_TAGS and f.start is None),key=lambda f:(f.end,f.filed,f.document.document_id))
   assert (current.end,current.unit.upper())==('2025-03-31','USD') and (previous.end,previous.unit.upper())==('2023-12-31','USD')
   cash[name]={'current':{'document_id':current.document.document_id,'tag':current.tag,'unit':current.unit,'end':current.end,'filed':current.filed,'exact_span':current.exact_span},'previous':{'document_id':previous.document.document_id,'tag':previous.tag,'unit':previous.unit,'end':previous.end,'filed':previous.filed,'exact_span':previous.exact_span},'scope':'Original native parser plus cash candidate ordering only; no numeric Signal result execution.'}
  rows.append({'signal_ref':ref,'function':function,'status':res['status'],'selected_ids':ids,'selected_set_changed':row['selected_set_changed'],'typed_q1_document_member':Q1 in ids,'max_selected_fact_end':row['latest_native_fact_period']})
 summary={'resolved':resolved,'refs':18,'deterministic_financial':len(deterministic),'deterministic_typed_q1_selected':sum(x['typed_q1_selected'] for x in deterministic),'financial_source_requests':len(financial),'financial_source_typed_q1_selected':sum(x['typed_q1_selected'] for x in financial),'changed_sets':changed}
 assert summary==new['summary']==result['groups'][name]
 assert summary==({'resolved':17,'refs':18,'deterministic_financial':6,'deterministic_typed_q1_selected':6,'financial_source_requests':9,'financial_source_typed_q1_selected':8,'changed_sets':6} if name=='default_v6' else {'resolved':17,'refs':18,'deterministic_financial':9,'deterministic_typed_q1_selected':9,'financial_source_requests':9,'financial_source_typed_q1_selected':9,'changed_sets':7})
 report[name]={'summary':summary,'actual_refs':rows,'generic_exact_old_order_preserved_refs':unchanged_generic,'unresolved_refs':[x['signal_ref'] for x in rows if x['status']!='resolved'],'financial_Q1_gaps':[x['signal_ref'] for x in financial if not x['typed_q1_selected']]}
 print('PASS '+name+' actual IDs, canonical originals, exact versions, PIT/capacity/order; '+json.dumps(summary),flush=True)
for path,h in by_path.items():assert sha(path)==h,path
print('PASS all4265 frozen bindings again at audit end',flush=True)
out={'verdict':'PASS_actual_input_consumption_only_with_default_v6_LLM_gap_retained','plan':b(P/'plan.json'),'plan_hash':EXPECTED,'result':b(P/'result.json'),'started':b(P/'started.json'),'unique_start_pid':started['pid'],'frozen_bindings_checked_before_and_after':4265,'qualified_view_documents':1780,'distinct_selected_originals_checked':len(loaded),'groups':report,'cash_native_parser_before_after':cash,'selected_original_bindings':selected_records,'audit_seconds':round(time.monotonic()-start,6),'audit_script':b(__file__),'harness_disclosure':'The initial auditor read flat spec keys and raised KeyError after the first4265 SHA pass; original script/log preserved. Corrected audit uses native SignalSpec.from_dict for canonical nested schema and checks exact native RawInfoRequest policy. No product execution was repeated.',
 'scope':'Read-only files and pure native SEC parser/cash fact matching only. No Store, append, prepare_inputs, actual Signal arithmetic, probe reentry, network, model, LabelStore, LockedTest, or mixed-origin JSON.',
 'limits':['Typed Q1 document membership is actual input selection, not evidence that every callable measured Q1 or any research/forecast benefit. max_selected_fact_end may be a DEI date unrelated to the metric.','default_v6 cash_to_current_liabilities_ratio remains an LLM/generic-path Q1 gap; its original selected ID sequence is unchanged. v6 and v12 exact-version results are separate denominators.','One unresolved news ref remains in each18; no data is not a negative observation.','The historical115 related-test run with2fail12errors from issuer-fixture migration remains separate and is not claimed green by this input-only result.','This audit checks terminal artifact/current binding consistency and native guards in frozen code; no duplicate run, OS recovery, fresh model behavior, Signal apply or whole F5/MVP closure is established.']}
(O/'actual-results.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'verdict':out['verdict'],'audit_seconds':out['audit_seconds'],'result':b(O/'actual-results.json')},indent=2))
