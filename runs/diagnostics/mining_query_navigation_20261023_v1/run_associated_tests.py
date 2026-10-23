"""Run the connected offline Mining suite without network or evaluation dispatch."""
import hashlib
import json
from pathlib import Path
import socket
import unittest

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
prior = json.loads((ROOT / 'runs/diagnostics/mining_reference_handles_20261023_v1/associated-test-bindings.json').read_text())
modules = prior['modules'] + ['tests.test_mining_query_navigation']
paths = {ROOT / row['path'] for row in prior['tested_files']}
paths.update(ROOT / (name.replace('.', '/') + '.py') for name in modules)
paths.add(Path(__file__).resolve())
paths.add(ROOT / 'src/stock_opportunity_agent/research/evolution_core.py')
paths.add(ROOT / 'spec/src/stock_opportunity_agent/research/evolution_core.md')
paths.add(BASE / 'prior-shared-selection.py.txt')

def bindings():
    """Record the exact code and tests before and after this offline run."""
    return [{'path': str(p.relative_to(ROOT)), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(paths)]

before = bindings()
network_calls = []
def blocked(*args, **kwargs):
    network_calls.append('attempt')
    raise AssertionError('network forbidden')
socket.create_connection = blocked
socket.socket.connect = blocked
socket.socket.connect_ex = blocked
suite = unittest.defaultTestLoader.loadTestsFromNames(modules)
with (BASE / 'associated-tests.log').open('w') as stream:
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
record = {'modules': modules, 'tested_files': before, 'unchanged': before == bindings(),
          'network_calls': len(network_calls), 'tests_run': result.testsRun, 'success': result.wasSuccessful()}
(BASE / 'associated-test-bindings.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps({k:v for k,v in record.items() if k not in ('modules','tested_files')}))
raise SystemExit(0 if record['success'] and record['unchanged'] and not network_calls else 1)
