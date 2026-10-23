"""Freeze approved financial-window expectations from original sources; stdlib only."""
import ast
from datetime import datetime
from fractions import Fraction
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
ORIGINAL = Path('/Users/l/Project/Recommandation')
SNAP = ORIGINAL / 'runs/diagnostics/reviewed_gpre_capture_snapshot_20261021_v1/stage/snapshot'
OLD = ORIGINAL / 'runs/diagnostics/current_financial_apply_20261021_v1/oracle'
bindings = {}
def read(path):
    path=Path(path); raw=path.read_bytes(); bindings[str(path)]=hashlib.sha256(raw).hexdigest(); return json.loads(raw)
def write(name, data):
    (OUT/name).write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n')
manifest=read(SNAP/'reviewed_snapshot.json'); assert len(manifest['documents'])==1780
old_manifest=read(OLD/'frozen-manifest.json')
for x in old_manifest['files']:
    path=Path(x['path']); raw=path.read_bytes(); assert len(raw)==x['bytes'] and hashlib.sha256(raw).hexdigest()==x['sha256']; bindings[str(path)]=x['sha256']
old=read(OLD/'oracle.json'); assert old['fixed_denominator']==9 and old['sufficient_unique']==7 and old['period_policy_ambiguous']==2
definitions=read(OLD/'definitions.json')
records=[]; docs=[];decoder=json.JSONDecoder()
for entry in manifest['documents']:
    path=SNAP/entry['path'];raw=path.read_bytes(); assert hashlib.sha256(raw).hexdigest()==entry['sha256']; bindings[str(path)]=entry['sha256']
    d=json.loads(raw)
    if d['company_id']!='cik_0001309402':continue
    assert datetime.fromisoformat(d['available_at'])<=datetime.fromisoformat('2025-05-30T00:00:00+00:00')
    assert hashlib.sha256(d['content'].encode()).hexdigest()==d['content_hash'];docs.append(dict(path=str(path),sha256=entry['sha256'],document_id=d['document_id'],content_hash=d['content_hash']))
    try:b=json.loads(d['content'])
    except json.JSONDecodeError:continue
    if not isinstance(b,dict) or b.get('schema_version')!='sec-company-facts-document-v1':continue
    text=d['content']; pos=text.index('[',text.index('"facts"'))+1; index=0
    while True:
        while text[pos].isspace() or text[pos]==',':pos+=1
        if text[pos]==']':break
        fact,end=decoder.raw_decode(text,pos)
        assert fact==b['facts'][index]
        if fact.get('tag') in ('Revenues','GrossProfit','RevenueFromContractWithCustomerExcludingAssessedTax'):
            records.append(dict(document_id=d['document_id'],path=str(path),sha256=entry['sha256'],content_hash=d['content_hash'],fact_index=index,raw_start=pos,raw_end=end,literal=text[pos:end],fact=fact))
        pos=end;index+=1

def pick(tag,start,end,value):
    result=[r for r in records if r['fact']['tag']==tag and r['fact'].get('start')==start and r['fact']['end']==end and r['fact']['unit']=='USD']
    assert result and {r['fact']['value'] for r in result}=={value};return result
current=pick('Revenues','2025-01-01','2025-03-31',601515000)
year_ago=pick('Revenues','2024-01-01','2024-03-31',597214000)
gross=pick('GrossProfit','2025-01-01','2025-03-31',3039000)
prior_gross=pick('GrossProfit','2024-01-01','2024-03-31',8367000)
all_ends=[r['fact']['end'] for r in records if r['fact']['tag']=='Revenues'];assert max(all_ends)=='2025-03-31'
value=Fraction(3039000,601515000)-Fraction(8367000,597214000)
missing=[]
for start,end in [('2024-10-01','2024-12-31'),('2023-10-01','2023-12-31')]:
    found=[r for r in records if r['fact']['tag']=='Revenues' and r['fact'].get('start')==start and r['fact']['end']==end]
    assert not found;missing.append(dict(start=start,end=end,tag='Revenues',found=0))
alloc=[]
for name,expected in [('gross_margin_change',4),('revenue_acceleration',3)]:
    root=ORIGINAL/'runs/cold_start/minimal_rounds_v182_integrated/signals/financial'/name
    m=read(root/'manifest.json'); inventory=[]
    for p in sorted((root/'versions').glob('v*/spec.json')):
        s=read(p);inventory.append(dict(version=s['version'],function=s['execution']['function'],path=str(p),sha256=bindings[str(p)]))
    assert max(x['version'] for x in inventory)+1==expected
    prior=definitions['definitions'][name+(':v3' if name=='gross_margin_change' else ':v2')]['spec']
    alloc.append(dict(signal_id=name,scope='original v182 registry; independent read only, no allocation/write performed',observed_manifest=m,inventory=inventory,next_unallocated_version=expected,inherited_parameters=prior['parameters']))
source=ROOT/'src/stock_opportunity_agent/signal_library.py';raw=source.read_bytes();bindings[str(source)]=hashlib.sha256(raw).hexdigest()
tree=ast.parse(raw); contracts={n.name:ast.get_docstring(n) for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('_gross_margin_change_yoy_signal','_revenue_acceleration_adjacent_signal')}
write('source-only-oracle.json',dict(schema_version='approved-financial-source-only-oracle-v1',frozen_before_new_native_executor=True,product_code_imported=False,network_calls=0,models=0,labels_read=0,source_append=0,fixed_new_denominator=2,old_financial9='immutable 6 strict pass / 1 prior-version literal failure / 2 period-policy unknown; completed stage not reentered',source_view_documents=1780,issuer_documents=len(docs),anchor=dict(start='2025-01-01',end='2025-03-31',unit='USD'),rows=[dict(signal_ref='gross_margin_change:v4',function='financial.gross_margin_change_yoy',status='sufficient_unique',expected_numeric_exact=str(value),expected_numeric_float=float(value),expected_state='neutral',formula='3039000/601515000 - 8367000/597214000',unit='fraction_difference',operands=dict(current_revenue=current,current_gross=gross,year_ago_revenue=year_ago,year_ago_gross=prior_gross),thresholds={'positive_min':.08,'negative_max':-.02}),dict(signal_ref='revenue_acceleration:v3',function='financial.revenue_acceleration_adjacent',status='unavailable_required_quarter_missing',expected_numeric=None,expected_state='unavailable',formula='(current quarter / year-ago quarter - 1) - (immediately previous quarter / its year-ago quarter - 1)',missing=missing,available_operands=dict(current=current,year_ago=year_ago),no_derivation='Annual minus nine-month arithmetic is not an explicitly reported standalone quarter; Q3 pair or annual cadence cannot replace latest Q1 anchor.',thresholds={'positive_min':.05,'negative_max':-.05})],version_allocation=alloc,callable_contracts=contracts))
write('source-only-records.json',dict(documents=docs,records=records))
write('source-only-bindings.json',bindings)
files=[]
for name in ['freeze_source_oracle.py','source-only-oracle.json','source-only-records.json','source-only-bindings.json']:
    p=OUT/name;files.append(dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size))
write('source-only-freeze.json',dict(frozen_before_new_executor=True,files=files))
print(json.dumps(dict(status='frozen',rows=2,margin=float(value),acceleration='unavailable',issuer_documents=len(docs),relevant_records=len(records),freeze_sha256=hashlib.sha256((OUT/'source-only-freeze.json').read_bytes()).hexdigest())))
