"""Local actual exhibit candidates and native verification; no store/acquisition."""
from pathlib import Path
from datetime import datetime
from urllib.parse import urlsplit
import hashlib,json
from stock_opportunity_agent.data.raw_info import RawInfoDocument
from stock_opportunity_agent.data.reviewed_snapshot import _read_bound,_sec_response_text,_verify_sec_response_document,ReviewedSourceRejected
P=Path(__file__).resolve().parent

def bound(path):return {'path':str(path.resolve()),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
def save(path,value):
 path.parent.mkdir(parents=True,exist_ok=True)
 if path.exists():assert json.loads(path.read_bytes())==value
 else:
  with path.open('x') as f:json.dump(value,f,indent=2);f.write('\n')
 return bound(path)
projection_path=P.parents[1]/'reviewed_frozen_case_inputs_20261020_v1/stage/case-identities.json';projection=json.loads(projection_path.read_bytes());by_company={r['company_id']:r for r in projection['cases']}
old_review_path=P.parent/'operating-content-review.json';old_review=json.loads(old_review_path.read_bytes());hiti=next(r for r in old_review['targets'] if r['ticker']=='HITI')
manual=json.loads((P/'supplemental-exhibit-content-review.json').read_bytes());mm={r['receipt_name']:r for r in manual['records_pending_native_binding']}
for name in ['proof-093','proof-094']:mm[name]=json.loads((P/(name+'-content-review.json')).read_bytes())
settings=[('proof-093','supplement-003','cik_0001847409','99.3'),('proof-094','supplement-003','cik_0001847409','99.2'),('supplement-004','proof-059','cik_0000878518','99.1'),('supplement-005','proof-059','cik_0000878518','99.3'),('supplement-006','proof-082','cik_0001097362','99.3'),('supplement-007','proof-082','cik_0001097362','99.1')]
records=[];drafts=[];checks=[]
for name,parent_name,company,code in settings:
 semantic=mm[name];rp=P/(name+'-receipt-snapshot.json');receipt=json.loads(rp.read_bytes());parentp=P/(parent_name+'-receipt-snapshot.json');parent_receipt=json.loads(parentp.read_bytes());entry=receipt['requests'][0];pe=parent_receipt['requests'][0]
 if company==hiti['case_id'].split(':')[0]:
  accession=hiti['accession'];roots=[v['root'] for v in hiti['stage_body_variants']]
 else:
  pr=parent_receipt['source_request'];accession=pr['filing']['accession_number'];roots=pr['associations'][0]['root_bindings']
 root_binding=None
 for binding in roots:
  root=_read_bound(binding)[1];arrays=root['body']['filings']['recent'];indexes=[i for i,a in enumerate(arrays['accessionNumber']) if a==accession]
  if len(indexes)==1:root_binding=binding;index=indexes[0];break
 assert root_binding is not None
 accepted=datetime.fromisoformat(arrays['acceptanceDateTime'][index].replace('Z','+00:00'));primary=arrays['primaryDocument'][index];form=arrays['form'][index];cik=company.removeprefix('cik_');case=by_company[company]
 rootproof={'kind':'sec_submissions_root','artifact':root_binding,'issuer_cik':cik,'accession_number':accession,'form':form,'primary_document':primary,'filing_date':arrays['filingDate'][index],'accepted_at':accepted.isoformat()}
 parentproof={'kind':'sec_parent_primary_response','artifact':bound(parentp),'raw_response':{'path':pe['raw_response'],'sha256':pe['raw_sha256']},'entry_name':parent_name,'endpoint':pe['url'],'document_role':'primary'}
 parent_body=_sec_response_text(parentproof,parent_receipt,pe['url'],{});parentproof['expected_content_hash']=hashlib.sha256(parent_body.encode()).hexdigest()
 filename=Path(urlsplit(entry['url']).path).name
 bodyproof={'kind':'sec_static_archive_body_response','artifact':bound(rp),'raw_response':{'path':entry['raw_response'],'sha256':entry['raw_sha256']},'entry_name':name,'endpoint':entry['url'],'document_role':'incorporated_exhibit','exhibit_document':filename,'exhibit_type':code}
 body=_sec_response_text(bodyproof,receipt,entry['url'],{});doc=RawInfoDocument.create(document_id='sec-exhibit:'+company+':'+accession.replace('-','')+':'+filename,company_id=company,source_type='filing',published_at=accepted,available_at=accepted,content=body,metadata={'source_url':entry['url'],'accession_number':accession,'form':form,'provider':'sec_edgar','cik':cik,'parent_form':form,'parent_primary_document':primary,'exhibit_document':filename,'document_role':'incorporated_exhibit','exhibit_type':code})
 bodyproof['expected_content_hash']=doc.content_hash;proofs=[rootproof,parentproof,bodyproof];parsed={p['kind']:(p,_read_bound(p['artifact'])[1]) for p in proofs}
 try:_verify_sec_response_document(doc,{'reviewed_available_at':doc.available_at.isoformat()},parsed,datetime.fromisoformat(case['prediction_time']),{},{},exhibit=True);status='passed';error=None
 except ReviewedSourceRejected as exc:status='rejected';error=str(exc)
 db=save(P/'candidate-documents'/(name+'-exhibit.json'),doc.to_dict())
 records.append({'case_id':case['case_id'],'accession':accession,'document_id':doc.document_id,'content_hash':doc.content_hash,'content_scope':semantic['content_scope'],'qualified':True,'reason':semantic['reason'],'review_read_scope':'selected_sections_partial_facts','body_binding':bodyproof['raw_response'],'limitations':['Semantic scope only; native qualification is separately recorded.','Publication/acceptance clock is exact retainedroot time and does not silently rewrite any withintext dates.']})
 drafts.append({'document':db,'target_keys':['operating|'+case['case_id']+'|'+accession],'proof_profile':'sec_filing_exhibit_response_v1','proofs':proofs,'reason':semantic['reason'],'semantic_target':{'case_id':case['case_id'],'accession':accession,'document_id':doc.document_id}})
 checks.append({'receipt_name':name,'document_id':doc.document_id,'native_verifier':status,'error':error,'actual_cutoff':case['prediction_time']})
review_binding=save(P/'exhibit-six-native-semantic-review.json',{'schema_version':'source-content-review-exact-exhibits-v1','records':records,'manual_review_bindings':[bound(P/'supplemental-exhibit-content-review.json'),bound(P/'proof-093-content-review.json'),bound(P/'proof-094-content-review.json')],'limits':['HITI AIF literalJan29,2024/fiscalOct2024/parentacceptedJan2025 remain different facts; no text/date repair.','No model fulltext reading or source admission.']})
for d in drafts:d['semantic_review']=review_binding
status={'reader':bound(Path(__import__('stock_opportunity_agent.data.reviewed_snapshot',fromlist=['x']).__file__)),'native_checks':checks,'candidate_drafts':drafts,'semantic_review':review_binding,'all_source_admissions':0,'scope':'Local candidates only. Failed native proofs stay unknown; no store/append/prepare/GET.'}
out=P/'exhibit-six-native-initial-probe.json';save(out,status);print(json.dumps({'probe':bound(out),'passed':sum(c['native_verifier']=='passed' for c in checks),'rejected':[c for c in checks if c['native_verifier']=='rejected']}))
