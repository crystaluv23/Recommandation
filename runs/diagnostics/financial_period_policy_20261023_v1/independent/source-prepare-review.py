"""Read-only real source preparation and AST review, without real-source Signal execution."""
import ast,hashlib,json,subprocess
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from stock_opportunity_agent.data.raw_info import RawInfoDocument,RawInfoStore
from stock_opportunity_agent.signal_library import SignalSpec,FrozenSignalRegistry,SignalExecutor,signal_measurement_scope
from stock_opportunity_agent.artifacts import canonical_json_hash
ROOT=Path(__file__).resolve().parents[4];OUT=Path(__file__).resolve().parent
oracle=json.loads((OUT/'source-only-oracle.json').read_text()); material=json.loads((OUT/'source-only-records.json').read_text())
definitions=json.loads(Path('/Users/l/Project/Recommandation/runs/diagnostics/current_financial_apply_20261021_v1/oracle/definitions.json').read_text())
specs=[]
for row in oracle['rows']:
 oldref='gross_margin_change:v3' if row['signal_ref'].startswith('gross') else 'revenue_acceleration:v2'
 obj=json.loads(json.dumps(definitions['definitions'][oldref]['spec']));obj['version']=int(row['signal_ref'].rsplit(':v',1)[1]);obj['execution']['function']=row['function'];specs.append(SignalSpec.from_dict(obj))
docs=tuple(RawInfoDocument.from_dict(json.loads(Path(d['path']).read_text())) for d in material['documents'])
fr=FrozenSignalRegistry(version=1,registry_hash=canonical_json_hash([s.to_dict() for s in specs]),specs=tuple(specs),skills={})
ex=SignalExecutor(fr,RawInfoStore(documents=docs));results=[]
with patch('socket.socket',side_effect=AssertionError('network forbidden')),patch('socket.create_connection',side_effect=AssertionError('network forbidden')):
 for s in specs:
  resolution=ex.prepare_inputs((s.ref,),company_id='cik_0001309402',as_of=datetime.fromisoformat('2025-05-30T00:00:00+00:00'),identity={'cik':'0001309402','ticker':'GPRE'})[0]
  chosen={r.document_id for r in resolution.documents};assert len(chosen)<=10
  fn=ex.deterministic_functions[s.function]
  scope=signal_measurement_scope(s,deterministic_functions=ex.deterministic_functions)
  assert callable(getattr(fn,'__signal_input_facts__',None)) and scope['execution']['callable_status']=='registered'
  basis=getattr(fn,'__signal_input_facts__')(s,tuple(d for d in docs if d.document_id in chosen),datetime.fromisoformat('2025-05-30T00:00:00+00:00'))
  if s.signal_id=='gross_margin_change':assert basis.unavailable_reason is None and len(basis.facts)==4
  else:assert basis.unavailable_reason is not None and 'unavailable' in basis.unavailable_reason
  results.append(dict(ref=s.ref,resolution=resolution.to_dict(),scope=scope,selected_basis=[dict(tag=f.tag,start=f.start,end=f.end,unit=f.unit,document_id=f.document.document_id,exact_span=f.exact_span) for f in basis.facts],unavailable_reason=basis.unavailable_reason))
code=ROOT/'src/stock_opportunity_agent/signal_library.py';current=ast.parse(code.read_text());base=ast.parse(subprocess.check_output(['git','show','ba309796:src/stock_opportunity_agent/signal_library.py'],cwd=ROOT,text=True))
names=['_revenue_acceleration_signal','_gross_margin_change_signal','_revenue_acceleration_input_facts','_gross_margin_input_facts']
old={n.name:ast.dump(n,include_attributes=False) for n in base.body if isinstance(n,ast.FunctionDef) and n.name in names};new={n.name:ast.dump(n,include_attributes=False) for n in current.body if isinstance(n,ast.FunctionDef) and n.name in names};assert old==new
report=dict(real_source_execute_calls=0,real_prepare_calls=2,models=0,network_calls=0,old_functions_AST_unchanged=names,code_sha256=hashlib.sha256(code.read_bytes()).hexdigest(),rows=results)
(OUT/'source-prepare-review.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(status='passed',prepare_calls=2,real_execute_calls=0,old_callables_unchanged=True,selected_counts=[len(r['resolution']['documents']) for r in results])))
