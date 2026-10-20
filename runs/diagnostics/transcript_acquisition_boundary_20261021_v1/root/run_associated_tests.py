"""Run affected modules with an actual socket network tripwire."""
import hashlib
import json
from pathlib import Path
import socket
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
NETWORK_ATTEMPTS = []

def blocked(*args, **kwargs):
    NETWORK_ATTEMPTS.append("socket network call")
    raise AssertionError("External network is forbidden in this verification")

modules = (
    "tests.test_transcript_acquisition_boundary",
    "tests.test_formal_transcript_availability",
    "tests.test_data_resolution",
    "tests.test_evolution_control",
    "tests.test_data",
    "tests.test_cold_start",
    "tests.test_provider_response_boundary",
)
source_paths = (
    "src/stock_opportunity_agent/data/acquisition.py",
    "scripts/run_cold_start_formal.py",
    "tests/test_transcript_acquisition_boundary.py",
    "tests/test_formal_transcript_availability.py",
    "tests/test_data_resolution.py",
    "tests/test_evolution_control.py",
)
bindings = {name: hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in source_paths}
suite = unittest.defaultTestLoader.loadTestsFromNames(modules)
with patch.object(socket, "create_connection", blocked), patch.object(socket.socket, "connect", blocked):
    with (ROOT / "associated-tests.log").open("w") as stream:
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
assert bindings == {name: hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in source_paths}, "Sources changed during verification"
receipt = {"modules": modules, "tests_run": result.testsRun,
    "failures": len(result.failures), "errors": len(result.errors),
    "network_attempts": len(NETWORK_ATTEMPTS), "source_bindings": bindings,
    "scope": "Local producer/consumer tests only; no proof admission, production role or full successor"}
(ROOT / "associated-result.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
print(json.dumps(receipt, ensure_ascii=False))
raise SystemExit(0 if result.wasSuccessful() and not NETWORK_ATTEMPTS else 1)
