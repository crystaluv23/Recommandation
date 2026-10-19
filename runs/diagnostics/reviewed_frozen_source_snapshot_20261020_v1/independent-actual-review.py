"""Read completed prepare products/dispositions; no materializer/prepare/store calls."""
from pathlib import Path
from datetime import datetime,timedelta,timezone
from collections import Counter
import hashlib,json
from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.data.raw_info import RawInfoDocument
P=Path(__file__).resolve().parent;S=P/'stage';canon=canonical_json_hash
memo={}
def hashfile(p):
 p=Path(p).resolve();assert '/outcome-label-store' not in str(p) and p.name!='locked_test.json'
 if str(p).endswith('/minimal_rounds_v182_integrated/input_manifest.json'):assert str(p) in seen
 h=hashlib.sha256()
 with p.open('rb') as f:
  for c in iter(lambda:f.read(1024*1024),b''):h.update(c)
 return h.hexdigest()
def read(p):
 p=Path(p).resolve();assert '/outcome-label-store' not in str(p) and p.name!='locked_test.json' and not str(p).endswith('/minimal_rounds_v182_integrated/input_manifest.json')
 return json.loads(p.read_bytes())
def rb(b):
 key=(b['path'],b['sha256'])
 if key not in memo:assert hashfile(b['path'])==b['sha256'];memo[key]=read(b['path'])
 return memo[key]
def dt(x):return datetime.fromisoformat(x)
def paths_diff(a,b,p=''):
 if type(a)!=type(b):return[p]
 if isinstance(a,dict):return [x for k in a.keys()|b.keys() for x in (paths_diff(a[k],b[k],p+'.'+k) if k in a and k in b else [p+'.'+k])]
 return [] if a==b else[p]
assert (S/'result.json').is_file()
result,plan=read(S/'result.json'),read(S/'plan.json');assert canon({k:v for k,v in plan.items() if k!='plan_hash'})==plan['plan_hash']==result['plan_hash'];assert hashfile(S/'result.json')=='ac71fbcbf40526e04446c0cca25e568d02b0fd9df06ffd28463d03fcc90369ec'
allbindings=plan['source_bindings']+plan['code_bindings']+result['verified_bindings'];seen={}
for b in allbindings:
 assert b['path'] not in seen or seen[b['path']]==b['sha256'];seen[b['path']]=b['sha256']
for p,h in seen.items():assert hashfile(p)==h,p
projection=rb(plan['authorities']['projection']);assert plan['fixed_cases']==projection['cases'];cases={x['case_id']:x for x in projection['cases']};assert len(cases)==40
assert Counter(x['split'] for x in cases.values())=={'anchor':16,'evolution_validation':8,'discovery':16}
fins,markets,ops=(result['outcomes'][x] for x in ('financial','market','operating'));assert [len(fins),len(markets),len(ops)]==[25,24,24];assert {x['case_id'] for x in markets}=={x['case_id'] for x in ops}=={x['case_id'] for x in cases.values() if x['split']!='anchor'}
financial=[];collisions=[];products_total=0;normalizations=0
for row in fins:
 cid=row['case_id'];case=cases[cid];assert row['company_id']==case['company_id'];assert canon(read(S/'cases'/cid/'financial.json'))==canon(row)
 n=rb(row['normalization']);normalizations+=1;assert n['selection']['period_end_from']=='0001-01-01' and dt(n['selection']['available_at_through'])==dt(case['prediction_time']);assert n['selection']['period_end_through']==dt(case['prediction_time']).astimezone(timezone.utc).date().isoformat()
 cache,raw=rb(n['source_cache']),RawInfoDocument.from_dict(rb(n['raw_response']));body=json.dumps(cache['body'],sort_keys=True,separators=(',',':'),ensure_ascii=False);assert body==raw.content and dt(cache['retrieved_at'])<=raw.available_at<=dt(n['normalized_at']);assert cache['endpoint']==n['item']['source_url'] and cache['params']==[['method','GET']] and raw.company_id==case['company_id']
 expected={x['document_id']:x for x in n['expected_products']};assert len(expected)==len(n['expected_products'])==len(row['products']);assert set(expected)=={x['document_id'] for x in row['products']}
 assert len(list((S/'cases'/cid/'products').glob('*.json')))==len(expected)
 for p in row['products']:
  d=RawInfoDocument.from_dict(rb(p['product']));payload=json.loads(d.content);assert d.document_id==p['document_id'] and d.source_type=='sec_company_facts' and d.company_id==case['company_id'];assert expected[d.document_id]=={'document_id':d.document_id,'content_hash':d.content_hash,'canonical_record_hash':canon(d.to_dict())}
  assert d.available_at==datetime.combine(datetime.fromisoformat(payload['filing_date']).date()+timedelta(days=1),datetime.min.time(),timezone.utc)<=dt(case['prediction_time']);assert d.metadata['fact_count']==len(payload['facts']) and payload['cik']==case['company_id'][4:];assert p['profile_preverified'] is True
  assert d.metadata['retrospective_api_extraction'] is True and d.metadata['requires_primary_filing_audit'] is True
  for m in p['matches']:
   old=rb(m['original_record']);equal=canon(old)==canon(d.to_dict());assert m['canonical_equal']==equal
   if not equal:collisions.append({'case_id':cid,'document_id':d.document_id,'old_record':m['original_record'],'new_product':p['product'],'content_and_public_clocks_equal':all(old[k]==d.to_dict()[k] for k in ('content','content_hash','published_at','available_at')),'different_paths':paths_diff(old,d.to_dict())})
  assert p['collision']==any(not x['canonical_equal'] for x in p['matches']);products_total+=1
 financial.append({'case_id':cid,'products':len(row['products']),'status':row['status'],'pair_audits':len(row['pair_audit']),'all_products_retained':True})
