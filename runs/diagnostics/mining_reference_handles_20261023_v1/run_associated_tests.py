"""Run the connected offline Mining suite without network or evaluation dispatch."""
import hashlib
import json
from pathlib import Path
import socket
import unittest

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
prior = json.loads((ROOT / 'runs/diagnostics/mining_catalog_working_context_20261023_v1/associated-test-bindings-final.json').read_text())
modules = prior['modules'] + ['tests.test_mining_reference_handles']
paths = {ROOT / row['path'] for row in prior['tested_files']}
paths.update(ROOT / (name.replace('.', '/') + '.py') for name in modules)
paths.add(Path(__file__).resolve())

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
