"""Independent temporary SEC proof graph and rehashed counterexamples."""
import argparse,copy,gzip,hashlib,json,tempfile
import importlib.machinery,importlib.util
from datetime import datetime,timezone
from pathlib import Path
from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.data.raw_info import RawInfoDocument,RawInfoOracle,RawInfoStore,content_sha256
from stock_opportunity_agent.data import reviewed_snapshot as reader
D=Path(__file__).resolve().parent;R=D.parents[2]
parser=argparse.ArgumentParser();parser.add_argument('--reader');parser.add_argument('--output',default='current-results.json');args=parser.parse_args()
if args.reader:
 loader=importlib.machinery.SourceFileLoader('independent_sec_reader',args.reader);spec=importlib.util.spec_from_loader(loader.name,loader);reader=importlib.util.module_from_spec(spec);loader.exec_module(reader)
def bound(p):return {'path':str(p.resolve()),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
def write(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,sort_keys=True));return bound(p)
class Fixture:
 def __init__(self,base,exhibit=False,response=False,linked=True):
  self.base=base;self.oracle=base/'oracle';RawInfoOracle.load_or_create(self.oracle);self.exhibit=exhibit;self.response=response;self.linked=linked
  self.company='cik_0000000001';self.acc='0000000002-25-000001';self.form='40-F' if exhibit else '10-Q';self.filename='CIK0000000001-submissions-001.json'
  self.rooturl='https://data.sec.gov/submissions/CIK0000000001.json';self.archiveurl='https://data.sec.gov/submissions/'+self.filename;self.parenturl='https://www.sec.gov/Archives/edgar/data/1/000000000225000001/report.htm';self.url=self.parenturl.replace('report.htm','aif.htm') if exhibit else self.parenturl
  self.arrays={'accessionNumber':[self.acc],'filingDate':['2025-05-05'],'form':[self.form],'primaryDocument':['report.htm'],'acceptanceDateTime':['2025-05-05T20:00:00Z'],'reportDate':['2025-03-31']}
  self.root={'cik':1,'filings':{'recent':{k:[] for k in self.arrays} if linked else copy.deepcopy(self.arrays),'files':[{'name':self.filename,'filingCount':1,'filingFrom':'2025-05-01','filingTo':'2025-05-10'}]}}
  self.parent='<html><table><tr><td>99.1</td><td><a href="aif.htm">Annual information form</a></td></tr></table></html>'
  self.content='<html>Independent original interim body é. Numeric and operating sufficiency untested.</html>'
  self.receipt={'automatic_retries':0,'redirects_followed':0,'requests':[]};self.rawbytes={};self.entries={}
  for name,url,text in [('body',self.url,self.content),('root',self.rooturl,json.dumps(self.root)),('archive',self.archiveurl,json.dumps(self.arrays)),('parent',self.parenturl,self.parent)]:
   self.rawbytes[name]=text.encode();self.entries[name]={'name':name,'method':'GET','url':url,'response_url':url,'status':'http_response_retained','http_status':200,'started_at_utc':'2026-10-20T00:00:00Z','retrieved_at_utc':'2026-10-20T00:00:01Z','raw_response':str(base/(name+'.raw')),'response_headers':{}}
  self.proofs=[];bp={'kind':'sec_static_archive_body_response','entry_name':'body','endpoint':self.url,'expected_content_hash':content_sha256(self.content),'document_role':'incorporated_exhibit' if exhibit else 'primary'};self.proofs.append(bp)
  self.rp={'kind':'sec_submissions_root_response' if response else 'sec_submissions_root','issuer_cik':'0000000001','accession_number':self.acc,'form':self.form,'primary_document':'report.htm','filing_date':'2025-05-05','accepted_at':'2025-05-05T20:00:00Z'}
  if response:self.rp.update(entry_name='root',endpoint=self.rooturl)
  self.proofs.append(self.rp)
  if linked:self.proofs.append({'kind':'sec_submissions_linked_archive_response' if response else 'sec_submissions_linked_archive','filename':self.filename,**({'entry_name':'archive','endpoint':self.archiveurl} if response else {})})
  md={'source_url':self.url,'provider':'sec_edgar','cik':'0000000001','accession_number':self.acc,'form':self.form};did='sec:'+self.company+':'+self.acc.replace('-','')
  if exhibit:
   bp.update(exhibit_document='aif.htm',exhibit_type='99.1');self.proofs.append({'kind':'sec_parent_primary_response','entry_name':'parent','endpoint':self.parenturl,'document_role':'primary','expected_content_hash':content_sha256(self.parent)})
   md.update(parent_form=self.form,parent_primary_document='report.htm',exhibit_document='aif.htm',document_role='incorporated_exhibit',exhibit_type='99.1');did='sec-exhibit:'+self.company+':'+self.acc.replace('-','')+':aif.htm'
  t=datetime(2025,5,5,20,tzinfo=timezone.utc);self.record=RawInfoDocument.create(document_id=did,company_id=self.company,source_type='filing',published_at=t,available_at=t,content=self.content,metadata=md).to_dict()
  self.receipt_mutator=lambda r:None
 def save(self):
  for name,b in self.rawbytes.items():p=self.base/(name+'.raw');p.write_bytes(b);self.entries[name].update(raw_sha256=bound(p)['sha256'],bytes=len(b))
  requests=[copy.deepcopy(self.entries[n]) for n in ['body','root','archive','parent'] if n!='parent' or self.exhibit]
  self.receipt['requests']=requests;self.receipt_mutator(self.receipt);receipt=write(self.base/'results.json',self.receipt)
  for p in self.proofs:
   if p['kind'].endswith('_response'):
    name=p['entry_name'];p.update(artifact=receipt,raw_response=bound(self.base/(name+'.raw')))
   else:
    payload,url=(self.root,self.rooturl) if p['kind']=='sec_submissions_root' else (self.arrays,self.archiveurl)
    p['artifact']=write(self.base/(p['kind']+'.json'),{'body':payload,'endpoint':url,'source_key':'sec_edgar','capability':'filing_documents','payload_kind':'json','params':[['method','GET']],'retrieved_at':'2026-10-20T00:00:00Z'})
  row={'document_id':self.record['document_id'],'company_id':self.company,'content_hash':self.record['content_hash'],'original_record':write(self.oracle/'original.json',self.record),'verdict':'admitted','reason':'Independent synthetic source linkage control, no semantic sufficiency claim','proof_profile':'sec_filing_exhibit_response_v1' if self.exhibit else 'sec_filing_response_acceptance_v1','reviewed_available_at':self.record['available_at'],'proofs':self.proofs}
  review={'schema_version':'reviewed-raw-info-snapshot-v1','oracle_identity':bound(self.oracle/'oracle.json'),'scope':{'as_of':'2025-07-31T00:00:00Z','company_ids':[self.company],'acquisition_allowed':False},'records':[row]};review['manifest_hash']=canonical_json_hash(review);write(self.base/'review.json',review);return self.base/'review.json'
