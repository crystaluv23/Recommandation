"""Bind old-revision counterexamples without modifying the shared checkout."""
from contextlib import ExitStack
import hashlib
import importlib.util
from pathlib import Path
import socket
import subprocess
import unittest
from unittest.mock import patch

import tests.test_signal_source_reading as controls

OUT = Path(__file__).resolve().parent
BASELINE_REVISION = '36673060441869c78ee5c405930bb677d76f715c'


def forbidden(*args, **kwargs):
    raise AssertionError('baseline reproduction cannot access network')


if __name__ == '__main__':
    revision = BASELINE_REVISION
    raw = subprocess.check_output(['git','show',revision+':src/stock_opportunity_agent/research/signal_source_reading.py'])
    path = OUT/'baseline-source.py'
    path.write_bytes(raw)
    spec = importlib.util.spec_from_file_location('bounded_reading_baseline', path)
    baseline = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(baseline)
    print('baseline_revision='+revision,flush=True)
    print('baseline_source_sha256='+hashlib.sha256(raw).hexdigest(),flush=True)
    with ExitStack() as guards:
        guards.enter_context(patch.object(socket,'create_connection',side_effect=forbidden))
        guards.enter_context(patch.object(socket.socket,'connect',side_effect=forbidden))
        guards.enter_context(patch.object(controls,'SignalSourceSession',baseline.SignalSourceSession))
        names = ['test_registry_loaded_immutable_spec_and_nested_source_metadata_are_isolated',
                 'test_catalog_preview_overflow_is_rejected_without_disclosure_or_mutation']
        suite = unittest.TestSuite(controls.SignalSourceReadingTests(name) for name in names)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        if result.testsRun != 2 or len(result.failures) != 1 or len(result.errors) != 1:
            raise SystemExit('unexpected baseline result')
        if 'ValidationError not raised' not in result.failures[0][1] or 'frozen Signal snapshot values cannot be mutated' not in result.errors[0][1]:
            raise SystemExit('unexpected baseline failure family')
        print('expected_baseline_reds=2; no current-product pass claimed')
