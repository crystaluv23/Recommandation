"""Independent persisted-output audit; no real Signal execution, preparation, model, acquisition or append."""
from datetime import datetime
from fractions import Fraction
import hashlib,json
from pathlib import Path
from unittest.mock import patch
from stock_opportunity_agent import signal_library as lib
from stock_opportunity_agent.data.raw_info import RawInfoDocument

OUT=Path(__file__).resolve().parent;BASE=OUT.parent;NATIVE=BASE/'native-approved'
bindings={}
def read(path):
 p=Path(path);raw=p.read_bytes();bindings[str(p.resolve())]=hashlib.sha256(raw).hexdigest();return json.loads(raw)
def canonical(obj):return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
def check_rows(rows):
 for row in rows:
  p=Path(row['path']);raw=p.read_bytes();assert hashlib.sha256(raw).hexdigest()==row['sha256'],p;bindings[str(p.resolve())]=row['sha256']
plan=read(NATIVE/'plan.json');assert plan['plan_hash']=='efad87e12671e882b92d830a069edbe3a9d142405e3af410c5f17441af00e2f5';assert canonical({k:v for k,v in plan.items() if k!='plan_hash'})==plan['plan_hash']
for name in ('source_bindings','code_bindings','old_completed_stage','independent_bindings'):check_rows(plan[name])
sourcefreeze=read(OUT/'source-only-freeze.json');assert bindings[str((OUT/'source-only-freeze.json').resolve())]=='4a00ff2c3007140f229140c615c2bd88b030281482a04ad95be3ea5924cc3f1f'
for row in sourcefreeze['files']:
 raw=Path(row['path']).read_bytes();assert len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256']
oracle=read(OUT/'source-only-oracle.json');addendum=read(OUT/'source-only-lineage-addendum.json');materials=read(OUT/'source-only-records.json');newdefs=read(OUT/'new-version-specs.json');assert plan['specs']==newdefs['specs']
assert addendum['fixed_new_denominator']==oracle['fixed_new_denominator']==plan['fixed_denominator']==2
batch=read(NATIVE/'native-batch.json');terminal=read(NATIVE/'result.json');start=read(NATIVE/'execution-start.json');contracts=read(NATIVE/'classification-contracts.json');projections=read(NATIVE/'consumer-projections.json')
assert terminal['plan_hash']==start['plan_hash']==plan['plan_hash'];assert terminal['status']=='completed_pending_independent_semantic_review' and terminal['native_batches']==1
assert batch['signal_calls']==2 and batch['usage']=={'llm_calls':0,'tokens':0,'cost':0.0}
assert not (NATIVE/'failure.json').exists();assert len(batch['results'])==len(batch['resolutions'])==len(projections)==2
assert [r['signal_id']+':v'+str(r['version']) for r in batch['results']]==plan['signal_refs']==['gross_margin_change:v4','revenue_acceleration:v3']
assert contracts.keys()=={'gross_margin_change:v4'}
manifest=read(Path(plan['reviewed_source_snapshot']['root'])/'reviewed_snapshot.json');assert len(manifest['documents'])==1780
all_entries={x['document_id']:x for x in manifest['documents']};docs={}
for d in materials['documents']:
 raw=read(d['path']);assert bindings[str(Path(d['path']).resolve())]==d['sha256'];assert raw['document_id']==d['document_id'];assert hashlib.sha256(raw['content'].encode()).hexdigest()==d['content_hash']==raw['content_hash'];docs[d['document_id']]=raw
assert len(docs)==61
allowed={}
for r in materials['records']:
 d=docs[r['document_id']];assert d['content'][r['raw_start']:r['raw_end']]==r['literal'];assert json.loads(r['literal'])==r['fact'];allowed.setdefault((r['fact']['tag'],r['fact'].get('start'),r['fact']['end'],r['fact']['value'],r['fact']['unit']),[]).append(r)