def execute(f):
 try:
  binding=reader.materialize_reviewed_snapshot(f.save(),f.base/'view');store=reader.open_raw_info_store(binding['root'],reviewed_snapshot=binding)
  return {'accepted':True,'worker_exact':canonical_json_hash([x.to_dict() for x in store.snapshot().documents])==canonical_json_hash([f.record])}
 except Exception as e:return {'accepted':False,'type':type(e).__name__,'message':str(e)}
def patchreceipt(f,key,v):f.receipt_mutator=lambda r:r['requests'][0].update({key:v})
mutations={
 'wrong_method':lambda f:patchreceipt(f,'method','POST'),
 'wrong_raw_path':lambda f:patchreceipt(f,'raw_response',str(f.base/'same-name-elsewhere'/'body.raw')),
 'wrong_raw_SHA':lambda f:patchreceipt(f,'raw_sha256','0'*64),
 'wrong_bytes_type':lambda f:patchreceipt(f,'bytes',True),
 'duplicate_endpoint':lambda f:setattr(f,'receipt_mutator',lambda r:r['requests'].append({**r['requests'][0],'name':'again'})),
 'duplicate_name':lambda f:setattr(f,'receipt_mutator',lambda r:r['requests'].append({**r['requests'][0],'url':f.parenturl+'/other'})),
 'wrong_response_url':lambda f:patchreceipt(f,'response_url',f.url+'?changed'),
 'clock_naive':lambda f:patchreceipt(f,'started_at_utc','2026-10-20T00:00:00'),
 'clock_reverse':lambda f:patchreceipt(f,'retrieved_at_utc','2026-10-19T23:59:59Z'),
 'root_wrong_issuer':lambda f:f.root.update(cik=2),
 'missing_root_link':lambda f:f.root['filings'].update(files=[]),
 'bad_parallel_column':lambda f:f.arrays.update(reportDate='2025-03-31'),
 'target_duplicate':lambda f:[v.append(v[0]) for v in f.arrays.values()],
 'bad_parent_form':lambda f:f.record['metadata'].update(form='6-K'),
 'backdate_original':lambda f:f.record.update(published_at='2025-02-12T00:00:00Z',available_at='2025-02-12T00:00:00Z'),
 'body_wrong_role':lambda f:f.proofs[0].update(document_role='primary'),
 'wrong_exhibit_code':lambda f:f.proofs[0].update(exhibit_type='99.2'),
}
def deceptive_code(f):
 f.parent='<html><table><tr><td>99.1</td><td><a href="aif.htm">Annual information form; see Exhibit99.2 for financials</a></td></tr></table></html>'
 f.rawbytes['parent']=f.parent.encode();f.proofs[-1]['expected_content_hash']=content_sha256(f.parent);f.proofs[0]['exhibit_type']='99.2';f.record['metadata']['exhibit_type']='99.2'
mutations['incidental_code_in_description']=deceptive_code
report={'reader_sha256':hashlib.sha256((Path(args.reader) if args.reader else R/'src/stock_opportunity_agent/data/reviewed_snapshot.py').read_bytes()).hexdigest(),'synthetic_isolated_scope':True,'negative_controls':{},'positive_controls':{}}
with tempfile.TemporaryDirectory() as temporary:
 base=Path(temporary)
 for name,mutate in mutations.items():
  f=Fixture(base/name,exhibit=True);mutate(f);report['negative_controls'][name]=execute(f)
 for name,options in [('primary_root',{'linked':False}),('primary_linked',{}),('response_root_linked',{'response':True}),('exhibit',{'exhibit':True})]:
  report['positive_controls'][name]=execute(Fixture(base/name,**options))
p=D/args.output;p.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
