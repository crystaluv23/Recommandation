"""Save explicit next-version specs and source-shaped generic fixtures; validate without real-source execution."""
import hashlib,json
from pathlib import Path
from unittest.mock import patch
from stock_opportunity_agent.signal_library import SignalRegistry,SignalSpec
from stock_opportunity_agent.research.signal_evolution import SignalCandidateValidator
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[3]
review=json.loads((OUT/'candidate-declared-lineage-review.json').read_text());specs=[r['next_spec'] for r in review['next_version_checks']]
for p,h in review['code_bindings'].items():assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h
byref={s['signal_id']+':v'+str(s['version']):s for s in specs}
q=[('2025-01-01','2025-03-31',150),('2024-01-01','2024-03-31',100),('2024-10-01','2024-12-31',120),('2023-10-01','2023-12-31',100)]
def facts(windows,tag='Revenues'):
 return [dict(tag=tag,start=s,end=e,value=v,unit='USD') for s,e,v in windows]
def doc(rows,name='synthetic'):
 return dict(document_id=name,source_type='sec_company_facts',published_at='2025-05-08T00:00:00+00:00',available_at='2025-05-09T00:00:00+00:00',metadata={'cik':'0000000001'},content=json.dumps(dict(schema_version='sec-company-facts-document-v1',cik='0000000001',accession_number=name,filing_date='2025-05-08',form='10-Q',facts=rows),sort_keys=True,separators=(',',':')))
def fixture(name,rows,expected='positive',extra=()):
 return dict(name=name,company_id='cik_0000000001',as_of='2025-05-30T00:00:00+00:00',expected=expected,documents=[doc(rows),*extra])
gross=facts([('2025-01-01','2025-03-31',30),('2024-01-01','2024-03-31',10)],'GrossProfit')
margin=facts(q[:2])+gross
fixtures={
 'gross_margin_change:v4':[
  fixture('quarter-yoy-margin',margin),
  fixture('negative-margin',facts(q[:2])+facts([('2025-01-01','2025-03-31',0),('2024-01-01','2024-03-31',10)],'GrossProfit'),'negative'),
  fixture('missing-current-profit',facts(q[:2])+gross[1:],'unavailable'),
  fixture('required-window-conflict',margin,'unavailable',[doc(facts([('2024-01-01','2024-03-31',101)]),'conflict')]),
  fixture('ytd-margin-same-window',facts([('2024-01-01','2024-06-30',150),('2023-01-01','2023-06-30',100)])+facts([('2024-01-01','2024-06-30',30),('2023-01-01','2023-06-30',10)],'GrossProfit'))],
 'revenue_acceleration:v3':[
  fixture('quarter-immediate-yoy',facts(q)),
  fixture('negative-acceleration',facts([('2025-01-01','2025-03-31',80),*q[1:]]),'negative'),
  fixture('missing-immediate-quarter',facts([*q[:2],q[3]]),'unavailable'),
  fixture('annual-adjacent-yoy',facts([('2024-01-01','2024-12-31',150),('2023-01-01','2023-12-31',100),('2022-01-01','2022-12-31',80)])),
  fixture('ytd-no-quarter-synthesis',facts([('2024-01-01','2024-06-30',150),('2023-01-01','2023-06-30',100)]),'unavailable'),
  fixture('required-window-conflict',facts(q),'unavailable',[doc(facts([('2024-01-01','2024-03-31',101)]),'conflict')])]
}
registry=SignalRegistry(OUT/'candidate-declared-lineage-registry/signals',candidate_root=OUT/'candidate-declared-lineage-registry/candidates');validator=SignalCandidateValidator(registry,llm_runner=None);checks=[]
with patch('socket.socket',side_effect=AssertionError('network forbidden')),patch('socket.create_connection',side_effect=AssertionError('network forbidden')):
 for ref,obj in byref.items():
  checked=validator.validate(SignalSpec.from_dict(obj),skill=None,tests=fixtures[ref]);assert checked.accepted and checked.executed_tests==len(fixtures[ref]),checked
  checks.append(dict(ref=ref,accepted=checked.accepted,reasons=list(checked.reasons),executed_tests=checked.executed_tests))
(OUT/'new-version-specs.json').write_text(json.dumps(dict(schema_version='independent-explicit-next-version-specs-v1',code_bindings=review['code_bindings'],specs=specs),indent=2)+'\n')
(OUT/'lineage-fixtures.json').write_text(json.dumps(dict(schema_version='independent-generic-lineage-fixtures-v1',by_ref=fixtures),indent=2)+'\n')
(OUT/'candidate-declared-inputs-validation.json').write_text(json.dumps(dict(status='passed',rows=checks,total_fixtures=sum(len(x) for x in fixtures.values()),real_source_Signal_execution=0,network_calls=0,models=0),indent=2)+'\n')
print(json.dumps(dict(status='passed',refs=list(byref),fixtures=sum(len(x) for x in fixtures.values()),files=['new-version-specs.json','lineage-fixtures.json'])))