assert products_total==result['derived_product_count']==result['expected_product_count']==result['profile_preverified_product_count']==842
assert len(collisions)==result['collisions']==4 and result['preappend_eligible_product_count']==products_total-4==838
market_originals=set();valid_originals=set();pairs=0;validpairs=0;valid_associations=set();noorigin=[]
for row in markets:
 cid=row['case_id'];cutoff=dt(cases[cid]['prediction_time']);assert canon(read(S/'cases'/cid/'market.json'))==canon(row);assert row['source_admitted'] is False
 for v in row['variants']:
  pairs+=1;market_originals.add(v['original_record']['path'])
  if not v.get('complete_canonical_reconstruction'):continue
  validpairs+=1;valid_originals.add(v['original_record']['path']);doc=RawInfoDocument.from_dict(rb(v['original_record']));cache=rb(v['cache']);bars=json.loads(doc.content);rawbars=cache['body']['results'];assert len(bars)==len(rawbars) and doc.company_id==cases[cid]['company_id'] and doc.available_at<=cutoff
  for b,r in zip(bars,rawbars,strict=True):
   assert b['as_of_date']==datetime.fromtimestamp(r['t']/1000,timezone.utc).date().isoformat() and b['symbol']==doc.metadata['symbol'] and dt(b['retrieved_at'])==dt(v['normalized_at'])
   assert all(float(b[k])==float(r[j]) for k,j in (('open','o'),('high','h'),('low','l'),('close','c'),('adjusted_close','c')))
   assert b['volume']==int(float(r['v']))  # Existing native PriceBar integer convention, not raw fractional equality.
  assert doc.metadata['prices']==[b['adjusted_close'] for b in bars] and bars[-1]['as_of_date']==v['latest_bar'] and dt(v['provider_retrieved_at'])<=dt(v['normalized_at'])
  valid_associations.add((cid,v['original_record']['path'],v['cache']['path']))
 if row['status']=='unknown_no_reconstructed_origin':
  for v in row['variants']:
   d=RawInfoDocument.from_dict(rb(v['original_record']));noorigin.append({'case_id':cid,'error':v.get('error'),'case_cutoff':cases[cid]['prediction_time'],'original_available_at':d.available_at.isoformat(),'original_end':d.metadata['end'],'past_cutoff':d.available_at>cutoff,'original':v['original_record']})
assert pairs==11244 and validpairs==959 and len(market_originals)==246 and len(valid_originals)==242
missing=read(S/'missing-proof-requests.json');assert len(missing)==result['missing_proof_request_count']==92;assert len({canon({'endpoint':m['endpoint'],'query':m['query']}) for m in missing})==92;purposes=Counter()
for m in missing:
 purposes.update({a['purpose'] for a in m['associations']})
 for a in m['associations']:
  if a['purpose'] in ('historical_issuer','all_type_splits'):
   assert (a['case_id'],a['original_record']['path'],a['cache']['path']) in valid_associations
   doc=RawInfoDocument.from_dict(rb(a['original_record']));cache=rb(a['cache']);bars=json.loads(doc.content);symbol=doc.metadata['symbol'];q=m['query']
   if a['purpose']=='historical_issuer':assert m['endpoint']=='https://api.massive.com/v3/reference/tickers/'+symbol and q=={'date':bars[-1]['as_of_date']}
   else:assert m['endpoint']=='https://api.massive.com/stocks/v1/splits' and q=={'ticker':symbol,'execution_date.gte':doc.available_at.astimezone(timezone.utc).date().isoformat(),'execution_date.lte':max(dt(cache['retrieved_at']),dt(bars[0]['retrieved_at'])).astimezone(timezone.utc).date().isoformat(),'sort':'execution_date.asc','limit':'1000'}
  else:
   assert a['purpose']=='exact_static_primary_body' and m['query']=={};op=next(x for x in ops if x['case_id']==a['case_id']);assert any(t['primary_url']==m['endpoint'] and t['accession']==a['accession_number'] and not t['body_cache_matches'] for t in op['targets'])
