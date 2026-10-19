"""Bounded offline counterreview against two retained provider bodies."""
import ast, copy, hashlib, json, subprocess, tempfile
from pathlib import Path
from datetime import datetime, timezone
from stock_opportunity_agent.data.acquisition import SecCompanyFactsAdapter
from stock_opportunity_agent.data.raw_info import RawInfoDocument, RawInfoStore
from stock_opportunity_agent.data.resolution import RawInfoRequest
from stock_opportunity_agent.data.sec_company_facts import validate_company_facts_response
from stock_opportunity_agent.data import backfill
from stock_opportunity_agent.signal_library import _sec_facts, SignalExecutor, FrozenSignalRegistry, SignalSpec
R=Path(__file__).resolve().parents[4]
D=Path(__file__).parent
root=R/'runs/diagnostics/financial_source_qualification_20261020_v1'
controls=json.loads((root/'normalization-checks.json').read_text())
config=controls['actual_FTAI_same_day_case']['modern_input_config']
fp=Path(config['cache']['path']); ep=Path(controls['actual_ENB_payload_requested_as_MS']['source_cache']['path'])
def body(p):
    b=json.loads(p.read_bytes())['body']; return json.loads(b) if isinstance(b,str) else b
ftai,enb=body(fp),body(ep)
original=Path(controls['actual_FTAI_same_day_case']['original_financial']['path'])
bindings={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (fp,ep,original)}
code={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (R/'src/stock_opportunity_agent/data'/name for name in ('sec_company_facts.py','acquisition.py','backfill.py'))}
code[str(R/'src/stock_opportunity_agent/signal_library.py')]=hashlib.sha256((R/'src/stock_opportunity_agent/signal_library.py').read_bytes()).hexdigest()
class Offline:
    def __init__(self,b): self.b=b
    def company_facts(self,cik): return copy.deepcopy(self.b)
request=RawInfoRequest(request_id='independent-financial-control',description='Reported facts',source_types=('financials',),max_documents=10)
def acquire(b,t,cik='0001590364'):
    return SecCompanyFactsAdapter(Offline(b)).acquire(request,company_id='cik_'+cik,identity={'cik':cik},as_of=datetime.fromisoformat(t)).documents
def capture(fn):
    try: value=fn(); return {'rejected':False,'value':value}
    except Exception as e: return {'rejected':True,'type':type(e).__name__,'message':str(e)}
checks={}
for t in ('2025-07-31T00:00:00+00:00','2025-07-31T23:59:59+00:00','2025-08-01T00:00:00+00:00','2025-07-31T20:00:00-04:00'):
    docs=acquire(ftai,t); products=tuple(d for d in docs if d.source_type=='sec_company_facts')
    facts=_sec_facts(products,datetime.fromisoformat(t))
    checks[t]={'product_count':len(products),'parsed_facts':len(facts),'same_day_facts':sum(f.filed=='2025-07-31' for f in facts),'old_period_preserved':min(f.end for f in facts),'signature':hashlib.sha256(json.dumps([(d.document_id,d.content_hash,d.available_at.isoformat()) for d in products]).encode()).hexdigest()}
checks['wrong_issuer_producer']=capture(lambda:len(acquire(enb,'2025-09-30T00:00:00+00:00','0000895421')))
checks['strict_body_cik']={}
for v in ('not-a-cik0001590364','-1590364',1590364.0,True,0,1590364,'0001590364'):
    b=copy.copy(ftai); b['cik']=v
    checks['strict_body_cik'][repr(v)]=capture(lambda b=b:validate_company_facts_response(b,'0001590364'))
