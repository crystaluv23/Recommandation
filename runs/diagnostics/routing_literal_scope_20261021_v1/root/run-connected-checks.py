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
ROLE_SOURCE = ROOT / 'src/stock_opportunity_agent/research/evolution_plan_roles.py'
MODULES = (
    'tests.test_evolution_routing_plan_roles',
    'tests.test_evolution_output_validation',
    'tests.test_need_dispositions',
    'tests.test_owned_partial_residual_mirror',
    'tests.test_signal_edge_correction',
    'tests.test_signal_correction_reservation',
    'tests.test_signal_card_measurement_scope',
    'tests.test_routing_literal_scope',
    'tests.test_evolution_state_patch',
    'tests.test_reflection_correction_frontier',
    'tests.test_reflect_facet_scope',
)
tripped = []
def forbidden(*args, **kwargs):
    tripped.append('network_or_real_labels')
    raise AssertionError('network and real LabelStore loading forbidden in offline checks')

before = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
role_before = hashlib.sha256(ROLE_SOURCE.read_bytes()).hexdigest()
assert before == 'a5ba1a7a3f078f8a0338e2c55e2910605346214cad8ade17968ac8e3f6721660'
assert role_before == '06a38e29144261f8f1abad255cde1bdbdfae8eb464a2c32f871b10b66953d8f1'
with ExitStack() as stack:
    stack.enter_context(patch('socket.socket', side_effect=forbidden))
    stack.enter_context(patch('stock_opportunity_agent.cases.label_store.LabelStore.load', side_effect=forbidden))
    suite = unittest.defaultTestLoader.loadTestsFromNames(MODULES)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
after = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
roles_unchanged = role_before == hashlib.sha256(ROLE_SOURCE.read_bytes()).hexdigest()
record = {'scope': 'connected offline tests; fixtures are not production Signal execution or fresh model obedience',
          'source_sha256': before, 'role_sha256': role_before, 'roles_unchanged': roles_unchanged, 'source_unchanged_during_tests': before == after,
          'modules': list(MODULES), 'tests_run': result.testsRun,
          'failures': len(result.failures), 'errors': len(result.errors),
          'skips': len(result.skipped), 'tripwires': tripped,
          'passed': result.wasSuccessful() and before == after and roles_unchanged and not tripped}
(HERE / 'connected-results.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record, indent=2))
raise SystemExit(0 if record['passed'] else 1)