opsummary=[];opvariants=[]
for row in ops:
 assert row['source_admitted'] is False and row['status']=='pending_wholebody_semantic_review';assert canon(read(S/'cases'/row['case_id']/'operating.json'))==canon(row)
 for t in row['targets']:
  for v in t['body_variants']:
   assert v['status']=='mechanical_profile_preverified_semantic_scope_pending';opvariants.append(v)
 opsummary.append({'case_id':row['case_id'],'targets':len(row['targets']),'targets_missing_body':sum(not t['body_cache_matches'] for t in row['targets']),'source_admitted':False})
assert len(opvariants)==71 and Counter(v['candidate_origin'] for v in opvariants)=={'bound_existing_original':56,'native_primary_prototype_no_bound_original':15}
assert sum(v.get('collision',False) for v in opvariants)==15
for k in ('global_store_constructed','labels_loaded','view_materialized','matrices_executed','admission_or_readiness_claim'):assert result[k] is False
for k in ('GET_attempts','model_calls','source_appends','signal_apply_calls','prepare_inputs_calls'):assert result[k]==0
binding_envelope=read(P/'prepared-file-bindings.json');bindings=binding_envelope['files'];assert binding_envelope['file_count']==len(bindings)==969;assert {str(x.resolve()) for x in S.rglob('*') if x.is_file()}=={b['path'] for b in bindings}
for b in bindings:assert hashfile(b['path'])==b['sha256']
for p,h in seen.items():assert hashfile(p)==h
operating_review=read(P/'independent-operating-collision-review.json')
out={'scope':'Independent once-only completed prepare artifact audit. No prepare/_prepare/_operating,materializer,store,append,view/matrix,GET,models,labels or LockedTest.','plan_hash':plan['plan_hash'],'result_binding':{'path':str(S/'result.json'),'sha256':hashfile(S/'result.json')},'prepared_stage_file_bindings_verified':969,'source_code_output_unique_bindings_verified_before_after':len(seen),'fixed_denominators':{'original_cases':40,'financial':25,'market':24,'operating':24},'financial':{'actual_product_files':842,'expected_products':842,'reported_native_profile_pass':842,'no_collision_product_count':838,'collisions':collisions,'family_rows':financial,'independent_check':'All842complete records match expected canonical identities,cutoff/filednextday,selected cache/raw/native clocks; materializer and nativeprofile not rerun.'},'market':{'pairs':pairs,'successful_pairs':validpairs,'unique_original_files':len(market_originals),'unique_reconstructed_original_files':len(valid_originals),'independent_bar_value_and_period_check':True,'volume_contract':'Existing native int(float(provider v)) checked explicitly, not lossless fractional volume. Original reader failure retained in independent-market-raw-equality-first-failure.json','no_origin':noorigin,'limits':'23families stilllack issuer/splits. FTI originalwindow/availability is later than originalMay30cutoff; no claimFTIhasnoprices. No trimming or requery occurred.'},'operating':{'families':24,'targets':sum(x['targets'] for x in opsummary),'mechanical_variants':71,'existing_original_variants':56,'prototype_variants':15,'prototype_collision_variants':15,'source_admitted':False,'wholebody_review_pending':True,'families_detail':opsummary,'collision_supplement':{'path':str(P/'independent-operating-collision-review.json'),'sha256':hashfile(P/'independent-operating-collision-review.json'),'distinct_originals':4,'as_is_native':operating_review['as_is_native_status_counts']},'meaning':'12variants of3existing IDs mechanically pass as-is,omitted bysupplement lookup. FTIinterim3variants/1ID source_type10-k conflictswith proved10-Q andcorrectlyrejects. Prototypes/oldrecords differonlysource_type; no automatictype rewrite oradmission.'},'missing_requests':{'unique_count':92,'purpose_counts':dict(purposes),'all_associations_checked':True,'limits':'Known proof deficits only, not all futureacquisition work; FTI hasno PITmatchingorigin and needsa separately specified eligiblewindow,notjustissuer/splitproofs.'},'no_admission_view_matrix_or_execution':True,'limits':['842nativeprofilepass is actualproducer evidence+storedfullset; thisindependentreader didnotrerunmaterializer.','Current sourceauthority extraction/filednextday isnotAPIvintageorprimaryfilingvalueaudit.','No wholebodyoperatingsufficiency,cohortreadiness,Signalmeasurement,modelbehavior,MVP orbenefitclosed.','Stage remains terminal andunchanged; no rejected source/collision was patched or silently removed.']}
path=P/'independent-actual-review.json';path.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({'review_sha256':hashfile(path),'source_bindings':len(seen),'products':products_total,'missing_by_purpose':dict(purposes),'stage_files':969}))
