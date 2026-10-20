"""Run associated native tests while blocking network and label-store loading."""
import sys
sys.dont_write_bytecode = True
import hashlib
import json
from pathlib import Path
import socket
import time
import unittest
from unittest.mock import patch

from stock_opportunity_agent.cases.label_store import LabelStore

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[3]
SOURCE = REPO / 'src/stock_opportunity_agent/research/signal_evolution.py'
TEST = REPO / 'tests/test_imported_slow_method_memory.py'
FILES = (SOURCE, TEST, REPO / 'tests/test_signal_evolution_engine.py', REPO / 'tests/test_imported_signal_feedback.py', REPO / 'scripts/run_reviewed_slow_feedback_stage.py', REPO / 'spec/scripts/run_reviewed_slow_feedback_stage.md', REPO / 'tests/test_reviewed_slow_feedback_stage.py', REPO / 'scripts/run_assigned_slow_target_stage.py', REPO / 'tests/test_assigned_slow_target_stage.py', REPO / 'spec/scripts/run_assigned_slow_target_stage.md', REPO / 'spec/src/stock_opportunity_agent/research/signal_evolution.md')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def execute():
    """Keep actual native consumer boundaries and reject any forbidden I/O."""
    bindings = {str(p): sha(p) for p in FILES}
    assert bindings[str(SOURCE)] == '5b4688501d929c982dbe13f6ebc464784134d6c76f454191312af69ddd64d395'
    selectors = ['tests.test_imported_slow_method_memory',
        'tests.test_signal_evolution_engine.SignalEvolutionTests',
        'tests.test_slow_reflection_source_partitions', 'tests.test_structured_reflection_roles',
        'tests.test_imported_signal_feedback', 'tests.test_signal_tracking',
        'tests.test_magnitude_slow_wiring', 'tests.test_reflection_inference_contract', 'tests.test_reviewed_slow_feedback_stage', 'tests.test_assigned_slow_target_stage']
    suite = unittest.defaultTestLoader.loadTestsFromNames(selectors)
    tripwires = {'network': 0, 'label_store_load': 0}
    def network(*args, **kwargs):
        tripwires['network'] += 1
        raise AssertionError('Network forbidden in connected test run')
    def label(*args, **kwargs):
        tripwires['label_store_load'] += 1
        raise AssertionError('Label-store loading forbidden in connected test run')
    start = time.monotonic()
    with (ROOT / 'connected-candidate-tests.log').open('x') as out:
        with patch.object(socket, 'socket', network), patch.object(socket, 'create_connection', network), patch.object(LabelStore, 'load', label):
            result = unittest.TextTestRunner(stream=out, verbosity=2).run(suite)
    after = {str(p): sha(p) for p in FILES}
    record = {'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
        'passed': result.wasSuccessful(), 'selectors': selectors, 'tripwires': tripwires,
        'seconds': time.monotonic() - start, 'bindings_before': bindings, 'bindings_after': after,
        'bytes_unchanged': bindings == after, 'scope': 'Associated synthetic/native local tests; no fresh model behavior or full S1/S2 acceptance.'}
    with (ROOT / 'connected-candidate-result.json').open('x') as out:
        json.dump(record, out, indent=2)
        out.write('\n')
    print(json.dumps(record))


if __name__ == '__main__':
    execute()
