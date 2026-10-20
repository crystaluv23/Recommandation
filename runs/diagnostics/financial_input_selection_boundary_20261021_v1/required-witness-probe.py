"""Synthetic >10 pool: sufficient legal subset versus harmful generic filling."""
from pathlib import Path
from datetime import datetime,timezone
import json,hashlib,sys,types
from stock_opportunity_agent import signal_library as lib
from stock_opportunity_agent.data.raw_info import RawInfoDocument
from stock_opportunity_agent.data.resolution import EvidenceResolver,RawInfoRequest,_rank_documents
if len(sys.argv)>1:
 name='stock_opportunity_agent._selector_original_probe'; module=types.ModuleType(name);module.__file__=sys.argv[1];module.__package__='stock_opportunity_agent';sys.modules[name]=module;exec(compile(Path(sys.argv[1]).read_text(),sys.argv[1],'exec'),module.__dict__);lib=module
R=Path('/Users/l/Project/Recommandation');O=R/'runs/diagnostics/financial_input_selection_boundary_20261021_v1'
T=datetime(2025,2,1,tzinfo=timezone.utc);PUB=datetime(2025,1,21,tzinfo=timezone.utc)
def fact(tag,start,end,value):return {'tag':tag,'start':start,'end':end,'unit':'USD','value':value}
def doc(name,facts):
 body={'schema_version':'sec-company-facts-document-v1','cik':'0000000001','filing_date':'2025-01-20','form':'10-K','facts':facts,'fixture':name}
 return RawInfoDocument.create(document_id=name,company_id='cik_0000000001',source_type='sec_company_facts',published_at=PUB,available_at=PUB,content=json.dumps(body,sort_keys=True,separators=(',',':')),metadata={'cik':'0000000001'})
A='Revenues';B='RevenueFromContractWithCustomerExcludingAssessedTax';C='SalesRevenueNet'
a=doc('a-operands',[fact(A,'2024-01-01','2024-12-31',100),fact(A,'2023-01-01','2023-12-31',80)])
b=doc('b-fill-changes-canonical',[fact(B,'2024-01-01','2024-12-31',110),fact(B,'2023-01-01','2023-12-31',100)])
noise=[doc('n'+str(i),[]) for i in range(9)]
w=doc('z-dominance-witness',[fact(B,'2010-01-01','2010-12-31',1),fact(C,'2010-01-01','2010-12-31',100)])
a=doc('a-operands-and-competing-tag',json.loads(a.content)['facts']+json.loads(b.content)['facts'])
pool=(a,*noise,w)
spec=lib.SignalSpec(signal_id='revenue_growth_yoy',version=1,category='financial',description='Synthetic basis preservation control.',execution_type=lib.SignalExecutionType.DETERMINISTIC,function='financial.revenue_growth_yoy',source_types=('sec_company_facts',))
request=RawInfoRequest(request_id='signal:'+spec.ref,description=spec.description,source_types=spec.source_types,max_documents=10)
helper=lib._revenue_growth_input_facts;selector=lib._measurement_input_selector(spec,lib._revenue_growth_signal,T)
ranked=tuple(_rank_documents(pool,request));full=helper(spec,ranked,T);selected=tuple(selector(ranked,request));alternative=(a,w)
class Corpus:
 acquisition_allowed=False
 documents=pool
 def search(self,company_id,**kwargs):return list(pool)
r=EvidenceResolver(Corpus()).resolve(request,company_id=a.company_id,identity={},as_of=T,select_documents=selector)
identity=lambda x:repr(lib._input_basis_identity(x))
assert len(pool)==11 and full.unavailable_reason is None
assert identity(full)==identity(helper(spec,alternative,T))
assert selected==() and r.status=='unresolved'
# Alternative obeys the exact same native unchanged-member/capacity gate.
r2=EvidenceResolver(Corpus()).resolve(request,company_id=a.company_id,identity={},as_of=T,select_documents=lambda pool,req:alternative)
assert r2.status=='resolved' and len(r2.documents)==2
out={'finding':'FAIL_required_nonoperand_witness_lost_despite_feasible_two_document_subset','synthetic':True,'full_pool_documents':11,'limit':10,'ranked_ids':[d.document_id for d in ranked],'full_basis':identity(full),'selector_ids':[d.document_id for d in selected],'native_selector_status':r.status,'alternative_ids':[a.document_id,w.document_id],'alternative_basis_equal':True,'alternative_native_status':r2.status,'source_records':[d.to_dict() for d in pool],'code_binding':{'path':lib.__file__,'sha256':hashlib.sha256(Path(lib.__file__).read_bytes()).hexdigest()},'scope':'Only pure fact/operand matching and native input resolution. No Signal arithmetic/execution, Store, network, models, labels or actual stage.'}
(O/'required-witness-results.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k not in ('source_records','full_basis')},indent=2))
