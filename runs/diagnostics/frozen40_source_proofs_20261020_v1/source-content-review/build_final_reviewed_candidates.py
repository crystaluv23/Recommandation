"""Build local reviewed candidates and verify native proofs; no store or acquisition."""
from pathlib import Path
from datetime import datetime
import hashlib,json
from stock_opportunity_agent.data.raw_info import RawInfoDocument
from stock_opportunity_agent.data.reviewed_snapshot import _read_bound,_sec_response_text,_verify_sec_response_document
P=Path(__file__).resolve().parent
# These source-scope judgments are manual review conclusions, never inferred from form.
MANUAL={
 'proof-011':('complete_annual_operating_report','Travel + Leisure Co. FY2023 actual Business/MD&A, two operating segments, annual financial statement notes and February21 signatures inspected. Amount/transaction units vary by table.'),
 'proof-024':('complete_interim_operating_report','Tandem Diabetes Care June30 2025 actual interim statements/MD&A, segment disclosure, extensive current risks and August6 signatures inspected. Three/six-month flows and balance-sheet instants stay distinct; inspected amounts in thousands.'),
 'proof-025':('complete_annual_operating_report','First Interstate BancSystem FY2024 actual community-bank Business, risks, MD&A interest/operating results, financial notes and February28 signatures inspected; inspected dollar tables are in millions with declared share/per-share exceptions.'),
 'proof-037':('complete_annual_operating_report','AXT FY2024 actual Business at12035 describes semiconductor substrates and subsidiaries, substantive risks80084/MD&A214442 and comparative revenue/gross-margin tables, with March14 signatures. Inspected dollar tables in thousands; not a universal report unit.')}
