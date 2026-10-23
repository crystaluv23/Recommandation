"""Run the scoped final offline suite with exact source bindings and no network."""
import hashlib
import json
from pathlib import Path
import socket
import unittest

BASE = Path(__file__).resolve().parent
REPO = BASE.parents[2]
old = json.loads((REPO / 'runs/diagnostics/icfr_native_capability_20261023_v1/associated-test-bindings-final.json').read_text())
modules = old['modules'] + ['tests.test_mining_narrative_read_evidence', 'tests.test_mining_catalog_working_context']
paths = {REPO / row['path'] for row in old['tested_files']}
paths.update(REPO / (name.replace('.', '/') + '.py') for name in modules)
paths.add(REPO / 'scripts/run_icfr_native_capability_stage.py')
paths.add(REPO / 'spec/scripts/run_icfr_native_capability_stage.md')
paths.add(REPO / 'spec/src/stock_opportunity_agent/research/signal_mining_agent.md')
paths.add(Path(__file__).resolve())
def bindings():
    return [{'path': str(p.relative_to(REPO)), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(paths)]
before = bindings()
network_calls = []
def blocked(*args, **kwargs):
    network_calls.append('attempt')
    raise AssertionError('network forbidden in final offline validation')
socket.create_connection = blocked
socket.socket.connect = blocked
socket.socket.connect_ex = blocked
suite = unittest.defaultTestLoader.loadTestsFromNames(modules)
with (BASE / 'associated-tests-final.log').open('w') as stream:
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
record = {'modules': modules, 'tested_files': before, 'unchanged': before == bindings(),
          'network_calls': len(network_calls), 'tests_run': result.testsRun,
          'success': result.wasSuccessful()}
(BASE / 'associated-test-bindings-final.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps({k:v for k,v in record.items() if k not in ('modules','tested_files')}))
raise SystemExit(0 if record['success'] and record['unchanged'] and not network_calls else 1)
