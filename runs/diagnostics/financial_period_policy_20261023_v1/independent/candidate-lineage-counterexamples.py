"""Independent synthetic period-policy controls through real prepare/execute; no test imports."""
from dataclasses import replace
from datetime import datetime,timezone,timedelta
from fractions import Fraction
import hashlib,json,math,socket
from pathlib import Path
from unittest.mock import patch
from stock_opportunity_agent.signal_library import (SignalSpec,SignalExecutionType,SignalRetrievalPolicy,FrozenSignalRegistry,SignalExecutor,SignalResult,signal_result_model_view)
from stock_opportunity_agent.data.raw_info import RawInfoDocument,RawInfoStore
from stock_opportunity_agent.artifacts import canonical_json_hash
OUT=Path(__file__).resolve().parent
ASOF=datetime(2025,5,30,tzinfo=timezone.utc); COMPANY='cik_0000000001'
M='financial.gross_margin_change'; A='financial.revenue_acceleration'
Q=[('2025-01-01','2025-03-31',150),('2024-01-01','2024-03-31',100),('2024-10-01','2024-12-31',120),('2023-10-01','2023-12-31',100)]
def fs(windows,tag='Revenues',unit='USD'):
 return [dict(tag=tag,start=s,end=e,value=v,unit=unit) for s,e,v in windows]
def margins(windows=Q[:2]):
 return fs(windows)+fs([(s,e, v*.2 if i==0 else v*.1) for i,(s,e,v) in enumerate(windows)],'GrossProfit')
def doc(name,rows,*,filed='2025-05-08',padding=''):
 p=dict(schema_version='sec-company-facts-document-v1',cik='0000000001',accession_number=name,filing_date=filed,form='10-Q',facts=rows,readable_note=padding)
 t=datetime.fromisoformat(filed).replace(tzinfo=timezone.utc)
 return RawInfoDocument.create(document_id=name,company_id=COMPANY,source_type='sec_company_facts',published_at=t,available_at=t+timedelta(days=1),content=json.dumps(p,sort_keys=True,separators=(',',':')),metadata={'cik':'0000000001'})
def spec(function,**params):
 return SignalSpec(signal_id='independent_control',version=1,category='financial',description='Independent literal reported-window measurement.',execution_type=SignalExecutionType.DETERMINISTIC,function=function,source_types=('financials',),retrieval_policy=SignalRetrievalPolicy(query_terms=('revenue sales gross profit',)),parameters={'positive_min':.05,'negative_max':-.05,'period_policy':'same_window_yoy' if function==M else 'adjacent_yoy',**params})
def noise(n=13):
 return [doc('noise'+str(i),fs([('2022-01-01','2022-12-31',i+1)],'OtherConcept'),filed='2024-02-01',padding='revenue sales gross profit '*1000) for i in range(n)]
rows=[]
def check(name,function,documents,expected,*,params=None,state=None,required=(),period='2025-03-31',coverage=None):
 s=spec(function,**(params or {})); fr=FrozenSignalRegistry(version=1,registry_hash=canonical_json_hash([s.to_dict()]),specs=(s,),skills={}); ex=SignalExecutor(fr,RawInfoStore(documents=documents))
 r=ex.prepare_inputs((s.ref,),company_id=COMPANY,as_of=ASOF)[0]; chosen={d.document_id for d in r.documents}
 result=ex.execute_batch((s.ref,),company_id=COMPANY,as_of=ASOF).results[0]
 observed=result.to_dict(); failures=[]
 if not set(required)<=chosen:failures.append('required guard/conflict/operand documents dropped')
 if len(chosen)>10:failures.append('over document cap')
 if expected is None:
  if result.value.value!='unavailable' or result.measurement is not None:failures.append('expected unavailable without measurement')
 else:
  if result.measurement is None or not math.isclose(result.measurement.value,float(expected),abs_tol=1e-12):failures.append('wrong numeric measurement')
  if result.measurement and (result.measurement.period_end!=period or result.measurement.unit!='fraction_difference'):failures.append('wrong measurement period/unit')
 if state and result.value.value!=state:failures.append('wrong classification')
 if coverage and result.coverage.value!=coverage:failures.append('wrong plausibility coverage')
 byid={d.document_id:d for d in documents}
 for e in result.supporting_evidence:
  d=byid[e.document_id]
  if e.exact_span not in d.content:failures.append('nonliteral evidence')
  try:raw=json.loads(e.exact_span)
  except Exception:failures.append('evidence is not complete fact literal');continue
  if not {'tag','start','end','unit','value'}<=set(raw):failures.append('truncated fact literal')
 restored=SignalResult.from_dict(json.loads(json.dumps(observed)))
 if restored.to_dict()!=observed:failures.append('persistence drift')
 view=signal_result_model_view(result,classification_contract=ex.classification_contracts_for((result,)).get(result.ref))
 if expected is None and 'numeric_measurement' in str(view):failures.append('unavailable exposes numeric claim')
 rows.append(dict(name=name,function=function,expected=None if expected is None else str(expected),required=list(required),selected=sorted(chosen),failures=failures,result=observed,consumer=view))

