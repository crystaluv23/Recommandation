PYTHONPATH=.:src:scripts /Users/l/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 - <<'PY'
import sys,subprocess,types,hashlib,unittest,socket,io,json
from unittest.mock import patch
sys.dont_write_bytecode=True
name='stock_opportunity_agent.signal_library'
raw=subprocess.check_output(['git','show','ee6de356acba873a9ebc756c1ee9a48b07f80fcd:'+name.replace('.','/').replace('stock_opportunity_agent','src/stock_opportunity_agent',1)+'.py'])
old=types.ModuleType(name);old.__file__='src/stock_opportunity_agent/signal_library.py';sys.modules[name]=old
import stock_opportunity_agent
stock_opportunity_agent.signal_library=old
exec(compile(raw,'<ee6de356 original signal_library.py>','exec'),old.__dict__)
from stock_opportunity_agent.cases.label_store import LabelStore
import run_minimal_rounds
suite=unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromName(n) for n in ('tests.test_signal_card_measurement_scope','tests.test_numeric_measurement_contract')])
log=io.StringIO()
with patch.object(socket,'socket',side_effect=AssertionError('network forbidden')),patch.object(socket,'create_connection',side_effect=AssertionError('network forbidden')),patch.object(LabelStore,'load',side_effect=AssertionError('labels forbidden')),patch.object(LabelStore,'record',side_effect=AssertionError('labels forbidden')),patch.object(run_minimal_rounds,'prepare',side_effect=AssertionError('fullprepare forbidden')):
 result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
print(log.getvalue())
print('BASELINE_SUMMARY',json.dumps({'baseline_commit':'ee6de356acba873a9ebc756c1ee9a48b07f80fcd','baseline_library_sha':hashlib.sha256(raw).hexdigest(),'tests':result.testsRun,'failures':[str(t) for t,_ in result.failures],'errors':[str(t) for t,_ in result.errors],'synthetic_only':True,'actual_stage_reentry':False,'production_LLM_or_GET_or_labels':False}))
PY
