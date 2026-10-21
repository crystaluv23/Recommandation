"""Connected offline guards; no model, HTTP, or real label loading."""
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
SOURCE = ROOT / 'src/stock_opportunity_agent/research/evolution_research_validation.py'
MODULES = (
    'tests.test_evolution_routing_plan_roles',
    'tests.test_evolution_output_validation',
    'tests.test_need_dispositions',
    'tests.test_owned_partial_residual_mirror',
    'tests.test_signal_edge_correction',
    'tests.test_signal_correction_reservation',
    'tests.test_signal_card_measurement_scope',
)
tripped = []
def forbidden(*args, **kwargs):
    tripped.append('network_or_real_labels')
    raise AssertionError('network and real LabelStore loading forbidden in offline checks')

before = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
with ExitStack() as stack:
    stack.enter_context(patch('socket.socket', side_effect=forbidden))
    stack.enter_context(patch('stock_opportunity_agent.cases.label_store.LabelStore.load', side_effect=forbidden))
    suite = unittest.defaultTestLoader.loadTestsFromNames(MODULES)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
after = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
record = {'scope': 'connected offline tests; fixtures are not production Signal execution or fresh model obedience',
          'source_sha256': before, 'source_unchanged_during_tests': before == after,
          'modules': list(MODULES), 'tests_run': result.testsRun,
          'failures': len(result.failures), 'errors': len(result.errors),
          'skips': len(result.skipped), 'tripwires': tripped,
          'passed': result.wasSuccessful() and before == after and not tripped}
(HERE / 'connected-results.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record, indent=2))
raise SystemExit(0 if record['passed'] else 1)
