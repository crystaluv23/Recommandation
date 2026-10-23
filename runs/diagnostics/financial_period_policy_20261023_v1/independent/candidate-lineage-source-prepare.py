"""Real-source bounded preparation only, using actual next-version ID plus policy."""
from datetime import datetime
import hashlib,json
from pathlib import Path
from unittest.mock import patch
from stock_opportunity_agent import signal_library as lib
from stock_opportunity_agent.data.raw_info import RawInfoDocument,RawInfoStore
from stock_opportunity_agent.artifacts import canonical_json_hash
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[3]
review=json.loads((OUT/'candidate-lineage-review.json').read_text())
for p,h in review['code_bindings'].items():assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h
specs=[lib.SignalSpec.from_dict(row['next_spec']) for row in review['next_version_checks']]
materials=json.loads((OUT/'source-only-records.json').read_text());docs=[]
for d in materials['documents']:
 p=Path(d['path']);assert hashlib.sha256(p.read_bytes()).hexdigest()==d['sha256'];docs.append(RawInfoDocument.from_dict(json.loads(p.read_text())))
snapshot=lib.FrozenSignalRegistry(version=1,registry_hash=canonical_json_hash([s.to_dict() for s in specs]),specs=tuple(specs),skills={})
ex=lib.SignalExecutor(snapshot,RawInfoStore(documents=docs));asof=datetime.fromisoformat('2025-05-30T00:00:00+00:00');rows=[]
with patch('socket.socket',side_effect=AssertionError('network forbidden')),patch('socket.create_connection',side_effect=AssertionError('network forbidden')):
 for s in specs:
  resolution=ex.prepare_inputs((s.ref,),company_id='cik_0001309402',as_of=asof,identity={'cik':'0001309402','ticker':'GPRE'})[0]
  chosen={d.document_id for d in resolution.documents};assert len(chosen)<=10
  helper=ex.deterministic_functions[s.function].__signal_input_facts__
  full=helper(s,tuple(docs),asof);selected=helper(s,tuple(d for d in docs if d.document_id in chosen),asof)
  assert lib._input_basis_identity(full)==lib._input_basis_identity(selected)
  if s.signal_id=='gross_margin_change':assert selected.unavailable_reason is None and len(selected.facts)==4
  else:assert selected.unavailable_reason and 'unavailable' in selected.unavailable_reason
  scope=lib.signal_measurement_scope(s,deterministic_functions=ex.deterministic_functions);assert scope['execution']['configured_parameters']['period_policy']==s.parameters['period_policy']
  rows.append(dict(ref=s.ref,spec=s.to_dict(),resolution=resolution.to_dict(),scope=scope,basis_equal_full_pool=True,selected_basis=[dict(tag=f.tag,start=f.start,end=f.end,unit=f.unit,document_id=f.document.document_id,exact_span=f.exact_span) for f in selected.facts],unavailable_reason=selected.unavailable_reason))
(OUT/'candidate-lineage-source-prepare.json').write_text(json.dumps(dict(status='passed',rows=rows,code_bindings=review['code_bindings'],real_source_execute_calls=0,real_prepare_calls=2,models=0,network_calls=0),indent=2)+'\n')
print(json.dumps(dict(status='passed',real_prepare_calls=2,selected_counts=[len(r['resolution']['documents']) for r in rows],real_source_execute_calls=0)))
