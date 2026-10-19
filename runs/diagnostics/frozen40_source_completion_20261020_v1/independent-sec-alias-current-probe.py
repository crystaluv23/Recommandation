"""Independent current alias source checks; real originals readonly, temp views only."""
from pathlib import Path
from datetime import datetime,timedelta
import hashlib,json,tempfile
from stock_opportunity_agent.data.raw_info import RawInfoDocument
from stock_opportunity_agent.data.filing_orientation import filing_source_matches_form
from stock_opportunity_agent.data.reviewed_snapshot import _verify_sec_document,ReviewedSourceRejected,materialize_reviewed_snapshot,open_raw_info_store
from stock_opportunity_agent.data.resolution import EvidenceResolver,RawInfoRequest
from stock_opportunity_agent.artifacts import canonical_json_hash
from tests.test_reviewed_sec_source_aliases import ReviewedSecSourceAliasTests
P=Path(__file__).resolve().parent;sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();checks=[];sources=[]
def readbound(b):
 assert sha(b['path'])==b['sha256'];sources.append(b);return json.loads(Path(b['path']).read_bytes())
table=P/'operating-target-candidates.json';assert sha(table)=='53be103294e060b90fa5b80fa7d47ab9b4e997432ca9f4c1e8661d7feb0134b0';data=json.loads(table.read_bytes())
for ticker in ('LEU','TNDM'):
 c=next(x for x in data['cases'] if x['ticker']==ticker);a=next(x for x in c['selected_annual_interim'] if x['form']=='10-K');doc=RawInfoDocument.from_dict(readbound(a['existing_same_id_originals'][0]['binding']));body=readbound(a['body_cache_matches'][0]['binding']);root=readbound(a['root_bindings'][0]);p={'sec_static_archive_body':({'endpoint':a['primary_url'],'expected_content_hash':doc.content_hash},body),'sec_submissions_acceptance':({'issuer_cik':c['company_id'][4:],'accession_number':a['accession'],'form':a['form'],'primary_document':a['primary_document'],'accepted_at':a['accepted_at']},root)};row={'reviewed_available_at':doc.available_at.isoformat()};assert doc.source_type=='10-k';_verify_sec_document(doc,row,p,datetime.fromisoformat(c['prediction_time']))
 try:_verify_sec_document(doc,row,p,doc.available_at-timedelta(microseconds=1));raise AssertionError('early cutoff admitted')
 except ReviewedSourceRejected:pass
 checks.append({'case':'actual '+ticker,'original_type':doc.source_type,'document_id':doc.document_id,'native_proofs_pass_without_clone':True,'early_cutoff_rejected':True,'original_source_record':a['existing_same_id_originals'][0]['binding']})
for alias in ('filing','sec_filing','filing_body'):
 for f in ('S-1','10-K/A','6-K/A'):assert filing_source_matches_form(alias,f)
forms=('10-K','10-Q','8-K','20-F','40-F','6-K')
for f in forms:
 assert filing_source_matches_form(f.lower(),f)
 for bad in (f+'/A','X'+f,f+' extra',True,{},None,''):assert not filing_source_matches_form(f.lower(),bad)
