"""Run only the five supplied synthetic native controls; never call source capture."""
from pathlib import Path
import builtins
from contextlib import ExitStack
import hashlib
import importlib.util
import io
import json
import sys
import unittest
from unittest.mock import patch
sys.dont_write_bytecode=True
REPO=Path('/Users/l/Project/Recommandation');BASE=REPO/'runs/diagnostics/financial_reflect_wire_20261021_v1';HERE=BASE/'independent'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
script=BASE/'driver/synthetic-observer-controls.py';candidate=BASE/'driver/capture-native-config.py';contract=BASE/'driver/contract-v3.json'
assert sha(script)=='19cc03ba9e20e5bf71c85211fbaf3b5e7b8ef07e53245bb47376ce6197463ff3'
assert sha(candidate)=='48b107515437e877fcb837ac4890e5b94720de707e87c99fb933b39ba9382093'
assert sha(contract)=='450f3e947181ffb186a6b99b365e17a82d3b47ca9690f90d747c5bddabc4a3ba'
pre={str(p):sha(p) for p in (script,candidate,contract)}
spec=importlib.util.spec_from_file_location('independent_native_observer_controls',script);m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
assert m.capture_candidate.request_ready_observer.__code__.co_filename==str(candidate)
blocked=[]
real_prefixes=[REPO/'runs/diagnostics/current_financial_apply_20261021_v1',REPO/'runs/diagnostics/reviewed_gpre_capture_snapshot_20261021_v1',REPO/'runs/diagnostics/measurement_input_selection_20261021_v1']
def guard_open(native):
 def wrapped(file,*args,**kwargs):
  if isinstance(file,(str,bytes,Path)):
   p=Path(file).resolve()
   if any(p.is_relative_to(root) for root in real_prefixes):blocked.append(str(p));raise AssertionError('No actual source access in synthetic review')
  return native(file,*args,**kwargs)
 return wrapped
with ExitStack() as s:
 for obj,name in ((m.ExactResponseCache,'load'),(m.LocalRoleExchange,'receive'),(m.ExternalAttemptLedger,'reserve'),(m.socket,'create_connection'),(m.socket.socket,'connect'),(m.urllib.request,'urlopen'),(m.LabelStore,'__init__'),(m.SignalExecutor,'execute_batch'),(m.capture_candidate.minimal,'prepare'),(m.capture_candidate.RawInfoStore,'__init__')):
  s.enter_context(patch.object(obj,name,m.denied))
 s.enter_context(patch.object(builtins,'open',guard_open(builtins.open)))
 s.enter_context(patch.object(io,'open',guard_open(io.open)))
 result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(m.NativeCarrierBoundaryTests))
assert pre=={str(p):sha(p) for p in (script,candidate,contract)}
record={'tests_run':result.testsRun,'errors':len(result.errors),'failures':len(result.failures),'forbidden_calls':m.FORBIDDEN,'actual_source_access_attempts':blocked,'source_before_after_equal':True,'bindings':pre,'scope':'Imports definitions only, then actual native synthetic Controller/client/observer tests in TemporaryDirectory. No capture() call or actual source open. Numeric/narrative positives create temp journals; invalid carrier/correction reject before journal; cap1 rejects at native observer before cache/receive.'}
(HERE/'synthetic-observer-independent-results.json').write_text(json.dumps(record,indent=2)+'\n')
assert result.wasSuccessful() and not m.FORBIDDEN and not blocked
print(json.dumps({'passed':result.testsRun,'real_source_access':0,'forbidden':0}))
