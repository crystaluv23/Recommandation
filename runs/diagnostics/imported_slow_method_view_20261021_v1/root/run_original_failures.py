"""Compare the ten connected failures against the original module in isolation."""
import hashlib
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import re
import socket
import sys
import unittest
from unittest.mock import patch

from stock_opportunity_agent.cases.label_store import LabelStore
import stock_opportunity_agent.research as package

ROOT = Path(__file__).resolve().parent
original = ROOT.parent / 'driver/original-signal_evolution.py.txt'
expected = '3f3723a2008d8e2aa1e2f30d5fff03d76e10e55595833f909a46aafe0bdd99ca'
assert hashlib.sha256(original.read_bytes()).hexdigest() == expected
name = 'stock_opportunity_agent.research.signal_evolution'
loader = importlib.machinery.SourceFileLoader(name, str(original))
spec = importlib.util.spec_from_loader(name, loader)
module = importlib.util.module_from_spec(spec)
sys.modules[name] = module
setattr(package, 'signal_evolution', module)
loader.exec_module(module)
selectors = re.findall(r'^(?:FAIL|ERROR): \w+ \(([^)]+)\)', (ROOT / 'connected-tests.log').read_text(), re.M)
assert len(selectors) == 10
suite = unittest.defaultTestLoader.loadTestsFromNames(selectors)
tripwires = {'network': 0, 'label_load': 0}
def network(*args, **kwargs):
    tripwires['network'] += 1
    raise AssertionError('Network forbidden')
def labels(*args, **kwargs):
    tripwires['label_load'] += 1
    raise AssertionError('Label loading forbidden')
with (ROOT / 'original-failed-selectors.log').open('x') as out:
    with patch.object(socket, 'socket', network), patch.object(socket, 'create_connection', network), patch.object(LabelStore, 'load', labels):
        result = unittest.TextTestRunner(stream=out, verbosity=2).run(suite)
failed = [test.id() for test, _trace in result.failures]
errors = [test.id() for test, _trace in result.errors]
record = {'original_module_sha256': expected, 'selectors': selectors, 'tests': result.testsRun,
    'failures': failed, 'errors': errors, 'passed_selectors': [s for s in selectors if s not in failed + errors],
    'tripwires': tripwires, 'scope': 'Frozen original module loaded at canonical import name; no product or test bytes rewritten.'}
with (ROOT / 'original-failed-selectors-result.json').open('x') as out:
    json.dump(record, out, indent=2)
    out.write('\n')
print(json.dumps(record))
