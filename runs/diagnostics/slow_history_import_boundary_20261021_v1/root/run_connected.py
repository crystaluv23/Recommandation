"""Run only the selected control regressions with real network and labels blocked."""
from contextlib import ExitStack
import json
from pathlib import Path
import socket
import time
import unittest
from unittest.mock import patch
import urllib.request
from stock_opportunity_agent.cases.label_store import LabelStore

root = Path(__file__).resolve().parent
tripwires = {"network": 0, "labels": 0}

def forbidden(kind):
    def fail(*args, **kwargs):
        tripwires[kind] += 1
        raise RuntimeError("forbidden real " + kind + " in control regressions")
    return fail

selectors = [
    "tests.test_historical_registry_definition_reads.HistoricalRegistryDefinitionReadsTests",
    "tests.test_evolution_control.RunControlTests",
    "tests.test_evolution_control.SlowOnlyRegistryChainTests",
]
started = time.monotonic()
with ExitStack() as stack:
    for method in ("__init__", "load"):
        stack.enter_context(patch.object(LabelStore, method, forbidden("labels")))
    stack.enter_context(patch.object(socket, "create_connection", forbidden("network")))
    stack.enter_context(patch.object(socket.socket, "connect", forbidden("network")))
    stack.enter_context(patch.object(socket.socket, "connect_ex", forbidden("network")))
    stack.enter_context(patch.object(urllib.request, "urlopen", forbidden("network")))
    suite = unittest.defaultTestLoader.loadTestsFromNames(selectors)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
receipt = {
    "selectors": selectors,
    "tests": result.testsRun,
    "failures": len(result.failures),
    "errors": len(result.errors),
    "tripwires": tripwires,
    "elapsed_seconds": time.monotonic() - started,
    "passed": result.wasSuccessful() and not any(tripwires.values()),
    "scope": "Native control tests and synthetic sources only; not actual feedback consumption.",
}
(root / "connected-result.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
print(json.dumps(receipt, sort_keys=True))
raise SystemExit(0 if receipt["passed"] else 1)
