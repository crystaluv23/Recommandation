"""Final bounded temp-only source-preparation counterreview; no real prepare."""
from pathlib import Path
from tempfile import TemporaryDirectory
from copy import deepcopy
from unittest.mock import patch
import hashlib,json
import diagnose_reviewed_frozen_source_snapshot as d
from test_reviewed_companyfacts_profile import CompanyFactsProfileFixture,write_bound
from test_reviewed_frozen_source_snapshot import cf_case
P=Path(__file__).resolve().parent;sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();checks=[]
expected={'scripts/diagnose_reviewed_frozen_source_snapshot.py':'b05af2849b3e54563e6041b8c11dff4d96ddce35875b4c19b7d40a2f6e126516','spec/scripts/diagnose_reviewed_frozen_source_snapshot.md':'1d7cea6c99ad68f8dd8442624561a5496ee6d395ac3ca1ac90e0934690b69c8a','tests/test_reviewed_frozen_source_snapshot.py':'247da143a875e2a59943db4dc833921e8b0ead5f1a98cbc180d49a255a0cfac5','src/stock_opportunity_agent/data/filing_orientation.py':'e539b5dd16333a939a81169783c2716e50e410497e7e4a180c5247289b8581db','src/stock_opportunity_agent/data/reviewed_snapshot.py':'3466550b2b8a7bb69aa6697860ac33425da3fc97de04ad224a9c28c48ad4e034'}
assert all(sha(p)==h for p,h in expected.items())
with TemporaryDirectory() as tmp:
 root=Path(tmp).resolve();f=CompanyFactsProfileFixture(root/'fixture');raw=root/'response.raw';raw.write_text(json.dumps(f.body));receipt={'status':'successful','terminal':True,'GET_attempts':1,'network_open_calls':1,'HTTP_responses_retained':1,'attempt_reservations':1,'automatic_retries':0,'redirects_followed':0,'native_cache':f.cache_binding,'raw_response_proof':f.raw_binding,'requests':[{'method':'GET','status':'http_response_retained','url':f.item['source_url'],'response_url':f.item['source_url'],'http_status':200,'raw_response':str(raw),'raw_sha256':sha(raw),'response_headers':{},'bytes':raw.stat().st_size}]}
 for mode in ('base_GET','POST','retained_bool','open_count_zero','reservation_bool','request_failed','GET_attempts_bool'):
  r=deepcopy(receipt)
  if mode=='POST':r['requests'][0]['method']='POST'
  if mode=='retained_bool':r['HTTP_responses_retained']=True
  if mode=='open_count_zero':r['network_open_calls']=0
  if mode=='reservation_bool':r['attempt_reservations']=False
  if mode=='request_failed':r['requests'][0]['status']='failed'
  if mode=='GET_attempts_bool':r['GET_attempts']=True
  row={'company_id':f.item['company_id'],'cache':f.cache_binding,'rawproof':f.raw_binding,'receipt':write_bound(root/(mode+'.json'),r)};table=root/'additional.json';write_bound(table,[row])
  try:
   with d._prepare_only():d._additional(table,{f.item['company_id']})
   accepted=True
  except d.ReviewedSourceRejected:accepted=False
  assert accepted==(mode=='base_GET');checks.append({'case':mode,'accepted':accepted,'expected_pass':mode=='base_GET'})
 oracle=root/'empty-namespace-root';oracle.mkdir();case=cf_case(f)
 with d._prepare_only():valid=d._financial(case,[],root/'all-products',oracle)
 norm=json.loads(Path(valid['normalization']['path']).read_bytes());assert len(valid['products'])==len(norm['expected_products'])==len(list((root/'all-products/products').glob('*.json')))==2 and valid['status']=='preappend_eligible' and all(x['profile_preverified'] for x in valid['products'])
 checks.append({'case':'actual native materializer+profile,all complete products persisted','product_count':2,'whole_expected_set_count':2,'status':valid['status']})
 native=d._verify_companyfacts_document;calls=[]
 def fail_second(*args):
  calls.append(args[0].document_id)
  if len(calls)==2:raise d.ReviewedSourceRejected('independent synthetic second-product rejection')
  return native(*args)
 with d._prepare_only(),patch.object(d,'_verify_companyfacts_document',fail_second):partial=d._financial(case,[],root/'partial',oracle)
 assert partial['status']=='unknown_native_profile_failed' and len(partial['products'])==2 and [p['profile_preverified'] for p in partial['products']]==[True,False]
 assert len(json.loads(Path(partial['normalization']['path']).read_bytes())['expected_products'])==2 and len(list((root/'partial/products').glob('*.json')))==2
 checks.append({'case':'injected mixed product profile failure keeps fulltwofiles/fullset,not family success','status':partial['status'],'product_count':2})
 # Canonical conflicts outside the nominal source namespace remain collisions.
 product=json.loads(Path(valid['products'][0]['product']['path']).read_bytes());product['metadata']['retrieved_at']='2027-01-01T00:00:00+00:00';write_bound(oracle/'any-old-alias'/case['company_id']/(product['document_id']+'.json'),product)
 from stock_opportunity_agent.data.raw_info import RawInfoDocument
 actual=RawInfoDocument.from_dict(json.loads(Path(valid['products'][0]['product']['path']).read_bytes()))
 with d._prepare_only():collision=d._collision(actual,oracle)
 assert collision['collision'] and len(collision['matches'])==1;checks.append({'case':'full-record crossnamespace clock conflict','collision':True})
 # Actual public wrapper forbids side effects even though parsing/helpers run.
 targets=[(d.RawInfoStore,'__init__'),(d.RawInfoStore,'append'),(d.SignalExecutor,'prepare_inputs')]
 with d._prepare_only():
  for o,n in targets:
   try:getattr(o,n)(None);raise AssertionError('guard failed '+n)
   except d.ReviewedSourceRejected:pass
 checks.append({'case':'actual prepare-only extra globalstore/append/prepare_inputs guards','passed':True})
