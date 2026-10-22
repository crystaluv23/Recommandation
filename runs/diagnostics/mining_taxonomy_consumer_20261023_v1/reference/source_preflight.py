"""Source-only independent taxonomy preflight. No product helpers, labels, or network."""
from __future__ import annotations
import hashlib,json,re
from datetime import date,datetime,timezone
from decimal import Decimal
from pathlib import Path
ROOT=Path('/Users/l/Project/Recommandation')
OUT=ROOT/'runs/diagnostics/mining_taxonomy_consumer_20261023_v1/reference'
def sha(data):return hashlib.sha256(data).hexdigest()
def file_sha(p):return sha(p.read_bytes())
def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))
invpath=ROOT/'runs/diagnostics/mining_positive_frontier_20261021_v1/oracle/static-inventory.json'
inv=json.loads(invpath.read_text())
wirepath=Path(inv['sources']['first_native_manifest_wire']['path']);wire=wirepath.read_text()
# This is a JSON-quoted wire payload. Decode ONLY the two allowed subobjects;
# do not deserialize source_input, original-case ground_truth, or other wire fields.
allowed={};wire_layer=wire
for layer in range(4):
 for key in ('label_map','case_prediction_times'):
  matches=list(re.finditer('"'+key+'"\\s*:',wire_layer))
  if len(matches)==1:
   try:allowed[key]=json.JSONDecoder().raw_decode(wire_layer,matches[0].end())[0]
   except ValueError:pass
 if len(allowed)==2:break
 wire_layer=wire_layer.replace('\\"','"')
assert len(allowed)==2
assert set(allowed['label_map'])==set(allowed['case_prediction_times'])=={x['case_ref'] for x in inv['dev8']}
assert all(allowed['case_prediction_times'][x['case_ref']]==x['cutoff'] for x in inv['dev8'])
case=next(x for x in inv['dev8'] if x['case_ref']=='case-008')
positive_path=Path(case['first2_noquery_financial_documents'][0]['file']['path'])
positive=json.loads(positive_path.read_text());content=positive['content'];payload=json.loads(content)
assert file_sha(positive_path)==case['first2_noquery_financial_documents'][0]['file']['sha256']
assert sha(content.encode())==positive['content_hash']
m=re.search(r'"facts"\s*:\s*\[',content);pos=m.end();spans=[];dec=json.JSONDecoder()
while True:
 while content[pos].isspace():pos+=1
 if content[pos]==']':break
 start=pos;row,end=dec.raw_decode(content,pos);spans.append((row,start,end,content[start:end]));pos=end
 while content[pos].isspace():pos+=1
 if content[pos]==',':pos+=1
 elif content[pos]==']':break
selected=[(i,*entry) for i,entry in enumerate(spans) if entry[0].get('tag')=='NetCashProvidedByUsedInOperatingActivities']
assert [x[0] for x in selected]==[118,119]
records=[]
for i,row,start,end,span in selected:
 assert row['taxonomy']=='us-gaap' and row['unit']=='USD'
 records.append({'json_pointer':f'/facts/{i}','row':row,'exact_span':span,'raw_content_char_start':start,'raw_content_char_end_exclusive':end,'raw_content_utf8_byte_start':len(content[:start].encode()),'raw_content_utf8_byte_end_exclusive':len(content[:end].encode()),'exact_span_sha256':sha(span.encode()),'row_canonical_sha256':sha(canonical(row).encode())})
assert date.fromisoformat(records[0]['row']['end']) < date.fromisoformat(records[1]['row']['end'])
assert (date(2010,6,30)-date(2010,1,1)).days==(date(2011,6,30)-date(2011,1,1)).days==180
negative_path=ROOT/'runs/diagnostics/mining_fact_semantics_repair_20261021_v1/root/namespace-before.json'
negative=json.loads(negative_path.read_text())
# Deliberately do not consume prior expected count, prior relations, or pass flags.
negative_content=negative['content'];nested=json.loads(negative_content)
negative_rows=[]
for ns in ('namespace-a','namespace-b'):
 row=nested['facts'][ns]['Metric']['units']['USD'][0]
 needle=json.dumps(row,sort_keys=True)
 start=negative_content.index(needle)
 negative_rows.append({'taxonomy_from_parent':ns,'json_pointer':f'/facts/{ns}/Metric/units/USD/0','row':row,'exact_leaf_span':needle,'raw_content_char_start':start,'raw_content_char_end_exclusive':start+len(needle),'leaf_span_sha256':sha(needle.encode()),'qualification':'The leaf has no taxonomy; parent namespace is required for this new projection.'})
