"""Run only temporary imported-header and existing pure-reader controls."""
import sys
sys.dont_write_bytecode = True
from contextlib import ExitStack
from pathlib import Path
import hashlib
import json
import socket
import ssl
import unittest
from unittest.mock import patch
from stock_opportunity_agent.cases.label_store import LabelStore
from stock_opportunity_agent.data.raw_info import RawInfoStore
from stock_opportunity_agent.research.evolution_transport import StructuredRoleClient
from stock_opportunity_agent.signal_library import SignalExecutor, SignalRegistry

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[3]
paths = [REPO / 'src/stock_opportunity_agent/research/signal_evolution.py',
         REPO / 'spec/src/stock_opportunity_agent/research/signal_evolution.md',
         REPO / 'tests/test_imported_slow_method_memory.py']
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
before = {str(path): sha(path) for path in paths}
selectors = ['tests.test_imported_slow_method_memory']
selectors += ['tests.test_signal_evolution_engine.SignalEvolutionTests.' + name for name in (
    'test_slow_source_read_keeps_whole_entries_and_enforces_scope',
    'test_slow_source_read_preserves_whole_entries_beyond_item_limit',
    'test_reflection_prioritizes_terminal_evidence_within_each_cycle',
    'test_slow_method_memory_is_bounded_by_complete_recent_entries',
    'test_typed_slow_source_read_replaces_view_once_and_keeps_pending',
    'test_typed_slow_source_read_cannot_evict_required_recent_frontier',
    'test_failed_slow_memory_cannot_consume_feedback')]
suite = unittest.defaultTestLoader.loadTestsFromNames(selectors)
counts = {}
def block(name):
    def forbidden(*args, **kwargs):
        counts[name] = counts.get(name, 0) + 1
        raise AssertionError('forbidden ' + name)
    return forbidden
with ExitStack() as stack:
    for cls, name in ((LabelStore, '__init__'), (LabelStore, 'load'), (LabelStore, 'record'), (LabelStore, 'ground_truth'),
        (RawInfoStore, '__init__'), (SignalRegistry, 'freeze'), (SignalRegistry, 'audit_capabilities'),
        (SignalRegistry, 'promote_validated_batch'), (SignalExecutor, 'execute_batch'), (SignalExecutor, 'prepare_inputs'),
        (StructuredRoleClient, 'complete_json'), (socket, 'socket'), (socket, 'create_connection')):
        stack.enter_context(patch.object(cls, name, block(getattr(cls, '__name__', 'socket') + '.' + name)))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
after = {str(path): sha(path) for path in paths}
record = {'selectors': selectors, 'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
    'forbidden_calls': counts, 'before': before, 'after': after, 'bindings_unchanged': before == after}
with (ROOT / 'safe-final-result.json').open('x') as handle: json.dump(record, handle, sort_keys=True, indent=2)
raise SystemExit(0 if result.wasSuccessful() and not counts and before == after else 1)