asof=datetime.fromisoformat(plan['case']['prediction_time']);specs={s['signal_id']+':v'+str(s['version']):lib.SignalSpec.from_dict(s) for s in plan['specs']};functions=lib.default_deterministic_signal_functions();rawdocs=tuple(RawInfoDocument.from_dict(d) for d in docs.values())
rows=[];restored=[]
with patch('socket.socket',side_effect=AssertionError('network forbidden')),patch('socket.create_connection',side_effect=AssertionError('network forbidden')):
 for result,resolution,projection in zip(batch['results'],batch['resolutions'],projections):
  ref=result['signal_id']+':v'+str(result['version']);spec=specs[ref];selected=resolution['documents'];ids=[d['document_id'] for d in selected]
  assert resolution['status']=='resolved' and resolution['coverage']['contract_satisfied'] is True
  assert resolution['request']['request_id']=='signal:'+ref and resolution['request']['description']==spec.description and resolution['request']['max_documents']==10
  assert resolution['request']['query']==' '.join(spec.retrieval_policy.query_terms)
  assert resolution['appended_documents']==[] and resolution['data_gap'] is None and len(ids)==10 and len(set(ids))==10
  assert len(resolution['events'])==1 and resolution['events'][0]['kind']=='local_query' and resolution['events'][0]['details']['matched_document_ids']==ids
  for docref in selected:
   d=docs[docref['document_id']];entry=all_entries[d['document_id']];assert entry['sha256']==hashlib.sha256(Path(next(x['path'] for x in materials['documents'] if x['document_id']==d['document_id'])).read_bytes()).hexdigest()
   assert docref['content_hash']==d['content_hash'];assert d['company_id']==plan['case']['company_id'];assert datetime.fromisoformat(d['available_at'])<=asof
  expected_fingerprint=sorted(did+':'+docs[did]['content_hash'] for did in ids);assert batch['document_fingerprints'][ref]==expected_fingerprint
  helper=functions[spec.function].__signal_input_facts__;basis=helper(spec,tuple(d for d in rawdocs if d.document_id in ids),asof);fullbasis=helper(spec,rawdocs,asof)
  assert lib._input_basis_identity(basis)==lib._input_basis_identity(fullbasis)
  evid=[]
  for evidence in result['evidence']['supporting']:
   d=docs[evidence['document_id']];assert evidence['document_id'] in ids and evidence['exact_span'] in d['content'];fact=json.loads(evidence['exact_span']);key=(fact['tag'],fact.get('start'),fact['end'],fact['value'],fact['unit'])
   candidates=allowed[key];match=[r for r in candidates if r['document_id']==evidence['document_id'] and r['literal']==evidence['exact_span']];assert len(match)==1
   assert evidence['timestamp']==min(datetime.fromisoformat(d['available_at']),asof).isoformat()
   evid.append(dict(document_id=evidence['document_id'],raw_start=match[0]['raw_start'],raw_end=match[0]['raw_end'],fact_index=match[0]['fact_index'],literal_sha256=hashlib.sha256(evidence['exact_span'].encode()).hexdigest(),fact=fact,source_only_permitted_versions=len(candidates)))
  reopened=lib.SignalResult.from_dict(json.loads(json.dumps(result)));assert reopened.to_dict()==result;restored.append(reopened)
  regenerated=lib.signal_result_model_view(reopened,classification_contract=contracts.get(ref));assert regenerated==projection
  assert projection['signal_id']==result['signal_id'] and projection['version']==result['version'] and projection['state']==result['state'] and projection['execution']==result['execution'] and projection['status']==result['status'] and projection['evidence']==result['evidence']
  if ref=='gross_margin_change:v4':
   expected=next(r for r in oracle['rows'] if r['signal_ref']==ref);assert result['state']=={'value':'neutral','confidence':1.0} and result['status']=={'coverage':'sufficient'} and result['execution']=={'status':'success'}
   assert len(evid)==4 and len(basis.facts)==4 and basis.unavailable_reason is None
   facts=[e['fact'] for e in evid];assert [(f['tag'],f['start'],f['end'],f['value'],f['unit']) for f in facts]==[('Revenues','2025-01-01','2025-03-31',601515000,'USD'),('GrossProfit','2025-01-01','2025-03-31',3039000,'USD'),('Revenues','2024-01-01','2024-03-31',597214000,'USD'),('GrossProfit','2024-01-01','2024-03-31',8367000,'USD')]
   independent_value=Fraction(3039000,601515000)-Fraction(8367000,597214000);assert str(independent_value)==expected['expected_numeric_exact'];assert result['measurement']['value']==float(independent_value)==expected['expected_numeric_float']
   assert result['measurement']['unit']=='fraction_difference' and result['measurement']['period']=={'start':'2025-01-01','end':'2025-03-31'}
   assert (asof.date()-datetime.fromisoformat('2025-03-31').date()).days==60
   contract=contracts[ref];assert canonical({k:v for k,v in contract.items() if k!='contract_hash'})==contract['contract_hash'];assert contract['result_hash']==canonical(result) and contract['spec_hash']==canonical(spec.to_dict()) and contract['signal_ref']==ref and contract['definition']==spec.description
   assert contract['execution']['function']==spec.function and contract['execution']['configured_parameters']=={'positive_min':.08,'negative_max':-.02,'period_policy':'same_window_yoy'} and 'period_policy' in contract['execution']['parameter_names']
   context=projection['interpretation']['measurement_context'];assert context['classification_contract']==contract and context['numeric_measurement']['value']==float(independent_value) and context['numeric_measurement']['numeric_sign']=='negative' and context['numeric_measurement']['categorical_state']=='neutral' and context['categorical_value_is_not_stock_direction'] is True
   assert context['numeric_measurement']['display']['value']==float(independent_value)*100 and context['numeric_measurement']['display']['unit']=='percentage_points'
   assert len(context['source_observations'])==4 and context['deferred_observation_count']==0
   for i,(observation,fact) in enumerate(zip(context['source_observations'],facts)):
    assert observation['evidence_index']==i and observation['evidence_group']=='supporting'
    for key in ('tag','start','end','value','unit'):assert observation[key]==fact[key]
   disposition='one_source_backed_numeric_measurement_matches_frozen_oracle'
  else:
   assert result['state']=={'value':'unavailable','confidence':0.0} and result['execution']=={'status':'domain_unavailable'} and result['status']=={'coverage':'unavailable'} and 'measurement' not in result and result['evidence']=={'supporting':[],'counter':[]}
   assert basis.unavailable_reason==result['interpretation']['summary'] and len(basis.facts)==2
   assert {(f.tag,f.start,f.end) for f in basis.facts}=={('Revenues','2025-01-01','2025-03-31'),('Revenues','2024-01-01','2024-03-31')}
   for start,end in [('2024-10-01','2024-12-31'),('2023-10-01','2023-12-31')]:assert not any(r['fact']['tag']=='Revenues' and r['fact'].get('start')==start and r['fact']['end']==end for r in materials['records'])
   assert ref not in contracts and 'measurement' not in projection and 'numeric_measurement' not in str(projection) and 'measurement_context' not in projection['interpretation']
   assert 'not evidence that the measured condition is absent' in projection['interpretation']['summary']
   disposition='correct_domain_abstention_for_two_missing_quarters_not_numeric_pass'
  rows.append(dict(ref=ref,disposition=disposition,result=result,selected_document_count=len(ids),fingerprint_verified=True,full_issuer_pool_equals_selected_basis=True,reconstructed_pure_basis=[dict(document_id=f.document.document_id,tag=f.tag,start=f.start,end=f.end,unit=f.unit,exact_span=f.exact_span) for f in basis.facts],basis_unavailable_reason=basis.unavailable_reason,source_literal_inventory=evid,persistence_and_saved_projection_equal=True))
