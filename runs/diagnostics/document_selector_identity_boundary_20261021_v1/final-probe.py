"""Native resolver selector membership controls using only in-memory documents."""
from pathlib import Path
from datetime import datetime,timezone
from dataclasses import replace
from copy import deepcopy
import hashlib,json
from stock_opportunity_agent.data.raw_info import RawInfoDocument
from stock_opportunity_agent.data.resolution import EvidenceResolver,RawInfoRequest
from stock_opportunity_agent.artifacts import canonical_json_hash
ROOT=Path('/Users/l/Project/Recommandation');OUT=ROOT/'runs/diagnostics/document_selector_identity_boundary_20261021_v1'
STAMP=datetime(2025,1,1,tzinfo=timezone.utc)
class FixtureCorpus:
 """No Store or persistence; supply already-eligible documents to native resolver."""
 acquisition_allowed=False
 def __init__(self,doc):self.documents=(doc,)
 def search(self,company_id,**kwargs):
  return [d for d in self.documents if d.company_id==company_id and d.available_at<=kwargs['as_of']]

def source(value,capture=False):
 doc=RawInfoDocument.create(document_id='legacy-fixture',company_id='issuer',source_type='filing',published_at=STAMP,available_at=STAMP,content='Actual immutable retained disclosure.',metadata={'selection':{'value':value}})
 return doc.as_capture() if capture else doc
request=RawInfoRequest(request_id='selector-test',description='Retain source disclosure.',source_types=('filing',),max_documents=1)
rows=[]
def run(name,old,new,mode='replace',capture=False):
 doc=source(old,capture);before=deepcopy(doc.to_dict());returned=[]
 def select(pool,req):
  assert req==request and pool==(doc,)
  if mode=='unchanged':result=pool[0]
  elif mode=='metadata_in_place':
   pool[0].metadata['selection']['value']=new;result=pool[0]
  elif mode=='body':result=RawInfoDocument.create(**{k:v for k,v in doc.to_dict().items() if k not in ('published_at','available_at','content_hash','content')},published_at=STAMP,available_at=STAMP,content='Changed retained disclosure.')
  elif mode=='id':result=replace(doc,document_id='new-fixture')
  else:result=replace(doc,metadata={'selection':{'value':new}})
  returned.append(result);return (result,)
 try:
  result=EvidenceResolver(FixtureCorpus(doc)).resolve(request,company_id='issuer',identity={},as_of=STAMP,include_context=True,select_documents=select)
  status='accepted';error=None
 except Exception as exc:status='rejected';error={'type':type(exc).__name__,'message':str(exc)}
 after=returned[0].to_dict() if returned else None
 row={'name':name,'capture':capture,'status':status,'error':error,'before':before,'returned':after,'original_and_returned_python_equal':doc==returned[0] if returned else None,'typed_canonical_changed':canonical_json_hash(before)!=canonical_json_hash(after) if after else None}
 if status=='accepted':row['resolution']={'status':result.status,'document_ids':[r.document_id for r in result.documents],'literal_context':[s.exact_text for s in result.context_spans]}
 rows.append(row)
run('unchanged_positive',True,True,'unchanged')
run('legacy_bool_to_int',True,1)
run('legacy_int_to_float',1,1.0)
run('legacy_body_replacement_negative',True,True,'body')
run('legacy_other_id_negative',True,True,'id')
run('capture_metadata_replacement_negative',True,1,capture=True)
run('legacy_metadata_in_place',True,1,'metadata_in_place')
run('capture_metadata_in_place',True,1,'metadata_in_place',capture=True)
assert rows[0]['status']=='accepted' and rows[0]['typed_canonical_changed'] is False
assert all(rows[i]['status']=='rejected' and rows[i]['typed_canonical_changed'] is True for i in (1,2,6,7))
assert all(rows[i]['status']=='rejected' for i in (3,4,5))
code=ROOT/'src/stock_opportunity_agent/data/resolution.py';raw=ROOT/'src/stock_opportunity_agent/data/raw_info.py'
out={'finding':'PASS_fixed_original_typed_identity_and_nested_mutation_controls','controls':rows,'code_bindings':[{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in (code,raw)],'spec':'spec/src/stock_opportunity_agent/data/resolution.md:111-119','forbidden_operations':{'Store_construction':0,'append_prepare_execute_GET_model_labels':0},'limits':'Synthetic in-memory raw documents through actual EvidenceResolver.resolve/select_documents. No production sources, stores or measurements were executed.'}
(OUT/'final-results.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'finding':out['finding'],'controls':[{k:r[k] for k in ('name','status','typed_canonical_changed')} for r in rows],'code_bindings':out['code_bindings']},indent=2))
