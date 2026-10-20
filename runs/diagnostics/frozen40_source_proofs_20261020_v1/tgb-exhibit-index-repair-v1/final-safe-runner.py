from pathlib import Path
import sys,builtins,io,json,hashlib,socket,unittest,tempfile
from unittest.mock import patch
base=Path('/Users/l/Project/Recommandation');sys.path.insert(0,str(base))
import run_minimal_rounds as minimal
from stock_opportunity_agent.cases.label_store import LabelStore
from stock_opportunity_agent.data.raw_info import RawInfoStore
selectors=['tests.test_reviewed_sec_exhibit_index','tests.test_reviewed_sec_response_profile.ReviewedSecResponseProfileTests.test_index_code_cell_excludes_description_cross_reference_and_ambiguous_rows','tests.test_reviewed_sec_response_profile.ReviewedSecResponseProfileTests.test_actual_retained_kgc_parent_index_layout_proves_only_its_literal_codes']
suite=unittest.defaultTestLoader.loadTestsFromNames(selectors)
def ids(s):
 for item in s:
  if isinstance(item,unittest.TestSuite):yield from ids(item)
  else:yield item.id()
expanded=list(ids(suite));assert len(expanded)==8
files=[base/p for p in ('spec/src/stock_opportunity_agent/data/reviewed_sec_response_profile.md','src/stock_opportunity_agent/data/reviewed_snapshot.py','tests/test_reviewed_sec_exhibit_index.py')]
def bound(p):return {'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
before=[bound(p) for p in files];real_labels=str(minimal.LABELS.resolve());counts={n:0 for n in ('labels','prepare','socket','non_temp_store')};temp_stores=[]
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
 if root is not None:
  p=Path(root).resolve()
  if not p.is_relative_to(Path(tempfile.gettempdir()).resolve()):return forbidden('non_temp_store')()
  temp_stores.append(str(p))
 return original_store(self,root,documents)
phase=base/'runs/diagnostics/frozen40_source_proofs_20261020_v1/tgb-exhibit-index-repair-v1'
log=phase/'final-safe-tests.log'
with log.open('x') as stream:
 stream.write('Explicit selectors:\n'+json.dumps(selectors,indent=2)+'\nOnly temporary native profile stores; no actual qualification/globalappend/LabelStore/fullprepare/network. Tripwires active.\n');stream.flush()
 with patch.object(minimal,'LABELS',NoLabels()),patch.object(LabelStore,'load',forbidden('labels')),patch.object(minimal,'prepare',forbidden('prepare')),patch.object(minimal,'_prepare_workspace',forbidden('prepare'),create=True),patch.object(socket,'socket',forbidden('socket')),patch.object(socket,'create_connection',forbidden('socket')),patch.object(builtins,'open',checked(original_builtin)),patch.object(io,'open',checked(original_io)),patch.object(RawInfoStore,'__init__',temp_store):
  result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
after=[bound(p) for p in files];assert before==after
report={'scope':'Eight explicit safe tests: six focused new tests plus existing crossreference/ambiguity and actual KGC controls. Native materialize/worker/restart only in tmp; actual TGB/HITI bodies read-only. Not actual sourcebatch qualification.','selectors':selectors,'expanded_test_ids':expanded,'tripwires':['minimal.LABELS unreadable and real labels open forbidden','LabelStore.load forbidden','minimal.prepare/_prepare_workspace forbidden','socket.socket/create_connection forbidden','RawInfoStore roots restricted to platform temporary directory'],'tripwire_calls':counts,'temporary_store_opens':len(temp_stores),'source_before':before,'source_after':after,'source_stable':before==after,'tests_run':result.testsRun,'successful':result.wasSuccessful(),'failures':len(result.failures),'errors':len(result.errors),'log':bound(log),'original_failure':bound(phase/'original-counterexample.json')}
p=phase/'final-safe-test-bindings.json'
with p.open('x') as f:json.dump(report,f,indent=2);f.write('\n')
print(json.dumps({'result':bound(p),'log':bound(log),'tests_run':result.testsRun,'successful':result.wasSuccessful(),'tripwire_calls':counts,'bindings':before},indent=2));assert result.wasSuccessful() and not any(counts.values())