with patch('socket.socket',side_effect=AssertionError('network forbidden')),patch('socket.create_connection',side_effect=AssertionError('network forbidden')):
 check('quarter_exact',A,[doc('q',fs(Q))],Fraction(3,10),state='positive')
 check('margin_yoy_vs_adjacent',M,[doc('m',margins()+fs([Q[2]],'GrossProfit'))],Fraction(1,10),state='positive')
 for i in range(4):check('missing_quarter_operand_'+str(i),A,[doc('q',fs([x for j,x in enumerate(Q) if i!=j]))],None,state='unavailable')
 # The missing-current row still has latest prior Q4 without its required Q3/last-year Q3, so unavailable.
 rows[-4]['comment']='If latest Q1 entirely absent, latest source anchor is Q4; a Q1 outcome cannot be claimed.'
 for tag in ('Revenues','GrossProfit'):
  for idx in (0,1):
   rr=[f for f in margins() if not (f['tag']==tag and f['start']==Q[idx][0])]
   check('missing_margin_'+tag+str(idx),M,[doc('m',rr)],None)
 annual=[('2024-01-01','2024-12-31',150),('2023-01-01','2023-12-31',100),('2022-01-01','2022-12-31',80)]
 check('annual_three_windows',A,[doc('annual',fs(annual))],Fraction(1,4),period='2024-12-31')
 check('quarter_never_falls_back_annual',A,[doc('mixed',fs(annual+Q[:2]))],None)
 check('same_end_shortest_missing',A,[doc('mixed',fs(annual+[Q[2]]))],None)
 for month,end in [(6,'2024-06-30'),(9,'2024-09-30')]:
  w=[('2024-01-01',end,150),('2023-01-01',end.replace('2024','2023'),100)]
  check('ytd_margin_'+str(month),M,[doc('ytd',margins(w))],Fraction(1,10),period=end)
  check('ytd_acceleration_'+str(month),A,[doc('ytd',fs(w))],None)
 for name,w in [('fiscal_june',[('2025-02-01','2025-04-30',150),('2024-02-01','2024-04-30',100),('2024-11-01','2025-01-31',120),('2023-11-01','2024-01-31',100)]),('leap',[('2024-12-01','2025-02-28',150),('2023-12-01','2024-02-29',100),('2024-09-01','2024-11-30',120),('2023-09-01','2023-11-30',100)])]:
  check(name,A,[doc(name,fs(w))],Fraction(3,10),period=w[0][1])
 for start,end in [('2024-12-30','2025-03-30'),('2025-01-15','2025-03-31'),('2024-01-01','2024-12-29')]:
  for fn in (A,M):check('unsupported_'+start+end+fn,fn,[doc('stub',fs([(start,end,150)]+Q[1:]))],None)
 for fn in (A,M):
  base=fs(Q) if fn==A else margins()
  check('zero_denominator_'+fn,fn,[doc('z',[{**f,'value':0} if f['tag']=='Revenues' and f['start']=='2024-01-01' else f for f in base])],None)
  check('wrong_comparator_currency_'+fn,fn,[doc('c',[{**f,'unit':'EUR'} if f['start']=='2024-01-01' else f for f in base])],None)
  check('all_eur_'+fn,fn,[doc('c',[{**f,'unit':'EUR'} for f in base])],Fraction(3,10) if fn==A else Fraction(1,10))
  check('stale_'+fn,fn,[doc('s',base)],None,params={'max_period_age_days':30})
  check('implausible_'+fn,fn,[doc('p',base)],Fraction(3,10) if fn==A else Fraction(1,10),params={'plausible_abs_max':.01},coverage='partial')
  for tag in ('Revenues',) if fn==A else ('Revenues','GrossProfit'):
   for ix in (0,1):
    f=next(f for f in base if f['tag']==tag and f['start']==Q[ix][0]);conflict=doc('conflict',[{**f,'value':f['value']+1}],filed='2025-05-09')
    check('conflict_'+tag+str(ix)+fn,fn,[*noise(),doc('base',base),conflict],None,required=('base','conflict'))
    same=doc('same',[f],filed='2025-05-09');check('duplicate_equal_'+tag+str(ix)+fn,fn,[*noise(),doc('base',base),same],Fraction(3,10) if fn==A else Fraction(1,10),required=('base',))
  old=doc('old',fs([Q[1],('2024-07-01','2024-09-30',120),('2023-07-01','2023-09-30',100),('2022-07-01','2022-09-30',80)]))
  check('latest_guard_no_older_pair_'+fn,fn,[*noise(),old,doc('latest',fs([Q[0]]))],None,required=('latest',))
 # Conflicts split across more than cap: fail closed if preserving all witnesses is impossible.
 many=[doc('c'+str(i),fs([(Q[0][0],Q[0][1],150+i)])) for i in range(12)]
 check('over_cap_conflict_witnesses',A,[*many,doc('prior',fs(Q[1:]))],None)
 # Additional asymmetric operands, exact-boundary, PIT, and ordering counterexamples.
 for idx in range(4):
  check('currency_operand_'+str(idx),A,[doc('c',[{**f,'unit':'EUR'} if i==idx else f for i,f in enumerate(fs(Q))])],None)
 for fn in (A,M):
  base=fs(Q) if fn==A else margins()
  check('exact_yoy_boundary_'+fn,fn,[doc('off',[{**f,'end':'2024-03-30'} if f['start']=='2024-01-01' else f for f in base])],None)
  check('future_current_document_'+fn,fn,[doc('future',base,filed='2025-06-01')],None)
  conflict=doc('conflict',fs([('2024-01-01','2024-03-31',101)]),filed='2025-05-09')
  for reverse in (False,True):
   docs=[doc('base',base),conflict,*noise()]
   check('reverse_conflict_'+str(reverse)+fn,fn,list(reversed(docs)) if reverse else docs,None,required=('base','conflict'))
  check('newest_unsupported_guard_'+fn,fn,[*noise(),doc('base',base),doc('lateststub',fs([('2025-04-15','2025-04-30',160)]))],None,required=('lateststub',))
 check('zero_current_revenue_acceleration',A,[doc('zero',fs([(*Q[0][:2],0),*Q[1:]]))],Fraction(-6,5),state='negative')
 check('margin_latest_quarter_must_not_take_ytd_profit',M,[doc('mixed',fs(Q[:2])+fs([('2025-01-01','2025-03-31',15),('2024-01-01','2024-03-31',10)],'GrossProfit')+fs([('2024-01-01','2024-12-31',999)],'GrossProfit'))],Fraction(0),state='neutral')
 # Ordinal thresholds are independent of changing the measurement.
 check('inherited_acceleration_negative_boundary',A,[doc('q',fs([(*Q[0][:2],135),Q[1],(*Q[2][:2],140),Q[3]]))],Fraction(-1,20),params={'positive_min':.05,'negative_max':-.05},state='negative')
 check('inherited_margin_positive_boundary',M,[doc('m',fs([(*Q[0][:2],100),Q[1]])+fs([(*Q[0][:2],18),(*Q[1][:2],10)],'GrossProfit'))],Fraction(2,25),params={'positive_min':.08,'negative_max':-.02},state='positive')
 check('threshold_positive_boundary',A,[doc('q',fs(Q))],Fraction(3,10),params={'positive_min':.3,'negative_max':-.05},state='positive')
 check('threshold_negative_boundary',A,[doc('q',fs([(*Q[0][:2],100),Q[1],Q[2],Q[3]]))],Fraction(-1,5),params={'positive_min':.05,'negative_max':-.2},state='negative')

