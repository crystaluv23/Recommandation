"""Run the changed paths and connected consumers with production tripwires."""
from contextlib import ExitStack
import json
from pathlib import Path
import socket
import unittest
from unittest.mock import patch

import run_minimal_rounds
from stock_opportunity_agent.cases.label_store import LabelStore
from stock_opportunity_agent.data.raw_info import RawInfoStore
from stock_opportunity_agent.research.evolution_transport import StructuredRoleClient

OUT = Path(__file__).resolve().parent
counts = {key: 0 for key in ('network', 'model', 'labels', 'real_store', 'fullprepare')}


def deny(kind):
    def rejected(*args, **kwargs):
        counts[kind] += 1
        raise AssertionError(kind + ' forbidden')
    return rejected


original = RawInfoStore.__init__


def store_init(self, root=None, *args, **kwargs):
    if root is not None and Path(root).resolve().is_relative_to(Path.cwd()):
        return deny('real_store')()
    return original(self, root, *args, **kwargs)


selectors = ['tests.test_signal_financials', 'tests.test_data_resolution',
             'tests.test_document_selector_identity_boundary', 'tests.test_signal_measurement_input_selection',
             'tests.test_signal_card_measurement_scope', 'tests.test_numeric_measurement_contract',
             'tests.test_seed_fixture_issuer_binding',
             'tests.test_information_plan_engine.InformationPlanRuntimeTests']
with ExitStack() as guards:
    for obj, name, kind in ((socket, 'socket', 'network'), (socket, 'create_connection', 'network'),
                            (LabelStore, '__init__', 'labels'), (LabelStore, 'load', 'labels'),
                            (run_minimal_rounds, 'prepare', 'fullprepare')):
        guards.enter_context(patch.object(obj, name, deny(kind)))
    for name in ('complete_json', 'complete_json_with_token_scores', 'complete_binary_token_with_scores'):
        guards.enter_context(patch.object(StructuredRoleClient, name, deny('model')))
    guards.enter_context(patch.object(RawInfoStore, '__init__', store_init))
    suite = unittest.defaultTestLoader.loadTestsFromNames(selectors)
    with (OUT / 'connected-final-tests.log').open('x') as log:
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
summary = {'selectors': selectors, 'tests': result.testsRun, 'success': result.wasSuccessful(),
           'failures': len(result.failures), 'errors': len(result.errors), 'tripwires': counts}
with (OUT / 'connected-final-tests.json').open('x') as handle:
    json.dump(summary, handle, indent=2)
    handle.write('\n')
print(json.dumps(summary))
raise SystemExit(not result.wasSuccessful() or any(counts.values()))