# Compare current shared path with original HEAD backfill function bytes, no original execution/store.
oldsrc=subprocess.check_output(['git','show','HEAD:src/stock_opportunity_agent/data/backfill.py'],cwd=R,text=True)
oldtree=ast.parse(oldsrc); names={'_company_fact_documents','_count_company_fact_rows','_optional_fact_date'}
ns=dict(vars(backfill)); exec(compile(ast.Module(body=[n for n in oldtree.body if isinstance(n,ast.FunctionDef) and n.name in names],type_ignores=[]),'original-backfill-functions','exec'),ns)
kwargs=dict(item=config['item'],selection=config['selection'],plan_hash='independent-valid-input-equality',retrieved_at=datetime(2026,10,20,tzinfo=timezone.utc))
a,sa=ns['_company_fact_documents'](ftai,**kwargs); b,sb=backfill._company_fact_documents(ftai,**kwargs)
checks['backfill_equivalence']={'all_document_dicts_equal':[d.to_dict() for d in a]==[d.to_dict() for d in b],'all_stats_equal':sa==sb,'documents':len(a),'facts':sa['selected_fact_row_count'],'old_function_source_sha':hashlib.sha256(ast.get_source_segment(oldsrc,next(n for n in oldtree.body if isinstance(n,ast.FunctionDef) and n.name=='_company_fact_documents')).encode()).hexdigest()}
legacy=RawInfoDocument.from_dict(json.loads(original.read_bytes()))
checks['legacy_consumer_same_day']=sum(f.filed=='2025-07-31' for f in _sec_facts((legacy,),datetime(2025,7,31,tzinfo=timezone.utc)))
wrong=RawInfoDocument.create(document_id='independent:synthetic-old-wrong-issuer-product',company_id='cik_0000895421',source_type='financials',published_at=datetime(2025,1,1,tzinfo=timezone.utc),available_at=datetime(2025,1,1,tzinfo=timezone.utc),content=json.dumps(enb,sort_keys=True,separators=(',',':')),metadata={'cik':'0000895421'})
with tempfile.TemporaryDirectory() as tmp:
    store=RawInfoStore(Path(tmp),documents=(legacy,wrong)); retimed=legacy.to_dict();retimed['available_at']='2025-08-01T00:00:00+00:00'
    checks['retimed_same_identity']={'append_return':store.append(RawInfoDocument.from_dict(retimed)),'saved_original_unchanged':store.load(legacy.document_id).to_dict()==legacy.to_dict()}
    products=[d for d in acquire(ftai,'2025-08-01T00:00:00+00:00') if d.source_type=='sec_company_facts']
    checks['new_product_ids']={'all_distinct_from_legacy':all(d.document_id!=legacy.document_id for d in products),'all_appended':all(store.append(d) for d in products)}
    restored=RawInfoStore(Path(tmp)); w=restored.load(wrong.document_id)
    checks['wrong_issuer_restored_consumer']=capture(lambda:len(_sec_facts((w,),datetime(2025,9,30,tzinfo=timezone.utc))))
    spec=SignalSpec.from_dict(json.loads((R/'runs/cold_start/minimal_rounds_v182_integrated/signals/financial/net_share_retirement_yoy/versions/v3/spec.json').read_bytes()))
    executor=SignalExecutor(FrozenSignalRegistry(0,'independent-exact-single-spec',(spec,),{}),restored)
    batch=executor.execute_batch((spec.ref,),company_id=wrong.company_id,as_of=datetime(2025,9,30,tzinfo=timezone.utc))
    result=batch.results[0]; saved=Path(tmp)/'technical-result.json';saved.write_text(json.dumps(result.to_dict(),sort_keys=True))
    checks['wrong_issuer_actual_executor']={'result':json.loads(saved.read_bytes()),'persisted_exact':json.loads(saved.read_bytes())==result.to_dict()}
assert bindings=={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in bindings}
output={'scope':'Offline deterministic issuer/time/data-product counterreview; no network/model/labels/source admission. Exact source body plus explicitly synthetic mislabeled product. No production root resumed.','source_bindings':bindings,'code_bindings':code,'checks':checks,'originals_unchanged':True}
p=D/'counterreview-result.json';p.write_text(json.dumps(output,indent=2)+'\n');print(p);print(json.dumps(checks,indent=2))
