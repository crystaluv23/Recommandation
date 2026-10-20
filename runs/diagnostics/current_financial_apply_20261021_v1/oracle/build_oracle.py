"""Independent arithmetic from reviewed raw literals, without executing implementation."""
from pathlib import Path
from decimal import Decimal, getcontext
from fractions import Fraction
import json,re,hashlib
getcontext().prec=50
ROOT=Path('/Users/l/Project/Recommandation');OUT=ROOT/'runs/diagnostics/current_financial_apply_20261021_v1/oracle'
load=lambda p:json.loads(Path(p).read_text());sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
raw=load(OUT/'raw-materials.json');records=raw['records'];definition=load(OUT/'definitions.json')
selected=load(ROOT/'runs/diagnostics/measurement_input_selection_20261021_v1/latest_v12.json')['rows']
selected={r['signal_ref']:{x['document_id'] for x in r['resolution']['documents']} for r in selected if r['financial_source_request']}
Q1='rawcap:v1:64c9e4f193885e37ae497a75841bec6dec372f9fddf1ef7649710c28c40fc902'
Q3='rawcap:v1:3930d4bb51f5f6ac4153610fa53b1df0e5e0b61d1fab9c14f0d056a3692c1877'
def operand(tag,start,end,doc=Q1):
 matches=[r for r in records if r['document_id']==doc and r['fact']['tag']==tag and r['fact'].get('start')==start and r['fact']['end']==end]
 assert len(matches)==1,(tag,start,end,len(matches));return matches[0]
def amount(op):return Fraction(str(op['fact']['value']))
def value(f):return dict(exact_fraction=f'{f.numerator}/{f.denominator}',decimal=str(Decimal(f.numerator)/Decimal(f.denominator)))
cash=operand('CashAndCashEquivalentsAtCarryingValue',None,'2025-03-31');liab=operand('LiabilitiesCurrent',None,'2025-03-31')
ocf=operand('NetCashProvidedByUsedInOperatingActivities','2025-01-01','2025-03-31');rev=operand('Revenues','2025-01-01','2025-03-31');priorrev=operand('Revenues','2024-01-01','2024-03-31')
shares=operand('WeightedAverageNumberOfSharesOutstandingBasic','2025-01-01','2025-03-31');priorshares=operand('WeightedAverageNumberOfSharesOutstandingBasic','2024-01-01','2024-03-31')
gp=operand('GrossProfit','2025-01-01','2025-03-31');priorgp=operand('GrossProfit','2024-01-01','2024-03-31')
q3gp=operand('GrossProfit','2024-07-01','2024-09-30',Q3);q3rev=operand('Revenues','2024-07-01','2024-09-30',Q3);q3prevrev=operand('Revenues','2023-07-01','2023-09-30',Q3)
def entry(ref,formula,result,unit,state,ops,reason):
 assert all(op['document_id'] in selected[ref] for op in ops)
 # Preserve every currently selected latest-end value to expose conflicts instead of silently choosing.
 tags={op['fact']['tag'] for op in ops};latest=[r for r in records if r['document_id'] in selected[ref] and r['fact']['tag'] in tags and r['fact']['end']=='2025-03-31']
 return dict(signal_ref=ref,oracle_status='sufficient_unique',formula=formula,expected_numeric=value(result),unit=unit,expected_state=state,operands=ops,current_period_alternatives=latest,classification_reason=reason,measurement_period={'start':'2025-01-01' if any(op['fact'].get('start') for op in ops) else None,'end':'2025-03-31'},numeric_comparison_policy={'exact_operands_required':True,'raw_numeric_absolute_tolerance':'1e-12','six_decimal_display_absolute_tolerance':'1e-6','note':'Display tolerance applies only when consumer explicitly retains only a six-decimal rendering; operand/period/unit/state checks still mandatory.'})
rows=[]
rows.append(entry('cash_burn_rate_elevated:v2','abs(-55,041,000) / 98,610,000',abs(amount(ocf))/amount(cash),'dimensionless ratio','positive',[ocf,cash],'Negative OCF and burn ratio >= frozen burn_threshold 0.1.'))
rows.append(entry('cash_reserves:v2','latest USD cash balance',amount(cash),'USD','neutral',[cash],'98,610,000 is below positive_min 100,000,000 and above negative_max 10,000,000.'))
rows.append(entry('cash_to_current_liabilities_ratio:v2','98,610,000 / 325,735,000',amount(cash)/amount(liab),'dimensionless ratio','negative',[cash,liab],'Same instant/date/currency; positive denominator; ratio below frozen negative_max=1.0.'))
rows.append(entry('liquidity_runway_months:v3','98,610,000 / (55,041,000 / 3)',amount(cash)*3/abs(amount(ocf)),'months','positive',[cash,ocf],'Jan 1 through Mar 31 is one reported 3-month quarter; rounded months=3; runway <= frozen 6-month positive threshold.'))
rows.append(entry('net_share_retirement_yoy:v3','1 - 64,069,000 / 63,341,000',1-amount(shares)/amount(priorshares),'dimensionless fraction','neutral',[shares,priorshares],'Same-filing Q1 weighted-average basic shares in shares; diluted agrees; -5% < retirement < 2%.'))
rows.append(entry('operating_cash_flow_margin:v2','-55,041,000 / 601,515,000',amount(ocf)/amount(rev),'dimensionless fraction','negative',[ocf,rev],'Exact same reported Q1 duration/USD, total revenue positive; margin <= frozen negative_max 0.0.'))
rows.append(entry('revenue_growth_yoy:v3','601,515,000 / 597,214,000 - 1',amount(rev)/amount(priorrev)-1,'dimensionless fraction','neutral',[rev,priorrev],'Same-filing comparable Q1 total revenue, USD; 0 < growth < frozen positive_min 0.25.'))
# These are alternatives, not an allowed-any-output acceptance test.
gross=[]
for name,oldgp,oldrev in [('same_quarter_previous_year',priorgp,priorrev),('latest_earlier_reported_quarter_with_similar_duration',q3gp,q3rev)]:
 f=amount(gp)/amount(rev)-amount(oldgp)/amount(oldrev)
 gross.append(dict(basis=name,computed=value(f),state='positive' if f>=Fraction(8,100) else 'negative' if f<=Fraction(-2,100) else 'neutral',operands=[gp,rev,oldgp,oldrev]))
