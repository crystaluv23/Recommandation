"""Run two exact new controls against the preserved old module, in isolation."""
import importlib.util
from pathlib import Path
import sys
import unittest
sys.dont_write_bytecode = True
import tests.test_imported_slow_method_memory as tests
path = Path(__file__).parent / 'original-signal_evolution.py.txt'
spec = importlib.util.spec_from_loader('original_signal_evolution_for_imported_header', loader=None)
old = importlib.util.module_from_spec(spec); old.__file__ = str(path)
sys.modules[old.__name__] = old
exec(compile(path.read_bytes(), str(path), 'exec'), old.__dict__)
tests.native = old
tests.ImportedOwner._imported_slow_history_manifest = old.SignalEvolutionEngine._imported_slow_history_manifest
tests.ImportedOwner._imported_artifact_units = staticmethod(old.SignalEvolutionEngine._imported_artifact_units)
tests.ImportedOwner._imported_slow_feedback = old.SignalEvolutionEngine._imported_slow_feedback
suite = unittest.TestSuite(tests.ImportedSlowMethodMemoryTests(name) for name in (
    'test_large_failed_original_remains_deferred_header_complete_and_readable',
    'test_hidden_source_closure_gates_header_summary_and_entries'))
result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(0 if result.wasSuccessful() else 1)
