"""Offline old/new numeric regression, not production selection or >10 execution."""
from pathlib import Path
from datetime import datetime,timezone
import sys,types,json,hashlib,subprocess
from stock_opportunity_agent import signal_library as new
from stock_opportunity_agent.data.raw_info import RawInfoDocument
from stock_opportunity_agent.data.resolution import EvidenceResolver,RawInfoRequest
from stock_opportunity_agent.artifacts import canonical_json_hash as digest
R=Path('/Users/l/Project/Recommandation');O=R/'runs/diagnostics/financial_input_selection_boundary_20261021_v1';P=R/'runs/diagnostics/reviewed_gpre_capture_snapshot_20261021_v1/stage'
read=lambda p:json.loads(Path(p).read_text())
oldtext=(O/'original-signal_library.py.txt').read_text();name='stock_opportunity_agent._financial_before_f5';old=types.ModuleType(name);old.__file__=str(O/'original-signal_library.py.txt');old.__package__='stock_opportunity_agent';sys.modules[name]=old;exec(compile(oldtext,old.__file__,'exec'),old.__dict__)
old_functions=old.default_deterministic_signal_functions();new_functions=new.default_deterministic_signal_functions()
plan=read(P/'plan.json');review=read(P/'source-review.json');company=plan['case']['company_id'];T=datetime.fromisoformat(plan['case']['prediction_time'])
real_docs=tuple(RawInfoDocument.from_dict(read(r['original_record']['path'])) for r in review['records'] if r['verdict']=='admitted' and r['company_id']==company)
class Corpus:
 acquisition_allowed=False
 def __init__(self,documents):self.documents=documents
 def search(self,company_id,**kwargs):return [d for d in self.documents if d.company_id==company_id and d.available_at<=kwargs['as_of']]

def evaluate(module,spec,data,as_of):
 try:return {'result':module.default_deterministic_signal_functions()[spec.function](module.SignalSpec.from_dict(spec.to_dict()),data,as_of).to_dict()}
 except Exception as e:return {'exception_type':type(e).__name__,'message':str(e)}
rows=[]
for group in plan['groups']:
 for ref in group['refs']:
  binding=next(b for b in group['definition_bindings'] if b['path'].endswith('/'+ref.split(':')[0]+'/versions/'+ref.split(':')[1]+'/spec.json'))
  spec=new.SignalSpec.from_dict(read(binding['path']))
  if not spec.function or not spec.function.startswith('financial.'):continue
  pol=spec.retrieval_policy
  request=RawInfoRequest(request_id='signal:'+spec.ref,description=spec.description,source_types=spec.source_types,lookback_days=pol.lookback_days,max_documents=10,query=pol.query,required_source_groups=pol.required_source_groups,minimum_distinct_periods=pol.minimum_distinct_periods,minimum_period_span_days=pol.minimum_period_span_days,minimum_observations=pol.minimum_observations)
  captured=[]
  def capture(pool,req):captured.extend(pool);return pool[:10]
  EvidenceResolver(Corpus(real_docs))._local_documents(request,company_id=company,identity=plan['identity'],as_of=T,select_documents=capture)
  before=evaluate(old,spec,tuple(captured),T);after=evaluate(new,spec,tuple(captured),T)
  assert digest(before)==digest(after),(ref,before,after)
  rows.append({'case':'actual_GPRE_full_filtered_pool','group':group['name'],'ref':ref,'pool_size':len(captured),'equal':True,'output':after})
# Small raw CompanyFacts fixtures covering old unavailable/partial/zero/freshness and parameters.
STAMP=datetime(2025,1,21,tzinfo=timezone.utc);AT=datetime(2025,2,1,tzinfo=timezone.utc)
def doc(label,facts):
 payload={'schema_version':'sec-company-facts-document-v1','cik':'0000000001','filing_date':'2025-01-20','form':'10-K','facts':facts}
 return RawInfoDocument.create(document_id=label,company_id='cik_0000000001',source_type='sec_company_facts',published_at=STAMP,available_at=STAMP,content=json.dumps(payload,sort_keys=True,separators=(',',':')),metadata={'cik':'0000000001'})
def f(tag,start,end,val,unit='USD'):return {'tag':tag,'unit':unit,'start':start,'end':end,'value':val}
C='CashAndCashEquivalentsAtCarryingValue';OCF='NetCashProvidedByUsedInOperatingActivities';RV='Revenues';SH='WeightedAverageNumberOfSharesOutstandingBasic'
base=[f(RV,'2024-01-01','2024-12-31',100),f(RV,'2023-01-01','2023-12-31',80),f(RV,'2022-01-01','2022-12-31',70),f('GrossProfit','2024-01-01','2024-12-31',40),f('GrossProfit','2023-01-01','2023-12-31',20),f(OCF,'2024-01-01','2024-12-31',-10),f(C,None,'2024-12-31',20),f('LiabilitiesCurrent',None,'2024-12-31',10),f(SH,'2024-01-01','2024-12-31',90,'shares'),f(SH,'2023-01-01','2023-12-31',100,'shares')]
fixtures={'complete':base,'empty':[],'zero_prior_revenue':[f(RV,'2024-01-01','2024-12-31',100),f(RV,'2023-01-01','2023-12-31',0)],'missing_same_currency_cash':[f(OCF,'2024-01-01','2024-12-31',-10),f(C,None,'2024-12-31',20,'EUR')],'zero_liabilities':[f(C,None,'2024-12-31',20),f('LiabilitiesCurrent',None,'2024-12-31',0)],'nonnegative_OCF':[f(OCF,'2024-01-01','2024-12-31',10),f(C,None,'2024-12-31',20)],'implausible_revenue':[f(RV,'2024-01-01','2024-12-31',10000),f(RV,'2023-01-01','2023-12-31',1)],'stale_cash':[f(C,None,'2020-12-31',20)]}
for label,facts in fixtures.items():
 data=(doc('fixture-'+label,facts),)
 for function in sorted(k for k in old_functions if k.startswith('financial.')):
  spec=new.SignalSpec(signal_id=function.split('.')[-1],version=1,category='financial',description='Pure regression fixture.',execution_type=new.SignalExecutionType.DETERMINISTIC,function=function,source_types=('sec_company_facts',))
  for parameters in ({},{'max_period_age_days':True}):
   obj=spec.to_dict();obj['parameters']=parameters;variant=new.SignalSpec.from_dict(obj)
   before=evaluate(old,variant,data,AT);after=evaluate(new,variant,data,AT)
   assert digest(before)==digest(after),(label,function,parameters,before,after)
   rows.append({'case':label,'function':function,'parameters':parameters,'equal':True,'output':after})
out={'verdict':'PASS_old_new_numeric_regression_only','original_HEAD':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'original_source_sha256':hashlib.sha256(oldtext.encode()).hexdigest(),'current_source_sha256':hashlib.sha256(Path(new.__file__).read_bytes()).hexdigest(),'comparisons':len(rows),'actual_full_pool_comparisons':18,'fixture_comparisons':len(rows)-18,'rows':rows,'limits':'Full-pool arithmetic here is an isolated old/new regression only, not production selection, document-budget execution, model behavior, source admission or research gain. No Store/network/labels/SignalExecutor execution.'}
(O/'numeric-regression-results.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k!='rows'},indent=2))
