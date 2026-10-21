#!/usr/bin/env python3
"""Parser-only controls with Signal calculation, fresh freeze, network and labels forbidden."""
from contextlib import ExitStack
import importlib.util
import json
from pathlib import Path
import socket
import sys
import unittest
from unittest.mock import patch

import tests.test_evolution_routing_plan_roles as tests
import stock_opportunity_agent.research.evolution_plan_roles as roles
from stock_opportunity_agent.cases.label_store import LabelStore
from stock_opportunity_agent.signal_library import SignalExecutor, SignalRegistry
from stock_opportunity_agent.artifacts import atomic_write_json
from diagnose_executed_answer_scope import binding

HERE = Path(__file__).resolve().parent
old = '--old' in sys.argv
name = 'focused-original' if old else 'focused-candidate'
output = HERE / (name + '-result.json')
if output.exists():
    raise RuntimeError('focused result already exists')
module = None
if old:
    source = HERE / 'original-evolution_research_validation.py.txt'
    spec = importlib.util.spec_from_loader('stock_opportunity_agent.research._saved_routing_validation', loader=None)
    module = importlib.util.module_from_spec(spec)
    module.__file__ = str(source)
    sys.modules[spec.name] = module
    exec(compile(source.read_text(), str(source), 'exec'), module.__dict__)

forbidden = []
def reject(*args, **kwargs):
    forbidden.append('forbidden effect')
    raise AssertionError('no Signal/freeze/network/label operation in parser controls')

suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(cls) for cls in
    (tests.RoutingResidualFacetContrastTests, tests.RoutingSharedObjectListContrastTests))
with ExitStack() as stack:
    for owner, method in ((socket,'socket'),(socket,'create_connection'),(LabelStore,'__init__'),
            (LabelStore,'load'),(LabelStore,'record'),(LabelStore,'ground_truth'),
            (SignalExecutor,'execute_batch'),(SignalRegistry,'freeze')):
        stack.enter_context(patch.object(owner, method, reject))
    if module is not None:
        stack.enter_context(patch.object(tests, '_shared_distinctive_phrase', module._shared_distinctive_phrase))
        stack.enter_context(patch.object(roles, '_shared_distinctive_phrase', module._shared_distinctive_phrase))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
atomic_write_json(output, {'scope':'saved helper vs unchanged native routing parser; no fresh model',
    'old_helper':old, 'tests':result.testsRun, 'failures':[(str(t),trace) for t,trace in result.failures],
    'errors':[(str(t),trace) for t,trace in result.errors], 'forbidden_calls':forbidden,
    'old_source':binding(HERE/'original-evolution_research_validation.py.txt'),
    'current_source':binding(Path('src/stock_opportunity_agent/research/evolution_research_validation.py')),
    'current_test':binding(Path(tests.__file__)), 'passed':result.wasSuccessful()})
sys.exit(0 if result.wasSuccessful() else 1)
