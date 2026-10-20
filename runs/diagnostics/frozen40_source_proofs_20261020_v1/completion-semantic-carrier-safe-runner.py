from pathlib import Path
import sys,builtins,io,json,hashlib,socket,unittest
from unittest.mock import patch
base=Path('/Users/l/Project/Recommandation');sys.path.insert(0,str(base))
import run_minimal_rounds as minimal
selectors=['tests.test_frozen_source_completion']
suite=unittest.defaultTestLoader.loadTestsFromNames(selectors)
def ids(s):
 for item in s:
  if isinstance(item,unittest.TestSuite):yield from ids(item)
  else:yield item.id()
expanded=list(ids(suite));assert len(expanded)==11
files=[base/p for p in ('spec/scripts/diagnose_reviewed_frozen_source_completion.md','scripts/diagnose_reviewed_frozen_source_completion.py','tests/test_frozen_source_completion.py','src/stock_opportunity_agent/data/reviewed_snapshot.py','src/stock_opportunity_agent/data/filing_orientation.py')]
def bound(p):return {'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
before=[bound(p) for p in files];real_labels=str(minimal.LABELS.resolve());counts={n:0 for n in ('labels','prepare','socket')}
def forbidden(name):
 def call(*args,**kwargs):counts[name]+=1;raise AssertionError('Forbidden '+name+' access')
 return call
class NoLabels:
 read_bytes=read_text=open=exists=is_file=__fspath__=forbidden('labels')
original_builtin,original_io=builtins.open,io.open
def checked(original):
 def call(file,*args,**kwargs):
  if isinstance(file,(str,Path)) and str(Path(file).absolute())==real_labels:return forbidden('labels')()
  return original(file,*args,**kwargs)
 return call
log=Path('/tmp/frozen-source-completion-semantic-carrier-11-safe.log')
with log.open('w') as stream:
 stream.write('Explicit selectors:\n'+json.dumps(selectors,indent=2)+'\nNo LabelStore/fullprepare/network; tripwires active.\n');stream.flush()
 with patch.object(minimal,'LABELS',NoLabels()),patch.object(minimal,'prepare',forbidden('prepare')),patch.object(minimal,'_prepare_workspace',forbidden('prepare'),create=True),patch.object(socket,'socket',forbidden('socket')),patch.object(socket,'create_connection',forbidden('socket')),patch.object(builtins,'open',checked(original_builtin)),patch.object(io,'open',checked(original_io)):
  result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
after=[bound(p) for p in files];assert before==after
report={'scope':'Only11 temporary fixture tests, including exact semantic body-carrier family repair; old9 final evidence retained. Native source proof, subset/fullsets and temp worker/restart/two18-ref consumers; no real prepare/execution/global append. Terminal failure test patches preflight to fail before any store opens.','selectors':selectors,'expanded_test_ids':expanded,'tripwires':['minimal.LABELS unreadable and real path open forbidden','minimal.prepare/_prepare_workspace forbidden','socket.socket/create_connection forbidden'],'tripwire_calls':counts,'candidate_and_dependency_before':before,'candidate_and_dependency_after':after,'source_stable':before==after,'tests_run':result.testsRun,'successful':result.wasSuccessful(),'failures':len(result.failures),'errors':len(result.errors),'log':bound(log)}
p=Path('/tmp/frozen-source-completion-semantic-carrier-11-safe-bindings.json');p.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'result':bound(p),'log':bound(log),'tests_run':result.testsRun,'successful':result.wasSuccessful(),'tripwire_calls':counts,'bindings':before},indent=2));assert result.wasSuccessful() and not any(counts.values())