assert sha(negative_content.encode())==negative['facts'][0]['content_hash']
assert all('taxonomy' not in f and 'taxonomy' not in json.loads(f['exact_span']) for f in negative['facts'])
sources={str(p):{'sha256':file_sha(p)} for p in [invpath,wirepath,positive_path,negative_path,ROOT/'reports/approved-reading-and-taxonomy-20261022.md',ROOT/'tests/test_mining_taxonomy.py',ROOT/'src/stock_opportunity_agent/research/mining_controller.py',ROOT/'src/stock_opportunity_agent/research/mining_agent_tools.py',ROOT/'src/stock_opportunity_agent/research/mining_role_model.py',ROOT/'src/stock_opportunity_agent/research/evolution_core.py']}
ref={
 'schema_version':'mining-taxonomy-source-only-reference-v1','disposition':'feasible_narrow_two_source_consumer_probe_with_explicit_boundaries',
 'scope':'Independent original JSON reading and standard-library date/Decimal arithmetic; no production helper determines expected namespace or comparison. No candidate, prediction direction, research benefit, label acquisition or model answer.',
 'opaque_existing_metadata':{'wire_path':str(wirepath),'wire_sha256':file_sha(wirepath),'wire_pointer_expected_sha256':inv['sources']['first_native_manifest_wire']['sha256'],'extraction':'Only label_map and case_prediction_times decoded after one JSON-quote layer; no source_input or ground_truth deserialized.','label_map':allowed['label_map'],'case_prediction_times':allowed['case_prediction_times'],'case_binding_matches_static_dev8':True,'constructor_constraint':'For a one-case controller use only that case-ref label-map subset. Constructor still accesses case.ground_truth.is_surge to construct unused defaults; supplying SimpleNamespace.is_surge from this same opaque map is a transparent compatibility adapter, not a new label.'},
 'positive_source_control':{
  'case_ref':'case-008','opaque_group':allowed['label_map']['case-008'],'case_cutoff':allowed['case_prediction_times']['case-008'],'source_path':str(positive_path),'file_sha256':file_sha(positive_path),'document_id':positive['document_id'],'content_sha256':positive['content_hash'],'company_id_private_binding':positive['company_id'],'source_type':positive['source_type'],'published_at':positive['published_at'],'available_at':positive['available_at'],'content_schema':payload['schema_version'],'filing_date':payload['filing_date'],'form':payload['form'],'records':records,
  'source_only_judgment':'The complete original document has exactly these2 operating-cash-flow rows, same explicit taxonomy/concept/USD and two six-month calendar durations, with no competing OCF row or different OCF currency in this document. A document-local historical current/prior comparison is supported.',
  'allowed_measurement_scope':{'concept':'NetCashProvidedByUsedInOperatingActivities','taxonomy':'us-gaap','unit':'USD','prior_period':{'start':'2010-01-01','end':'2010-06-30'},'current_period':{'start':'2011-01-01','end':'2011-06-30'},'current_value':'9506313','prior_value':'4342261','latest_over_comparable_prior_decimal':str(Decimal(9506313)/Decimal(4342261)),'optional_compute_six_decimal':'2.189254','latest_minus_comparable_prior':'5164052','not_required':'No compute action, candidate, predictive direction, positive/control contrast, or mandatory numeric prose is needed merely to consume taxonomy correctly.'},
  'material_qualifications':[
   'The reported periods are calendar first-half durations. fiscal_period=Q2 does not make them individual second quarters; fiscal_year=2011 on both rows does not override start/end.',
   'The latest row is latest within the selected historical2011 source only. It is not the latest available issuer fact at the2025 cutoff; dev8 inventory lists56 financial documents and later source availability2025-05-07.',
   'Source metadata states retrospective_api_extraction=true, retrieved_at2026-10-19, next_utc_day_after_companyfacts_filed_date, and requires_primary_filing_audit=true. This is a reviewed saved-source provenance/control proof, not an independently verified primary-filing or real-time acquisition proof.',
   'Description explicitly includes discontinued operations. Do not narrow it to continuing operations without evidence.',
   'The actual source belongs to opaque control group case-008. A source-side positive control means comparable namespace provenance, not the positive outcome class or favorable economics.',
   'No full dev8 comparable-factor admission or natural unknown/mismatch frequency claim was made. Only this exact selected source control was independently qualified.'
  ],'metadata':positive['metadata']},
 'original_namespace_counterexample':{
  'source_path':str(negative_path),'file_sha256':file_sha(negative_path),'raw_source_content':negative_content,'raw_source_content_sha256':sha(negative_content.encode()),'records':negative_rows,'old_saved_fact_records':negative['facts'],'old_fact_refs':[f['fact_ref'] for f in negative['facts']],
  'new_projection_expected':'A fresh source projection can retain namespace-a for current Metric120 and namespace-b for prior Metric100. Same concept spelling and USD do not establish same namespace: no automatic unique current/comparable pair or same-concept period relation across them.',
  'old_legacy_expected':'The original persisted leaf facts have neither taxonomy field nor taxonomy in exact_span. Without the complete parent source they remain readable but namespace unknown; no automatic unique/current/comparable inference and no invented default us-gaap. Do not retroactively alter original refs or hashes.',
  'typed_legacy_exception':'An old typed exact_span that itself contains taxonomy may establish namespace; this is different from these legacy leaves.',
  'conflict_expected':'A retained taxonomy conflicting with taxonomy in a typed literal is unknown/conflicting provenance and cannot establish an automatic comparable basis.',
  'explicit_arithmetic_authority':'The existing generic explicit compute accepts2 finite same-case fact refs.120/100=1.200000 is legal explicit arithmetic even across these namespaces; it must not be relabeled an automatically proven same-concept comparable pair. Reject semantic promotion, not the arithmetic itself.',
  'sample_scope':'Previously saved synthetic counterexample; not a natural dev8 source discovery or new business label. Its available_at is fixture lineage only, not an independent real-issuer filing proof.',
  'fresh_coverage_limit':'A fresh fetch of the original parent source tests known namespace mismatch. It does not by itself test the old imported unknown-leaf variant; keep that as a separate preserved source/legacy control unless explicitly included.'},
 'hash_bindings':sources,
 'no_model_or_external_calls':True,'no_product_edits':True
}
(OUT/'source-reference.json').write_text(json.dumps(ref,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'source_reference_sha256':file_sha(OUT/'source-reference.json'),'same_namespace_positive':True,'mismatch_and_unknown_original_qualified':True,'existing_metadata_matches':True},indent=2))
