"""Fixed original two capability failures rechecked on stable current selector."""
from pathlib import Path
from datetime import datetime,timezone
import json,hashlib
from stock_opportunity_agent import signal_library as lib
from stock_opportunity_agent.data.raw_info import RawInfoDocument
from stock_opportunity_agent.data.resolution import EvidenceResolver,RawInfoRequest,_rank_documents
R=Path('/Users/l/Project/Recommandation');O=R/'runs/diagnostics/financial_input_selection_boundary_20261021_v1';T=datetime(2025,2,1,tzinfo=timezone.utc)
initial_sha=hashlib.sha256(Path(lib.__file__).read_bytes()).hexdigest()
rows=[]
for file in ['dominance-results.json','required-witness-results.json']:
 old=json.loads((O/file).read_text());docs=tuple(RawInfoDocument.from_dict(d) for d in old['source_records'])
 spec=lib.SignalSpec(signal_id='revenue_growth_yoy',version=1,category='financial',description='Synthetic basis preservation control.',execution_type=lib.SignalExecutionType.DETERMINISTIC,function='financial.revenue_growth_yoy',source_types=('sec_company_facts',))
 request=RawInfoRequest(request_id='signal:'+spec.ref,description=spec.description,source_types=spec.source_types,max_documents=10)
 ranked=tuple(_rank_documents(docs,request));helper=lib._revenue_growth_input_facts;basis=helper(spec,ranked,T)
 assert repr(lib._input_basis_identity(basis))==old['full_basis']
 selector=lib._measurement_input_selector(spec,lib._revenue_growth_signal,T);selected=tuple(selector(ranked,request))
 assert 0<len(selected)<=10 and lib._input_basis_identity(helper(spec,selected,T))==lib._input_basis_identity(basis)
 class Corpus:
  acquisition_allowed=False
  documents=docs
  def search(self,company_id,**kwargs):return list(self.documents)
 r=EvidenceResolver(Corpus()).resolve(request,company_id='cik_0000000001',identity={},as_of=T,select_documents=selector)
 assert r.status=='resolved' and [d.document_id for d in r.documents]==[d.document_id for d in selected]
 rows.append({'original_failure':{'path':str(O/file),'sha256':hashlib.sha256((O/file).read_bytes()).hexdigest()},'old_selector_ids':old['selector_ids'],'old_native_status':old['native_selector_status'],'new_selector_ids':[d.document_id for d in selected],'new_native_status':r.status,'full_basis_exact':True,'documents':len(selected),'limit':10})
assert initial_sha==hashlib.sha256(Path(lib.__file__).read_bytes()).hexdigest()
out={'verdict':'PASS_two_fixed_offline_capability_counterexamples','code_sha256':initial_sha,'controls':rows,'limits':'Synthetic pure matching/native resolver only, not model behavior, actual source execution, full feasibility search or research gain. Original c665 failures remain unchanged.'}
(O/'ability-final-results.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
