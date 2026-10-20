"""Compare only the two named synthetic Slow positive producers with old source."""
import ssl
import socket
import importlib.util
import sys
import json
import hashlib
import unittest
from pathlib import Path
from unittest.mock import patch
from contextlib import ExitStack
from stock_opportunity_agent.cases.label_store import LabelStore
from stock_opportunity_agent.signal_library import SignalExecutor
import tests.test_signal_evolution_engine as test_module

ROOT = Path(__file__).resolve().parent
OLD = ROOT / 'original-signal_evolution.py'
name = 'stock_opportunity_agent.research._s5_prechange_signal_evolution'
spec = importlib.util.spec_from_file_location(name, OLD)
module = importlib.util.module_from_spec(spec)
sys.modules[name] = module
spec.loader.exec_module(module)
names = [
    'tests.test_signal_evolution_engine.SignalEvolutionTests.test_controller_mining_dispatch_stages_materialized_candidate',
    'tests.test_signal_evolution_engine.SignalEvolutionTests.test_signal_update_uses_one_induction_call_and_local_holdout_gate',
]
observed = []
execute = SignalExecutor.execute_batch

def observed_execute(self, *args, **kwargs):
    batch = execute(self, *args, **kwargs)
    for result in batch.results:
        if 'SEC Company Facts' in str(result.execution_error_message):
            observed.append(dict(signal_ref=result.ref, status=result.execution_status.value,
                                 error_code=result.execution_error_code,
                                 error_message=result.execution_error_message))
    return batch

def forbidden(*args, **kwargs):
    raise AssertionError('old-source synthetic controls only')

with (ROOT / 'two-old-source-failures.log').open('x') as log, ExitStack() as stack:
    for target, attr in ((socket, 'socket'), (socket, 'create_connection'),
                         (LabelStore, 'load'), (LabelStore, 'record')):
        stack.enter_context(patch.object(target, attr, side_effect=forbidden))
    stack.enter_context(patch.object(test_module, 'SignalEvolutionEngine', module.SignalEvolutionEngine))
    stack.enter_context(patch.object(test_module, 'signal_candidate_execution_contract', module.signal_candidate_execution_contract))
    stack.enter_context(patch.object(SignalExecutor, 'execute_batch', observed_execute))
    result = unittest.TextTestRunner(stream=log, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromNames(names))
summary = dict(selectors=names, old_source_path=str(OLD),
               old_source_sha256=hashlib.sha256(OLD.read_bytes()).hexdigest(),
               bound_old_engine=True, dependencies='current checkout; test engine and shared contract bound to saved HEAD source',
               tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors),
               actual_native_issuer_failures=observed)
(ROOT / 'two-old-source-failures.json').open('x').write(json.dumps(summary, indent=2)+'\n')
print(json.dumps(summary, indent=2))
