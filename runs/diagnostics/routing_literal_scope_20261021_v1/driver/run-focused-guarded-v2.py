"""Scoped native unit checks; all external and research execution effects blocked."""
import sys
sys.dont_write_bytecode = True

import hashlib
import json
import socket
import time
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from stock_opportunity_agent.cases.label_store import LabelStore
from stock_opportunity_agent.data.raw_info import RawInfoStore
from stock_opportunity_agent.signal_library import SignalExecutor, SignalRegistry

OUT = Path(__file__).resolve().parent
REPO = Path('/Users/l/Project/Recommandation')
NAMES = (
    'tests.test_routing_literal_scope',
    'tests.test_evolution_routing_plan_roles.RoutingResidualFacetContrastTests',
    'tests.test_evolution_routing_plan_roles.RoutingSharedObjectListContrastTests',
    'tests.test_need_dispositions',
)
PATHS = (
    'src/stock_opportunity_agent/research/evolution_research_validation.py',
    'src/stock_opportunity_agent/research/evolution_plan_roles.py',
    'spec/src/stock_opportunity_agent/research/evolution_research_validation.md',
    'tests/test_routing_literal_scope.py',
)


def bindings():
    return [{'path': str(REPO / p), 'sha256': hashlib.sha256((REPO / p).read_bytes()).hexdigest()}
            for p in PATHS]


trips = []


def forbidden(*args, **kwargs):
    trips.append('forbidden')
    raise AssertionError('Forbidden external/research effect in scoped native tests')


before = bindings()
start = time.monotonic()
with ExitStack() as stack, (OUT / 'focused-final-v2.log').open('x') as log:
    for obj, method in (
        (socket, 'socket'), (socket, 'create_connection'),
        (LabelStore, '__init__'), (LabelStore, 'load'), (LabelStore, 'record'), (LabelStore, 'ground_truth'),
        (RawInfoStore, '__init__'), (RawInfoStore, 'append'),
        (SignalExecutor, 'execute_batch'), (SignalExecutor, 'prepare_inputs'), (SignalRegistry, 'freeze'),
    ):
        stack.enter_context(patch.object(obj, method, forbidden))
    suite = unittest.defaultTestLoader.loadTestsFromNames(NAMES)
    result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
after = bindings()
summary = {'selectors': NAMES, 'tests': result.testsRun, 'failures': len(result.failures),
           'errors': len(result.errors), 'successful': result.wasSuccessful(), 'forbidden': trips,
           'source_before': before, 'source_after': after, 'sources_equal': before == after,
           'wall_seconds': time.monotonic() - start,
           'scope': 'Native offline units; existing catalog writes only to test temporary directories; no Registry.freeze, RawInfoStore or Signal calculation.'}
with (OUT / 'focused-final-v2-result.json').open('x') as out:
    json.dump(summary, out, indent=2)
print(json.dumps(summary, indent=2))
sys.exit(0 if result.wasSuccessful() and before == after and not trips else 1)
