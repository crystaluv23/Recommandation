"""One old-module selector with its genuine relative executor-source layout."""
import sys
sys.dont_write_bytecode = True
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import ssl
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from contextlib import ExitStack
from stock_opportunity_agent.cases.label_store import LabelStore
import stock_opportunity_agent.research as package

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[3]
SELECTOR = 'tests.test_imported_signal_feedback.ImportedSignalFeedbackTests.test_update_payload_and_suppression_share_committed_feedback_scope'
original = ROOT / 'original-signal_evolution.py.txt'
old_bytes = original.read_bytes()
assert hashlib.sha256(old_bytes).hexdigest() == '3f3723a2008d8e2aa1e2f30d5fff03d76e10e55595833f909a46aafe0bdd99ca'
revision = '7f3a01d9b8216e6a61d8f61969abf89c9c10a9c4'
executor_bytes = subprocess.check_output(['git', 'show', revision + ':src/stock_opportunity_agent/signal_library.py'], cwd=REPO)
assert executor_bytes == (REPO / 'src/stock_opportunity_agent/signal_library.py').read_bytes()
counts = {'network': 0, 'LabelStore': 0}
def denied(name):
    def call(*args, **kwargs):
        counts[name] += 1
        raise AssertionError(name + ' forbidden')
    return call
with tempfile.TemporaryDirectory() as raw:
    root = Path(raw).resolve() / 'src/stock_opportunity_agent'
    source = root / 'research/signal_evolution.py'; source.parent.mkdir(parents=True)
    source.write_bytes(old_bytes); (root / 'signal_library.py').write_bytes(executor_bytes)
    name = 'stock_opportunity_agent.research.signal_evolution'
    spec = importlib.util.spec_from_file_location(name, source)
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module
    setattr(package, 'signal_evolution', module); spec.loader.exec_module(module)
    suite = unittest.defaultTestLoader.loadTestsFromName(SELECTOR)
    with ExitStack() as stack:
        for owner, method, family in ((socket, 'socket', 'network'), (socket, 'create_connection', 'network'),
                (LabelStore, '__init__', 'LabelStore'), (LabelStore, 'load', 'LabelStore')):
            stack.enter_context(patch.object(owner, method, denied(family)))
        result = unittest.TextTestRunner(verbosity=2).run(suite)
record = {'scope': 'One original selector, canonical import name and correct temporary package paths. Exact original module/executor bytes; remaining imports are current unchanged dependencies. No working-tree source or test writes.',
    'selector': SELECTOR, 'revision': revision, 'original_module_sha256': hashlib.sha256(old_bytes).hexdigest(),
    'original_executor_sha256': hashlib.sha256(executor_bytes).hexdigest(), 'temporary_original_module_sha256': hashlib.sha256(old_bytes).hexdigest(),
    'tests': result.testsRun, 'failures': [{'selector': test.id(), 'traceback': trace} for test, trace in result.failures],
    'errors': [{'selector': test.id(), 'traceback': trace} for test, trace in result.errors], 'tripwires': counts}
with (ROOT / 'original-single-selector-layout-result.json').open('x') as handle:
    json.dump(record, handle, indent=2, sort_keys=True); handle.write('\n')
print(json.dumps({k: record[k] for k in ('selector', 'tests', 'tripwires')}))
raise SystemExit(0 if result.wasSuccessful() else 1)
