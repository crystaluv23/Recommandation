"""Independent temporary capture/type/store/real-resolver controls; no actual source append."""
from pathlib import Path
from datetime import datetime,timezone
from copy import deepcopy
from dataclasses import replace
import hashlib,importlib.util,json,sys,tempfile
from stock_opportunity_agent.data import raw_info as current
from stock_opportunity_agent.data.raw_info import RawInfoDocument,RawInfoStore,capture_document_id
from stock_opportunity_agent.data.resolution import EvidenceResolver,RawInfoRequest,_deduplicate_documents
from stock_opportunity_agent.models import ValidationError
P=Path(__file__).resolve().parent
oldpath=Path('/tmp/recommandation-capture-id-v1/candidate-before-search-guard-raw_info.py')
spec=importlib.util.spec_from_file_location('capture_pre_search_reconstructed',oldpath);old=importlib.util.module_from_spec(spec);sys.modules[spec.name]=old;spec.loader.exec_module(old)
clock=datetime(2025,1,2,tzinfo=timezone.utc)
def doc(module,metadata):return module.RawInfoDocument.create(document_id='legacy',company_id='issuer',source_type='filing',published_at=clock,available_at=clock,content='Complete source body é',metadata=metadata)
def rejected(fn):
 try:fn()
 except ValidationError:return True
 return False
results=[]
for label,module in [('reconstructed_pre_search_candidate',old),('current',current)]:
 cap=doc(module,{'nested':{'flag':True}}).as_capture();store=module.RawInfoStore(documents=(cap,));cap.metadata['nested']['flag']=1
 load=rejected(lambda:store.load(cap.document_id))
 search=rejected(lambda:store.search('issuer',as_of=clock))
 documents=rejected(lambda:store.documents)
 resolved_reject=rejected(lambda:EvidenceResolver(store).resolve(RawInfoRequest(request_id='probe',description='source body',source_types=('filing',)),company_id='issuer',identity={},as_of=clock))
 results.append({'version':label,'load_reject':load,'search_reject':search,'documents_reject':documents,'native_resolver_reject':resolved_reject})
assert results[0]=={'version':'reconstructed_pre_search_candidate','load_reject':True,'search_reject':False,'documents_reject':False,'native_resolver_reject':False},results
assert all(results[1][k] is True for k in ('load_reject','search_reject','documents_reject','native_resolver_reject')),results
# Complete typed canonical distinction and JSON restrictions.
variants=[None,False,True,0,1,0.0,1.0,'1',[],{},[1,2],[2,1]]
ids=[doc(current,{'typed':x}).as_capture().document_id for x in variants];assert len(set(ids))==len(ids)
a=doc(current,{'a':1,'z':[True,1,1.0,None]}).as_capture();z=doc(current,{'z':[True,1,1.0,None],'a':1}).as_capture();assert a.document_id==z.document_id
bad=[float('nan'),float('inf'),-float('inf'),(1,2),{1:'key'}]
assert all(rejected(lambda v=v:doc(current,{'v':v}).as_capture()) for v in bad)
for key,value in [('nested',{'flag':1}),('nested',{'flag':1.0})]:
 cap=doc(current,{'nested':{'flag':True}}).as_capture();record=cap.to_dict();record['metadata'][key]=value
 assert rejected(lambda:RawInfoDocument.from_dict(record))
for identifier in ('rawcap:v1:forged','rawcap:v2:forged','rawcap:','rawcap:v1:'+('0'*64)):
 record=a.to_dict();record['document_id']=identifier;assert rejected(lambda:RawInfoDocument.from_dict(record))
for extra in ({'extra':None},{'content':'changed'}):
 record={**a.to_dict(),**extra};assert rejected(lambda:RawInfoDocument.from_dict(record))
with tempfile.TemporaryDirectory() as d:
 store=RawInfoStore(d,documents=(a,));assert store.append(a.as_capture()) is False
 assert RawInfoStore(d).load(a.document_id).to_dict()==a.to_dict()
 path=Path(d)/a.source_type/a.company_id/(a.document_id+'.json');record=json.loads(path.read_text());record['metadata']['a']=1.0;path.write_text(json.dumps(record))
 assert rejected(lambda:RawInfoStore(d))
legacy=doc(current,{'capture':1});same=replace(legacy,metadata={'capture':2});store=RawInfoStore(documents=(legacy,));assert store.append(same) is False and store.load('legacy').metadata=={'capture':1}
captures=(legacy.as_capture(),same.as_capture());assert captures[0].document_id!=captures[1].document_id
unique,duplicates=_deduplicate_documents(captures);assert len(unique)==len(duplicates)==1
out={'verdict':'PASS_bounded_capture_core','mutation_resolver_comparison':results,'typed_variant_distinct_count':len(ids),'strict_invalid_JSON_rejected':len(bad),
 'forged_namespace_record_and_disk_load_rejected':True,'recorded_replay_idempotent':True,'legacy_same_content_refetch_unchanged':True,'two_captures_one_deduplicated_fact':True,
 'current_source':{'path':str(Path(current.__file__).resolve()),'sha256':hashlib.sha256(Path(current.__file__).read_bytes()).hexdigest()},
 'old_counterexample_source':{'path':str(oldpath),'sha256':hashlib.sha256(oldpath.read_bytes()).hexdigest(),'provenance':'Owner reconstructed pre-search-guard intermediate by removing only two guards; not a contemporaneous byte capture.'},
 'scope':'Only synthetic in-memory/temp records and real resolver; no global/actual append, network, models, LabelStore, prepare or old-stage resume.'}
(P/'core-results.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