# Candidate-only precision controls. Exact integers are retained by source literals.
with patch('socket.socket',side_effect=AssertionError('network forbidden')),patch('socket.create_connection',side_effect=AssertionError('network forbidden')):
 for d in (-1,0,1):
  # One ten-millionth either side of the inherited thresholds; no epsilon band.
  check('candidate_margin_decimal_neighbor_'+str(d),M,[doc('n',fs([(*Q[0][:2],1000000000),(*Q[1][:2],1000000000)])+fs([(*Q[0][:2],180000000+d*100),(*Q[1][:2],100000000)],'GrossProfit'))],Fraction(80000000+d*100,1000000000),params={'positive_min':.08,'negative_max':-.02},state='positive' if d>=0 else 'neutral')
  check('candidate_acceleration_decimal_neighbor_'+str(d),A,[doc('n',fs([(*Q[0][:2],1350000000+d*100),(*Q[1][:2],1000000000),(*Q[2][:2],1400000000),(*Q[3][:2],1000000000)]))],Fraction(-50000000+d*100,1000000000),state='negative' if d<=0 else 'neutral')
 check('candidate_scientific_notation',A,[doc('sci',fs([(*Q[0][:2],1.35e18),(*Q[1][:2],1e18),(*Q[2][:2],1.4e18),(*Q[3][:2],1e18)]))],Fraction(-1,20),state='negative')
 big=2**53
 for fn in (A,M):
  base=fs([(*w[:2],big) for w in Q]) if fn==A else fs([(*w[:2],big*2) for w in Q[:2]])+fs([(*w[:2],big) for w in Q[:2]],'GrossProfit')
  for tag in ('Revenues',) if fn==A else ('Revenues','GrossProfit'):
   original=next(f for f in base if f['tag']==tag and f['start']==Q[0][0])
   for delta in (0,1):
    # Revenues 2^53 and 2^53+1 collapse to the same _SecFact.value float.
    witness=doc('witness',[{**original,'value':original['value']+delta}],filed='2025-05-09')
    check('candidate_large_integer_'+fn+tag+str(delta),fn,[*noise(),doc('big',base),witness],None if delta else Fraction(0),required=('big','witness') if delta else ('big',))
 # Final float representation remains the declared measurement/classification boundary.
 check('candidate_subulp_margin_rounds_to_float_threshold',M,[doc('subulp',fs([(*Q[0][:2],10**18),(*Q[1][:2],10**18)])+fs([(*Q[0][:2],18*10**16-1),(*Q[1][:2],10**17)],'GrossProfit'))],Fraction(8*10**16-1,10**18),params={'positive_min':.08,'negative_max':-.02},state='positive')
 check('candidate_subulp_acceleration_rounds_above_float_threshold',A,[doc('subulp',fs([(*Q[0][:2],135*10**16+1),(*Q[1][:2],10**18),(*Q[2][:2],140*10**16),(*Q[3][:2],10**18)]))],Fraction(-5*10**16+1,10**18),state='neutral')

(OUT/'candidate-lineage-counterexample-results.json').write_text(json.dumps(dict(total=len(rows),passed=sum(not r['failures'] for r in rows),failed=sum(bool(r['failures']) for r in rows),rows=rows),ensure_ascii=False,indent=2)+'\n')
print(json.dumps(dict(total=len(rows),passed=sum(not r['failures'] for r in rows),failures=[dict(name=r['name'],failures=r['failures'],result=r['result']) for r in rows if r['failures']]),indent=2))