for source in ('news','my_filing','filing_body_extra','10-k/a','10-k-summary',True,{},None):assert not filing_source_matches_form(source,'10-K')
checks.append({'case':'shared predicate generic registration/amendment positives, exact6 whole-form and typed/malformed negatives','passed':True})
t=ReviewedSecSourceAliasTests();t.setUp()
try:
 for legacy in (True,False):
  # Separate profile positives and true readonly successor consumption.
  alias,form=('sec_filing','10-K/A') if legacy else ('filing_body','S-1')
  fixture=t.fixture(alias,form);binding,store=t.restored(fixture,legacy=legacy);result=EvidenceResolver(store.snapshot()).resolve(RawInfoRequest('read','Read exact original',('filing',)),company_id=fixture.company,identity={},as_of=fixture.document.available_at);assert [r.document_id for r in result.documents]==[fixture.document.document_id]
  checks.append({'case':('legacy' if legacy else 'response')+' generic '+form,'original_type_retained':alias,'native_view_restart_worker_and_generic_consumer':True})
  for variant in ('wrong_form_alias','metadata_type','url','body','cutoff'):
   f=t.fixture('10-k' if variant=='wrong_form_alias' else '10-q','10-Q');path=t.review_path(f,legacy=legacy);r=json.loads(path.read_bytes());record=r['records'][0]
   if variant=='metadata_type':
    x=json.loads(f.original.read_bytes());x['metadata']['form']=True;f.original.write_text(json.dumps(x));record['original_record']['sha256']=sha(f.original)
   elif variant=='url':record['proofs'][0]['endpoint']='https://www.sec.gov/Archives/edgar/data/1/000000000225000001/different.htm'
   elif variant=='body':
    bodyproof=record['proofs'][0]
    if legacy:
     b=Path(bodyproof['artifact']['path']);x=json.loads(b.read_bytes());x['body']='different literal body';b.write_text(json.dumps(x));bodyproof['artifact']['sha256']=sha(b)
    else:
     b=Path(bodyproof['raw_response']['path']);b.write_bytes(b'different literal body');bodyproof['raw_response']['sha256']=sha(b);receiptpath=Path(bodyproof['artifact']['path']);receipt=json.loads(receiptpath.read_bytes());entry=next(x for x in receipt['requests'] if x['name']==bodyproof['entry_name']);entry['raw_sha256']=sha(b);entry['bytes']=b.stat().st_size;receiptpath.write_text(json.dumps(receipt));bodyproof['artifact']['sha256']=sha(receiptpath)
   elif variant=='cutoff':r['scope']['as_of']=(f.document.available_at-timedelta(microseconds=1)).isoformat()
   r['manifest_hash']=canonical_json_hash({k:v for k,v in r.items() if k!='manifest_hash'});path.write_text(json.dumps(r))
   try:materialize_reviewed_snapshot(path,f.base/'view');raise AssertionError('negative admitted '+variant)
   except ReviewedSourceRejected:pass
   checks.append({'case':('legacy' if legacy else 'response')+' '+variant,'rehashed_negative_rejected':True})
  # Rehashed legal-alias substitution in an already materialized file remains a
  # different original and must fail even when every materialized SHA is updated.
  f=t.fixture('10-q','10-Q');binding,store=t.restored(f,legacy=legacy);marker=Path(binding['root'])/'reviewed_snapshot.json';m=json.loads(marker.read_bytes());row=m['documents'][0];target=Path(binding['root'])/row['path'];x=json.loads(target.read_bytes());x['source_type']='sec_filing';target.write_text(json.dumps(x));row['sha256']=sha(target);marker.write_text(json.dumps(m));altered={**binding,'manifest_sha256':sha(marker)}
  try:open_raw_info_store(binding['root'],reviewed_snapshot=altered);raise AssertionError('changed canonical alias admitted')
  except ReviewedSourceRejected:pass
  checks.append({'case':('legacy' if legacy else 'response')+' rehashed materialized legal-alias substitution','restore_rejected':True})
finally:t.doCleanups()
assert all(sha(b['path'])==b['sha256'] for b in sources)
paths=['src/stock_opportunity_agent/data/filing_orientation.py','src/stock_opportunity_agent/data/reviewed_snapshot.py','tests/test_reviewed_sec_source_aliases.py'];bindings=[{'path':str(Path(x).resolve()),'sha256':sha(x)} for x in paths]
assert bindings[0]['sha256']=='e539b5dd16333a939a81169783c2716e50e410497e7e4a180c5247289b8581db';assert bindings[1]['sha256']=='3466550b2b8a7bb69aa6697860ac33425da3fc97de04ad224a9c28c48ad4e034'
report={'scope':'Independent readonly actual LEU/TNDM verifier plus isolated temporary fixture/read-only-view/consumer checks; no real oracle/store construction, GET, models, labels, LockedTest or source modifications.','old_failure_preserved':{'path':str(P/'sec-source-alias-boundary-probe.json'),'sha256':sha(P/'sec-source-alias-boundary-probe.json')},'current_bindings':bindings,'checks':checks,'all_passed':True,'actual_originals_and_proofs_unchanged':True,'limits':['Only source-type capability connection and native source qualification/readonly consumption; not whole-body operating sufficiency or actual case readiness.','Real LEU/TNDM sources were verifier-only, not materialized or appended; no original type/clock/content was changed.','Generic registration/amended forms remain proof-qualified but are not automatically declared annual/interim operating reports.']}
out=P/'sec-source-alias-current-review.json';out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'all_passed':True,'checks':len(checks),'review_sha256':sha(out)}))