def bound(path):return {'path':str(path.resolve()),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
def save(path,value):
 path.parent.mkdir(parents=True,exist_ok=True)
 if path.exists():
  assert json.loads(path.read_bytes())==value
  return bound(path)
 with path.open('x') as f:json.dump(value,f,indent=2);f.write('\n')
 return bound(path)
projection_path=P.parents[1]/'reviewed_frozen_case_inputs_20261020_v1/stage/case-identities.json'
projection=json.loads(projection_path.read_bytes());by_case={r['case_id']:r for r in projection['cases']}
for name in ['proof-067','proof-072','proof-076','proof-080']:
 manual=json.loads((P/(name+'-content-review.json')).read_bytes())
 assert manual['qualified_content_scope_only'] is True
 MANUAL[name]=(manual['content_scope'],manual['reason'])
records=[];fragments=[];checks=[]
for name,(scope,reason) in MANUAL.items():
 receipt_path=P/(name+'-receipt-snapshot.json');receipt=json.loads(receipt_path.read_bytes());request=receipt['source_request'];entry=receipt['requests'][0]
 assocs=request['associations'];case_ids={a['case_id'] for a in assocs};assert len(case_ids)==1;case_id=next(iter(case_ids));case=by_case[case_id];filing=request['filing'];cik=filing['cik'].zfill(10)
 candidates=[]
 for binding in assocs[0]['root_bindings']:
  root=_read_bound(binding)[1];arrays=root['body']['filings']['recent'];indexes=[i for i,a in enumerate(arrays['accessionNumber']) if a==filing['accession_number']]
  if len(indexes)==1:candidates.append(binding)
 assert candidates;root_binding=candidates[0]
 rootproof={'kind':'sec_submissions_root','artifact':root_binding,'issuer_cik':cik,'accession_number':filing['accession_number'],'form':filing['form'],'primary_document':filing['primary_document'],'filing_date':filing['filing_date'],'accepted_at':filing['accepted_at']}
 bodyproof={'kind':'sec_static_archive_body_response','artifact':bound(receipt_path),'raw_response':{'path':entry['raw_response'],'sha256':entry['raw_sha256']},'entry_name':name,'endpoint':request['endpoint'],'document_role':'primary'}
 body=_sec_response_text(bodyproof,receipt,request['endpoint'],{})
 accepted=datetime.fromisoformat(filing['accepted_at']);doc=RawInfoDocument.create(document_id='sec:'+case['company_id']+':'+filing['accession_number'].replace('-',''),company_id=case['company_id'],source_type='filing',published_at=accepted,available_at=accepted,content=body,metadata={'provider':'sec_edgar','cik':cik,'form':filing['form'],'accession_number':filing['accession_number'],'source_url':request['endpoint']})
 bodyproof['expected_content_hash']=doc.content_hash;proofs=[rootproof,bodyproof]
 parsed={p['kind']:(p,_read_bound(p['artifact'])[1]) for p in proofs}
 _verify_sec_response_document(doc,{'reviewed_available_at':doc.available_at.isoformat()},parsed,datetime.fromisoformat(case['prediction_time']),{},{})
 docbinding=save(P/'candidate-documents'/(name+'.json'),doc.to_dict())
 records.append({'case_id':case_id,'accession':filing['accession_number'],'document_id':doc.document_id,'content_hash':doc.content_hash,'content_scope':scope,'qualified':True,'reason':reason,'review_read_scope':'selected_sections_partial_facts','body_binding':bodyproof['raw_response'],'source_receipt':bound(receipt_path),'body_locators':bound(P/(name+'-body-locators.json')),'native_profile_verified':True,'source_admitted':False})
 fragments.append({'document':docbinding,'target_keys':['operating|'+case_id+'|'+filing['accession_number']],'proof_profile':'sec_filing_response_acceptance_v1','proofs':proofs,'reason':reason,'semantic_target':{'case_id':case_id,'accession':filing['accession_number'],'document_id':doc.document_id}})
 checks.append({'receipt':name,'document_id':doc.document_id,'profile':'passed','canonical_record_sha256':docbinding['sha256'],'actual_cutoff':case['prediction_time']})
reviewbinding=save(P/'primary-final8-native-content-review.json',{'schema_version':'source-content-review-exact-candidates-v1','records':records,'projection_binding':bound(projection_path),'limits':['Manual selected-section source-scope review, not complete fact audit or model reading.','Candidate files only; no store/append/view/prepare/GET/model/labels.','Availability preserves exact retained root accepted_at; current fetch clock remains separate in receipt/cache.']})
for f in fragments:f['semantic_review']=reviewbinding
terminal_path=P.parent/'final-plan-v2/collection/results.json'
terminal=json.loads(terminal_path.read_bytes())
assert terminal['terminal'] is True and terminal['GET_attempts']==95
assert bound(terminal_path)['sha256']=='a873794947eb6907d14c74ea7db4127459ec4968b6cb8397eb67e25fc4b77b51'
unknowns=[json.loads((P/name).read_bytes()) for name in ['proof-059-content-unknown.json','proof-082-content-unknown.json','proof-093-content-review.json','proof-094-content-review.json']]
evidence={}
def add(binding):
 key=str(Path(binding['path']).resolve());assert bound(Path(key))==binding
 if key in evidence:assert evidence[key]==binding
 evidence[key]=binding
for path in P.glob('*.json'):
 if path.name!='source-final-candidate-fragments.json':add(bound(path))
for name in ['proof-011','proof-024','proof-025','proof-037','proof-059','proof-067','proof-072','proof-076','proof-080','proof-082','proof-093','proof-094']:
 snapshot=json.loads((P/(name+'-receipt-snapshot.json')).read_bytes());entry=snapshot['requests'][0]
 assert entry==next(row for row in terminal['requests'] if row['name']==name)
 add({'path':entry['raw_response'],'sha256':entry['raw_sha256']})
 disposition=next(row for row in terminal['dispositions'] if row['name']==name);assert disposition['status']=='received';add(disposition['native_cache'])
 native=_read_bound(disposition['native_cache'])[1]
 locator=json.loads((P/(name+'-body-locators.json')).read_bytes())
 assert hashlib.sha256(native['body'].encode()).hexdigest()==locator['decoded_body_sha256']
add(bound(terminal_path));add(bound(terminal_path.parent.parent/'request-plan.json'))
for fragment in fragments:
 for proof in fragment['proofs']:
  add(proof['artifact'])
  if 'raw_response' in proof:add(proof['raw_response'])
fb=save(P/'source-final-candidate-fragments.json',{'schema_version':'explicit-operating-candidate-fragments-v1','candidates':fragments,'native_verification':checks,'source_review':reviewbinding,'unknown_or_unqualified_source_bodies':unknowns,'evidence_bindings':list(evidence.values()),'collection_terminal_receipt':bound(terminal_path),'reviewed_body_count':12,'qualified_primary_candidates':8,'wrapper_unknown_primary_count':2,'content_scoped_but_missing_parent_receipt_exhibits':2,'source_admissions':0,'limits':['Retained publication/acceptance clock differs from within-text AIF Date; HITI literal conflicting2024 date remains unchanged, no automatic fact-asof2025 reassignment.','Unknown bodies/raw/nativecache/semantic review artifacts remain explicitly bound; they are not admitted via evidence presence.','Only eight primary candidates have complete current native source-proof verification; HITI two require an actual parent HTTP receipt.','Manual source-scope inspection is selected_sections_partial_facts, never model wholetext reading.','0GET/Store/prepare/append/view/model/labels by reviewer.']})
print(json.dumps({'review':reviewbinding,'fragments':fb,'native_verified':len(checks),'evidence_bindings':len(evidence),'unknown_bodies':len(unknowns)}))
