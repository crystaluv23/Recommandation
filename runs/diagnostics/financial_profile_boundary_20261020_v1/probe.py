"""Independent local proof-graph mutations; no global writes/network/model/labels."""
import argparse, copy, hashlib, json, tempfile
import importlib.machinery, importlib.util
from datetime import datetime, timezone
from pathlib import Path
from stock_opportunity_agent.artifacts import canonical_json_hash
from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoOracle, RawInfoStore, content_sha256
from stock_opportunity_agent.data.sec_company_facts import STANDARD_FORMS, STANDARD_TAXONOMIES, materialize_company_fact_documents
from stock_opportunity_agent.data import reviewed_snapshot as reader
PROFILE='sec_companyfacts_filed_next_utc_day_v1'
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
args=argparse.ArgumentParser();args.add_argument('--reader');args.add_argument('--output',default='current-results.json');args=args.parse_args()
if args.reader:
    loader=importlib.machinery.SourceFileLoader('independent_bound_reader',args.reader)
    module_spec=importlib.util.spec_from_loader(loader.name,loader)
    reader=importlib.util.module_from_spec(module_spec);loader.exec_module(reader)
def stamp(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(obj,ensure_ascii=False,sort_keys=True))
    return {'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
def productkey(record):
    return {'document_id':record['document_id'],'content_hash':record['content_hash'],'canonical_record_hash':canonical_json_hash(record)}
class Fixture:
    def __init__(self,base,body=None,cik='0000000001',cutoff='2025-02-01T00:00:00+00:00'):
        self.base=base;self.oracle=base/'oracle';RawInfoOracle.load_or_create(self.oracle)
        self.body=body or {'cik':1,'entityName':'Present-day name é','facts':{'us-gaap':{'CashAndCashEquivalentsAtCarryingValue':{'units':{'USD':[{'val':110,'end':'2024-12-31','filed':'2025-01-20','form':'10-K','accn':'0000000010-25-000001'},{'val':100,'end':'2023-12-31','filed':'2024-01-20','form':'10-K','accn':'0000000010-24-000001'}]}}}}}
        self.item={'cik':cik,'company_id':'cik_'+cik,'symbol':'EXAMPLE','source_url':'https://data.sec.gov/api/xbrl/companyfacts/CIK'+cik+'.json'}
        self.selection={'period_end_from':'0001-01-01','period_end_through':cutoff[:10],'available_at_through':cutoff,'taxonomy_allowlist':list(STANDARD_TAXONOMIES),'form_allowlist':list(STANDARD_FORMS)}
        self.cache={'body':self.body,'endpoint':self.item['source_url'],'source_key':'sec_edgar','capability':'financial_statements','payload_kind':'json','params':[['method','GET']],'retrieved_at':'2026-08-01T00:00:00+00:00'}
        rawtext=json.dumps(self.body,sort_keys=True,separators=(',',':'),ensure_ascii=False)
        self.raw=RawInfoDocument.create(document_id='sec_edgar:'+self.item['company_id']+':sec_company_facts_raw_response:'+content_sha256(rawtext)[:24],company_id=self.item['company_id'],source_type='sec_company_facts_raw_response',content=rawtext,published_at=datetime(2026,8,1,tzinfo=timezone.utc),available_at=datetime(2026,8,1,tzinfo=timezone.utc),metadata={'provider':'sec_edgar','cik':cik}).to_dict()
        self.provenance={'acquisition_policy_hash':canonical_json_hash({'schema_version':'sec-company-facts-acquisition-v1','selection':self.selection}),'acquisition_selection':self.selection}
        products,_=materialize_company_fact_documents(self.body,item=self.item,selection=self.selection,provenance=self.provenance,retrieved_at=datetime(2026,10,20,tzinfo=timezone.utc))
        self.records=[p.to_dict() for p in products]
        self.norm={'schema_version':'sec-companyfacts-normalization-v1','normalizer_profile':PROFILE,'item':self.item,'selection':self.selection,'provenance':self.provenance,'normalized_at':'2026-10-20T00:00:00+00:00','expected_products':[productkey(r) for r in self.records]}
        self.cutoff=cutoff
    def save(self):
        cb=stamp(self.base/'cache.json',self.cache);rb=stamp(self.oracle/'raw.json',self.raw)
        self.norm.update(source_cache=cb,raw_response=rb);nb=stamp(self.base/'normalization.json',self.norm)
        rows=[]
        for i,r in enumerate(self.records):
            rows.append({'document_id':r['document_id'],'company_id':r['company_id'],'content_hash':r['content_hash'],'verdict':'admitted','reason':'Synthetic exact normalization control; not primary filing audit','proof_profile':PROFILE,'reviewed_available_at':r['available_at'],'original_record':stamp(self.oracle/f'product-{i}.json',r),'proofs':[{'kind':k,'artifact':b} for k,b in [('sec_companyfacts_cache',cb),('sec_companyfacts_raw_response',rb),('sec_companyfacts_normalization',nb)]]})
        self.review={'schema_version':'reviewed-raw-info-snapshot-v1','oracle_identity':{'path':str(self.oracle/'oracle.json'),'sha256':hashlib.sha256((self.oracle/'oracle.json').read_bytes()).hexdigest()},'scope':{'as_of':self.cutoff,'company_ids':[self.item['company_id']],'acquisition_allowed':False},'records':rows}
        self.review['manifest_hash']=canonical_json_hash(self.review)
        return Path(stamp(self.base/'review.json',self.review)['path'])
def rewrite_product(f,field,value):
    r=f.records[0];p=json.loads(r['content'])
    if field=='filed': p['filing_date']=value
    else:p['facts'][0][field]=value
    r['content']=json.dumps(p,sort_keys=True,separators=(',',':'));r['content_hash']=content_sha256(r['content']);r['document_id']='secfacts:'+f.item['cik']+':'+p['accession_number']+':'+r['content_hash'][:16]
    f.norm['expected_products'][0]=productkey(r)
def result(f,path):
    try:
        binding=reader.materialize_reviewed_snapshot(f.save(),path)
        store=reader.open_raw_info_store(binding['root'],reviewed_snapshot=binding)
        return {'accepted':True,'documents':len(store.documents),'binding':binding}
    except Exception as e:return {'accepted':False,'type':type(e).__name__,'message':str(e)}
mutations={
 'value':lambda f:rewrite_product(f,'value',999),
 'unit':lambda f:rewrite_product(f,'unit','CAD'),
 'end':lambda f:rewrite_product(f,'end','2022-12-31'),
 'filed':lambda f:rewrite_product(f,'filed','2024-01-19'),
 'body_cik':lambda f:f.cache['body'].update(cik=2),
 'endpoint':lambda f:f.cache.update(endpoint=f.item['source_url'].replace('data.sec.gov','evil.example')),
 'method':lambda f:f.cache.update(params=[['method','POST']]),
 'selection_cap':lambda f:f.selection.update(period_end_from='2022-01-01'),
 'form_allowlist':lambda f:f.selection['form_allowlist'].remove('10-Q'),
 'early_normalized_clock':lambda f:f.norm.update(normalized_at='2026-07-31T23:59:59+00:00'),
 'expected_missing':lambda f:f.norm['expected_products'].pop(),
 'expected_extra':lambda f:f.norm['expected_products'].append({'document_id':'extra','content_hash':'x','canonical_record_hash':'y'}),
 'expected_duplicate':lambda f:f.norm['expected_products'].append(copy.deepcopy(f.norm['expected_products'][0])),
 'rawresponse':lambda f:f.raw.update(content='{}',content_hash=content_sha256('{}')),
 'whole_raw':lambda f:setattr(f,'records',[copy.deepcopy(f.raw)]),
 'metadata_bool_as_integer':lambda f:f.records[0]['metadata'].update(requires_primary_filing_audit=1),
 'metadata_count_as_float':lambda f:f.records[0]['metadata'].update(fact_count=float(f.records[0]['metadata']['fact_count'])),
}
report={'scope':'Independent synthetic temporary proof graph; fixed SEC cache body except named source-request/CIK probes; outer hashes recomputed, no source authentication claim.','code_bindings':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(args.reader) if args.reader else ROOT/'src/stock_opportunity_agent/data/reviewed_snapshot.py',ROOT/'src/stock_opportunity_agent/data/sec_company_facts.py']},'mutations':{}}
with tempfile.TemporaryDirectory() as tmp:
    base=Path(tmp)
    for name,mutate in mutations.items():
        f=Fixture(base/name);mutate(f);out=result(f,f.base/'view');report['mutations'][name]=out
        if out['accepted']:
            target=HERE/('first-failures' if args.output=='initial-results.json' else 'reproduced-failures')/name
            import shutil;shutil.copytree(f.base,target,dirs_exist_ok=True)
    f=Fixture(base/'positive');b=reader.materialize_reviewed_snapshot(f.save(),f.base/'view');s=reader.open_raw_info_store(b['root'],reviewed_snapshot=b)
    report['positive']={'restart':len(s.documents)==2,'worker':s.snapshot().documents==s.documents,'refresh':s.refresh()==0,'full_record_equality':[d.to_dict() for d in s.documents]==f.records}
    original_cache=(f.base/'cache.json').read_bytes();(f.base/'cache.json').write_text('{}')
    for name,op in [('refresh',s.refresh),('worker',s.snapshot)]:
        try:op();report['positive'][name+'_drift_rejected']=False
        except reader.ReviewedSourceRejected:report['positive'][name+'_drift_rejected']=True
    (f.base/'cache.json').write_bytes(original_cache)
    for name,destination in [('direct_inside',f.oracle/'forbidden'),('symlink_inside',base/'alias'/'forbidden')]:
        if name=='symlink_inside':(base/'alias').symlink_to(f.oracle,target_is_directory=True)
        try:reader.materialize_reviewed_snapshot(f.save(),destination);report['positive'][name+'_rejected']=False
        except reader.ReviewedSourceRejected:report['positive'][name+'_rejected']=True
p=HERE/args.output;p.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
