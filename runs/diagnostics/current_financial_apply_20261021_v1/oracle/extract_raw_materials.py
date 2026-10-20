"""Read frozen definitions and selected source records without importing product code."""
from pathlib import Path
import hashlib,json,ast
ROOT=Path('/Users/l/Project/Recommandation')
OUT=ROOT/'runs/diagnostics/current_financial_apply_20261021_v1/oracle'
BASE=ROOT/'runs/diagnostics/measurement_input_selection_20261021_v1'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
load=lambda p:json.loads(Path(p).read_text())
p=load(BASE/'plan.json'); plan=dict(p); declared=plan.pop('plan_hash')
assert hashlib.sha256(json.dumps(plan,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()==declared
assert load(BASE/'result.json')['plan_hash']==declared
selection=load(BASE/'latest_v12.json'); rows=[r for r in selection['rows'] if r['financial_source_request']]
assert len(rows)==9
assert all(r['function'].startswith('financial.') for r in rows)
g=next(g for g in p['groups'] if g['name']=='latest_v12')
bindings=[]
for b in g['definition_bindings']:
 assert sha(b['path'])==b['sha256'],b['path']
 bindings.append(b)
defs={}
for b in bindings:
 if '/financial/' in b['path'] and b['path'].endswith('/spec.json'):
  d=load(b['path']);ref=d['signal_id']+':v'+str(d['version']);defs[ref]=dict(path=b['path'],sha256=b['sha256'],spec=d)
assert set(defs)=={r['signal_ref'] for r in rows}
snapshot=Path(p['reviewed_source_snapshot']['root']);m=snapshot/'reviewed_snapshot.json'
assert sha(m)==p['reviewed_source_snapshot']['manifest_sha256']
manifest=load(m); byid={d['document_id']:d for d in manifest['documents']}
ids={d['document_id'] for r in rows for d in r['resolution']['documents']}
TAGS={'CashAndCashEquivalentsAtCarryingValue','CashAndCashEquivalents','CashEquivalents','LiabilitiesCurrent','NetCashProvidedByUsedInOperatingActivities','CashFlowsFromUsedInOperatingActivities','GrossProfit','Revenues','RevenueFromContractWithCustomerExcludingAssessedTax','RevenueFromContractWithCustomerIncludingAssessedTax','SalesRevenueNet','Revenue','WeightedAverageNumberOfSharesOutstandingBasic','WeightedAverageNumberOfDilutedSharesOutstanding'}
records=[]; docs=[];decoder=json.JSONDecoder()
for did in sorted(ids):
 entry=byid[did];path=snapshot/entry['path'];assert sha(path)==entry['sha256'];d=load(path)
 assert d['document_id']==did and d['company_id']==p['case']['company_id']
 assert hashlib.sha256(d['content'].encode()).hexdigest()==d['content_hash']
 for r in rows:
  for selected in r['resolution']['documents']:
   if selected['document_id']==did:assert selected['content_hash']==d['content_hash']
 assert d['available_at']<=p['case']['prediction_time']
 meta={k:d[k] for k in ('document_id','company_id','available_at','published_at','content_hash','source_type','metadata')}
 meta.update(path=str(path),sha256=entry['sha256']);docs.append(meta)
 try:b=json.loads(d['content'])
 except json.JSONDecodeError:continue
 if not isinstance(b,dict) or b.get('schema_version')!='sec-company-facts-document-v1':continue
 assert str(b['cik']).zfill(10)==p['identity']['cik']
 assert str(d['metadata']['cik']).zfill(10)==p['identity']['cik']
 assert b['filing_date']<=p['case']['prediction_time'][:10]
 text=d['content'];key=text.index('"facts"');start=text.index('[',key)+1;i=0
 while True:
  while text[start].isspace() or text[start]==',':start+=1
  if text[start]==']':break
  fact,end=decoder.raw_decode(text,start);literal=text[start:end];assert fact==b['facts'][i]
  if fact['tag'] in TAGS:
   rec=dict(document_id=did,document_sha256=entry['sha256'],content_hash=d['content_hash'],available_at=d['available_at'],filing_date=b['filing_date'],fact_index=i,raw_start=start,raw_end=end,literal=literal,fact=fact)
   records.append(rec)
  start=end;i+=1
 assert i==len(b['facts'])
# Docstrings are public measurement definitions only: no function code/helper is evaluated.
code=ROOT/'src/stock_opportunity_agent/signal_library.py';tree=ast.parse(code.read_text());desc={}
for node in ast.walk(tree):
 if isinstance(node,ast.FunctionDef) and node.name.endswith('_signal'):
  for ref in defs:
   if node.name=='_'+ref.split(':')[0]+'_signal':desc[ref]=ast.get_docstring(node)
(OUT/'definitions.json').write_text(json.dumps(dict(group={k:v for k,v in g.items() if k!='definition_bindings'},definitions=defs,callable_docstrings=desc,docstring_source_sha256=sha(code)),ensure_ascii=False,indent=2)+'\n')
(OUT/'raw-materials.json').write_text(json.dumps(dict(documents=docs,records=records),ensure_ascii=False,indent=2)+'\n')
for d in docs:assert sha(d['path'])==d['sha256']
for b in bindings:assert sha(b['path'])==b['sha256']
assert sha(m)==p['reviewed_source_snapshot']['manifest_sha256']
bound=[dict(path=str(BASE/n),sha256=sha(BASE/n)) for n in ('plan.json','result.json','latest_v12.json')]+[dict(path=str(m),sha256=sha(m))]+bindings+[dict(path=d['path'],sha256=d['sha256']) for d in docs]
(OUT/'binding-audit.json').write_text(json.dumps(dict(status='verified_before_after',plan_hash=declared,fixed_denominator=9,selected_source_documents=len(docs),definitions_verified=len(bindings),bindings=bound,forbidden_operations='No product imports, helpers, Signal execution, models, network, label/case/split files, acquisition, append or completed-stage entry.'),indent=2)+'\n')
print(json.dumps(dict(status='complete',docs=len(docs),records=len(records),refs=list(defs))))
print('RECENT_RECORDS')
seen=set()
for r in records:
 f=r['fact'];key=(f['tag'],f.get('start'),f['end'],f['unit'],f['value'])
 if f['end']>='2024-01-01' and key not in seen:
  seen.add(key);print(json.dumps({k:f.get(k) for k in ('tag','start','end','unit','value')},sort_keys=True))
