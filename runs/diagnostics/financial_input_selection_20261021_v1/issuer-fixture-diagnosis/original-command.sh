PYTHONPATH=.:src:scripts /Users/l/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 - <<'PY'
import stock_opportunity_agent
import sys,subprocess,types,hashlib,unittest,socket,io,json,re
from pathlib import Path
from unittest.mock import patch
sys.dont_write_bytecode=True
name='stock_opportunity_agent.signal_library';raw=subprocess.check_output(['git','show','ee6de356acba873a9ebc756c1ee9a48b07f80fcd:src/stock_opportunity_agent/signal_library.py'])
old=types.ModuleType(name);old.__file__='src/stock_opportunity_agent/signal_library.py';sys.modules[name]=old;stock_opportunity_agent.signal_library=old
exec(compile(raw,'<ee6de356 original signal_library.py>','exec'),old.__dict__)
from stock_opportunity_agent.cases.label_store import LabelStore
import run_minimal_rounds
text=Path('runs/diagnostics/measurement_input_selection_20261021_v1/root-final-focused-tests.log').read_text()
selectors=re.findall(r'^(?:ERROR|FAIL): \w+ \((tests\.[^)]+)\)',text,re.M)
assert len(selectors)==14
suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(n) for n in selectors)
log=io.StringIO()
with patch.object(socket,'socket',side_effect=AssertionError('network forbidden')),patch.object(socket,'create_connection',side_effect=AssertionError('network forbidden')),patch.object(LabelStore,'load',side_effect=AssertionError('labels forbidden')),patch.object(LabelStore,'record',side_effect=AssertionError('labels forbidden')),patch.object(run_minimal_rounds,'prepare',side_effect=AssertionError('fullprepare forbidden')):
 result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
# Retain per-node original exception tails; no success claimed for a mixed-module
# route that did not actually reach its prior input construction.
rows=[]
for status,items in [('error',result.errors),('failure',result.failures)]:
 for test,trace in items:
  rows.append({'node':test.id(),'status':status,'trace_tail':trace.splitlines()[-1], 'issuer_exception_in_trace':'SEC Company Facts opaque company has no explicit issuer binding' in trace})
print('HEAD_BASELINE',json.dumps({'commit':'ee6de356acba873a9ebc756c1ee9a48b07f80fcd','library_sha256':hashlib.sha256(raw).hexdigest(),'selected_old_failure_nodes':selectors,'tests_run':result.testsRun,'errors':len(result.errors),'failures':len(result.failures),'rows':rows,'actual_stage_reentry':False,'GETs_or_production_models_or_labels':0},indent=2))
PY
