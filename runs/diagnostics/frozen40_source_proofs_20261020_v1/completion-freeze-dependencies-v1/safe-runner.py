from pathlib import Path
import sys,builtins,io,json,hashlib,socket,unittest,tempfile
from unittest.mock import patch
base=Path('/Users/l/Project/Recommandation');sys.path.insert(0,str(base))
import run_minimal_rounds as minimal
from stock_opportunity_agent.cases.label_store import LabelStore
from stock_opportunity_agent.data.raw_info import RawInfoStore
mode=sys.argv[1]
selectors=['tests.test_frozen_source_completion.FrozenSourceCompletionCodeBindingTests'] if mode.startswith('original') else ['tests.test_frozen_source_completion']
suite=unittest.defaultTestLoader.loadTestsFromNames(selectors)
def ids(s):
 for item in s:
  if isinstance(item,unittest.TestSuite):yield from ids(item)
  else:yield item.id()
expanded=list(ids(suite));assert len(expanded)==(2 if mode.startswith('original') else 14)
if mode.startswith('original'):
 import types
 import tests.test_frozen_source_completion as target_tests
 old_path=base/'runs/diagnostics/frozen40_source_proofs_20261020_v1/completion-freeze-dependencies-v1/original-consumer.py.txt'
 old=types.ModuleType('original_completion');old.__file__=str(old_path)
 exec(compile(old_path.read_text(),str(old_path),'exec'),old.__dict__)
 old.SPEC=target_tests.completion.SPEC
 target_tests.completion=old

files=[base/p for p in ('spec/scripts/diagnose_reviewed_frozen_source_completion.md','scripts/diagnose_reviewed_frozen_source_completion.py','tests/test_frozen_source_completion.py','src/stock_opportunity_agent/data/reviewed_snapshot.py')]
def bound(p):return {'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
before=[bound(p) for p in files];real_labels=str(minimal.LABELS.resolve());counts={n:0 for n in ('labels','prepare','socket','non_temp_store')}
def forbidden(name):
 def call(*args,**kwargs):counts[name]+=1;raise AssertionError('Forbidden '+name+' access')
 return call
class NoLabels:
 read_bytes=read_text=open=exists=is_file=__fspath__=forbidden('labels')
original_builtin,original_io,original_store=builtins.open,io.open,RawInfoStore.__init__
def checked(original):
 def call(file,*args,**kwargs):
  if isinstance(file,(str,Path)) and str(Path(file).absolute())==real_labels:return forbidden('labels')()
  return original(file,*args,**kwargs)
 return call
def temp_store(self,root=None,documents=()):
 if root is not None and not Path(root).resolve().is_relative_to(Path(tempfile.gettempdir()).resolve()):return forbidden('non_temp_store')()
 return original_store(self,root,documents)
phase=base/'runs/diagnostics/frozen40_source_proofs_20261020_v1/completion-freeze-dependencies-v1';log=phase/(mode+'-safe-tests.log')
with log.open('x') as stream:
 stream.write('Explicit selectors:\n'+json.dumps(selectors,indent=2)+'\nOnly temp fixtures; binding tests mock load_bundle, scope producer test mocks executor storage/view/consumption. No actual prepare/globalstore/network/model/LabelStore/fullprepare.\n');stream.flush()
 with patch.object(minimal,'LABELS',NoLabels()),patch.object(LabelStore,'load',forbidden('labels')),patch.object(minimal,'prepare',forbidden('prepare')),patch.object(minimal,'_prepare_workspace',forbidden('prepare'),create=True),patch.object(socket,'socket',forbidden('socket')),patch.object(socket,'create_connection',forbidden('socket')),patch.object(builtins,'open',checked(original_builtin)),patch.object(io,'open',checked(original_io)),patch.object(RawInfoStore,'__init__',temp_store):
  result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
after=[bound(p) for p in files];assert before==after
report={'phase':mode,'scope':'Only explicit temporary tests, no real bundle prepare/execute/GET/globalstore/LabelStore. Original expected red is the current pre-fix consumer; source preserved as original-consumer.py.txt.','selectors':selectors,'expanded_test_ids':expanded,'tripwire_calls':counts,'source_before':before,'source_after':after,'source_stable':before==after,'executed_consumer':bound(old_path) if mode.startswith('original') else bound(base/'scripts/diagnose_reviewed_frozen_source_completion.py'),'tests_run':result.testsRun,'successful':result.wasSuccessful(),'failures':len(result.failures),'errors':len(result.errors),'log':bound(log)}
p=phase/(mode+'-safe-test-bindings.json')
with p.open('x') as f:json.dump(report,f,indent=2);f.write('\n')
print(json.dumps({'result':bound(p),'log':bound(log),'tests_run':result.testsRun,'successful':result.wasSuccessful(),'failures':len(result.failures),'errors':len(result.errors),'tripwire_calls':counts,'bindings':before},indent=2))
assert not any(counts.values())
assert (not result.wasSuccessful() and len(result.failures)>0 and not result.errors) if mode.startswith('original') else result.wasSuccessful()