for name in ('source_bindings','code_bindings','old_completed_stage','independent_bindings'):check_rows(plan[name])
assert not (BASE/'native/execution-start.json').exists() and read(BASE/'native/preflight-rejected.json')['real_batches']==0
report=dict(status='independent_actual_review_passed_with_one_numeric_measurement_and_one_domain_abstention',plan_hash=plan['plan_hash'],fixed_new_denominator=2,source_backed_numeric_measurements=1,source_missing_correct_domain_abstentions=1,numeric_passes_claimed=1,rows=rows,source_only_freeze_sha256=bindings[str((OUT/'source-only-freeze.json').resolve())],source_only_lineage_addendum_sha256=bindings[str((OUT/'source-only-lineage-addendum.json').resolve())],verified_originals=dict(source_bindings=1799,current_code_bindings=98,old_completed_stage_files=24,prepared_independent_top_level_files=41),actual_usage=batch['usage'],actual_result_count=batch['signal_calls'],call_count_limit='signal_calls counts native results; function-invocation count not instrumented',old_financial9='6 pass / 1 fail / 2 unknown remains completed and unchanged',preservation_scope='Saved JSON deserialize/reserialize and public model projection regeneration only; not OS crash recovery or fresh-model consumption',unavailable_consumer_scope='Unavailable projection intentionally has no success classification contract or numeric measurement; it states generic domain abstention. Exact missing-Q4 reason and version-owned policy remain in raw batch/plan and addendum, not fabricated into a success contract.',product_status='No stable Registry publication, business pointer advance, Slow reuse, full successor, new model execution or predictive benefit established.',reviewer_calls=dict(real_Signal_execute=0,real_prepare=0,pure_basis_reconstruction=4,projection_regeneration=2,models=0,network=0,labels=0,append=0))
(OUT/'actual-review.json').write_text(json.dumps(report,indent=2)+'\n');bindings[str((OUT/'actual-review.py').resolve())]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest();bindings[str((OUT/'actual-review.json').resolve())]=hashlib.sha256((OUT/'actual-review.json').read_bytes()).hexdigest()
(OUT/'actual-review-bindings.json').write_text(json.dumps(bindings,indent=2)+'\n')
print(json.dumps(dict(status=report['status'],numeric_measurements=1,correct_abstentions=1,bound_paths=len(bindings),actual_review_sha256=bindings[str((OUT/'actual-review.json').resolve())])))