assert all(sha(p)==h for p,h in expected.items())
old=P/'independent-receipt-counterexamples.json';bad=P/'independent-receipt-original-counterexamples.json'
report={'scope':'Independent static final candidate review and canonical temporary receipt/nativefinancial fixtures only. No actual prepare/source scan/globalstore/GET/models/LabelStore/LockedTest.','current_bindings':[{'path':str(Path(p).resolve()),'sha256':h} for p,h in expected.items()],'previous_valid_failure_evidence':{'path':str(old),'sha256':sha(old),'meaning':'old script27137 positiveGET accepted and five single-field contradictory receipts alsoaccepted'},'prior_harness_misuse':{'path':str(bad),'sha256':sha(bad),'meaning':'unresolved /var temp path made all cases including positive fail binding guard; excluded from product failure inference'},'checks':checks,'all_passed':True,'static_connections_reviewed':['Exactfixed40 projection remains bound;25distinct financial and24nonAnchor market+24operating cases match original company/split/cutoff/ticker, no source-based replacement.','NativeCompanyFacts full comparative selection/threeproof profile/full expected set, variants/ambiguities and crossnamespace canonical collisions preserved.','Operating supplemental bound existing fullrecord is preferred unchanged; multiplecanonicals or sourceproof mismatch remainunknown;prototype onlywhenno boundoriginal.','Knownmissing GET requests are source-bound endpoint/query only and preserve associations; no request execution or newCollector invoked.','Prepare-only wrapper inherits existing socket/model/LabelStore/fullprepare/Signalapply guards and adds RawInfoStore init/append/prepare_inputs rejection. No futureexecute/view/matrix implemented.'],'conclusion':'Fixed receipt-family false acceptance is closed under finalhash, with genuine positive preserved. No additional bounded blocker found for authorized prepare-only diagnosis; not source admission or execution authorization.','limits':['The complete real25source responses and realfixed40 preparation were not executed by this independentreview. Existingowner8tests evidence is separate from these independent fixtures.','Partial/gap/unknown outcomes remain valid diagnosis results and do not imply readiness or numeric measurement.']}
out=P/'independent-final-review.json';out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'all_passed':True,'checks':len(checks),'review_sha256':sha(out)}))
