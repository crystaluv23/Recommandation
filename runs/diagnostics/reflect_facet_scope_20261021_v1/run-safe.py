"""Local-only scoped verification; never executes a production model or stage."""
from contextlib import ExitStack
import importlib.util
import json
from pathlib import Path
import socket
import sys
import unittest
from unittest.mock import patch
from stock_opportunity_agent.cases.label_store import LabelStore
from stock_opportunity_agent.data.raw_info import RawInfoStore
import run_minimal_rounds as minimal

selectors = ['tests.test_reflect_facet_scope', 'tests.test_owned_partial_residual_mirror']
tripwires = {'socket': 0, 'labels': 0, 'source_append': 0, 'fullprepare': 0}
def blocked(kind):
    def fail(*args, **kwargs):
        tripwires[kind] += 1
        raise AssertionError('forbidden ' + kind)
    return fail
with ExitStack() as stack:
    for target, name, kind in ((socket, 'socket', 'socket'), (socket, 'create_connection', 'socket'),
        (LabelStore, 'load', 'labels'), (LabelStore, 'record', 'labels'), (LabelStore, 'ground_truth', 'labels'),
        (RawInfoStore, 'append', 'source_append'), (minimal, 'prepare', 'fullprepare')):
        stack.enter_context(patch.object(target, name, blocked(kind)))
    stack.enter_context(patch.object(minimal, 'LABELS', Path('/forbidden-unreadable-label-store')))
    if '--original-wire' in sys.argv:
        import tests.test_reflect_facet_scope as tests
        alias = 'stock_opportunity_agent.research._facet_original_plan_roles'
        spec = importlib.util.spec_from_file_location(alias, Path(__file__).with_name('original-evolution_plan_roles.py'))
        old = importlib.util.module_from_spec(spec)
        sys.modules[alias] = old
        spec.loader.exec_module(old)
        stack.enter_context(patch.object(tests, 'LLMResearchController', old.LLMResearchController))
        selectors = ['tests.test_reflect_facet_scope.ReflectFacetScopeTests.test_scope_guidance_reaches_actual_initial_request_without_answer_injection']
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromNames(selectors))
print(json.dumps({'selectors': selectors, 'tests': result.testsRun, 'success': result.wasSuccessful(), 'tripwires': tripwires}))
sys.exit(not result.wasSuccessful())