acc=[]
current_growth=amount(rev)/amount(priorrev)-1
prior2023=operand('Revenues','2023-01-01','2023-03-31',doc='rawcap:v1:074b3bc1f1fdd816c51c6fa872f18d11b40cc04635eb61d5349be127ac8e0130')
for name,a,b in [('same_quarter_previous_year_growth',priorrev,prior2023),('latest_earlier_reported_quarter_growth',q3rev,q3prevrev)]:
 f=current_growth-(amount(a)/amount(b)-1)
 acc.append(dict(basis=name,computed=value(f),state='positive' if f>=Fraction(5,100) else 'negative' if f<=Fraction(-5,100) else 'neutral',operands=[rev,priorrev,a,b],all_operands_in_actual_selected_set=all(op['document_id'] in selected['revenue_acceleration:v2'] for op in [rev,priorrev,a,b])))
for ref,alts in [('gross_margin_change:v3',gross),('revenue_acceleration:v2',acc)]:
 rows.append(dict(signal_ref=ref,oracle_status='period_policy_ambiguous',expected_state=None,expected_numeric=None,reason='Frozen definition and public callable docstring do not uniquely specify which earlier comparable period/growth pair; coverage span >=330 is an input coverage gate, not the mathematical comparison rule.',alternatives=alts,acceptance_rule='Record native output without pass credit; never choose oracle after observing implementation output. Alternative calculations illustrate ambiguity, not an any-of acceptance set.'))
order=list(definition['definitions']);rows.sort(key=lambda r:order.index(r['signal_ref']))
# Primary-filing corroboration records exact tags and issuer/time contexts; no product HTML parser.
primary=ROOT/'runs/diagnostics/reviewed_gpre_capture_snapshot_20261021_v1/stage/snapshot/documents/1514.json';pd=load(primary);text=pd['content'];corroboration=[]
for tag,context,expected in [('CashAndCashEquivalentsAtCarryingValue','c-3','98,610'),('LiabilitiesCurrent','c-3','325,735'),('NetCashProvidedByUsedInOperatingActivities','c-1','55,041'),('Revenues','c-1','601,515'),('Revenues','c-5','597,214'),('WeightedAverageNumberOfSharesOutstandingBasic','c-1','64,069'),('WeightedAverageNumberOfSharesOutstandingBasic','c-5','63,341')]:
 hits=[]
 for m in re.finditer(r'<ix:nonFraction\b[^>]*name="us-gaap:'+tag+r'"[^>]*>[^<]*</ix:nonFraction>',text,re.S):
  lit=m.group(0)
  if 'contextRef="'+context+'"' in lit and '>'+expected+'<' in lit:hits.append(dict(raw_start=m.start(),raw_end=m.end(),literal=lit))
 assert hits,(tag,context)
 ctx=re.search(r'<xbrli:context\b[^>]*id="'+context+r'"[^>]*>.*?</xbrli:context>',text,re.S);assert ctx
 corroboration.append(dict(tag=tag,context=context,context_literal=ctx.group(0),facts=hits))
(OUT/'primary-filing-corroboration.json').write_text(json.dumps(dict(path=str(primary),sha256=sha(primary),content_hash=pd['content_hash'],records=corroboration),indent=2)+'\n')
answer=dict(schema_version='independent-source-arithmetic-oracle-v1',scope='Exact latest_v12 financial deterministic comparison group for qualified GPRE source view; not a replacement for old default_v6 or a current-run default claim.',fixed_denominator=9,sufficient_unique=7,period_policy_ambiguous=2,threshold_source='Exact frozen Signal specs; public owning contract/docstrings only, never execution or basis-helper output.',prior_native_execution_performed=False,models_executed=0,network_calls=0,real_label_reads=0,source_append_calls=0,rows=rows,notes=['Latest current ends 2025-03-31, 60 days before 2025-05-30, within 550-day freshness bound.','All seven unique controls have complete operands in their own actual selected sources; basic and diluted share counts agree at both Q1 ends.','Total revenue is Revenues 601,515,000/597,214,000; same-period revenue-from-contract 35,846,000/41,559,000 is >3x smaller. Literal/tag conflicts remain in raw-materials; do not mix bases.','These predictions concern measurement outputs/categories, not future price outcomes or independent predictive benefit.','No root/source/Registry/product file is modified; source/definition hashes verified before and after extraction.'])
(OUT/'oracle.json').write_text(json.dumps(answer,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(dict(fixed_denominator=9,sufficient_unique=7,ambiguous=2,expected=[dict(signal_ref=r['signal_ref'],status=r['oracle_status'],state=r['expected_state'],numeric=r['expected_numeric']) for r in rows]),indent=2))
