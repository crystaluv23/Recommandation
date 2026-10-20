"""Run only the authorized synthetic candidate-authoring test selectors."""
import ssl
import socket
import unittest
import json
import hashlib
import time
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch
from stock_opportunity_agent.cases.label_store import LabelStore

ROOT = Path(__file__).resolve().parent
NAMES = [
    'tests.test_candidate_fixture_authoring_contract',
    'tests.test_signal_evolution_engine.DualLoopTests.test_v147_materialization_modules_reuse_accepted_siblings',
    'tests.test_signal_evolution_engine.SignalEvolutionTests.test_fixture_unavailable_does_not_hide_technical_failure',
    'tests.test_signal_evolution_engine.SignalEvolutionTests.test_fixture_failure_reports_pre_execution_coverage_gap',
    'tests.test_signal_evolution_engine.SignalEvolutionTests.test_candidate_identity_guard_preserves_ticker_case',
    'tests.test_signal_evolution_engine.SignalEvolutionTests.test_update_contract_preserves_complete_retrieval_and_rejects_empty_diff',
]
FILES = [
    'src/stock_opportunity_agent/research/signal_evolution.py',
    'spec/src/stock_opportunity_agent/research/signal_evolution.md',
    'tests/test_candidate_fixture_authoring_contract.py',
    'tests/test_signal_evolution_engine.py',
]

def bindings():
    return {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in FILES}

before = bindings()
suite = unittest.defaultTestLoader.loadTestsFromNames(NAMES)
started = time.monotonic()
calls = []

def forbidden(*args, **kwargs):
    calls.append('forbidden')
    raise AssertionError('offline fixture authoring only')

with (ROOT / 'final-v5-focused-tests.log').open('x') as log, ExitStack() as guards:
    for target, method in ((socket, 'socket'), (socket, 'create_connection'),
                           (LabelStore, 'load'), (LabelStore, 'record')):
        guards.enter_context(patch.object(target, method, side_effect=forbidden))
    log.write('Selectors: ' + json.dumps(NAMES) + '\n')
    log.flush()
    result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
summary = dict(selectors=NAMES, tests_run=result.testsRun,
               failures=len(result.failures), errors=len(result.errors),
               success=result.wasSuccessful(), seconds=time.monotonic()-started,
               tripwire_calls=calls, before=before, after=bindings())
(ROOT / 'final-v5-focused-tests.json').open('x').write(json.dumps(summary, indent=2)+'\n')
print(json.dumps(summary, indent=2))
raise SystemExit(not result.wasSuccessful())
