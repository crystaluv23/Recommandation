"""Run the affected Mining/Signal chain offline and bind the tested files."""
import json
from pathlib import Path
import socket
from unittest import TestLoader, TextTestRunner
from unittest.mock import patch

from diagnose_executed_answer_scope import binding

BASE = Path(__file__).resolve().parent
modules = json.loads(Path("runs/diagnostics/mining_taxonomy_consumer_20261023_v1/final-test-bindings.json").read_text())["modules"]
modules.append("tests.test_mining_comparison_progress")
paths = [*sorted(Path("src").rglob("*.py")),
    *[Path(module.replace(".", "/") + ".py") for module in modules],
    Path("spec/src/stock_opportunity_agent/research/signal_mining_agent.md"), Path(__file__)]
before = [binding(path) for path in paths]
network_calls = []


def blocked(*args, **kwargs):
    """Fail any unexpected real network transport rather than send it."""
    network_calls.append("blocked_network_attempt")
    raise AssertionError("offline associated-test network tripwire")


with (BASE / "associated-tests.log").open("x") as stream:
    with patch.object(socket, "create_connection", blocked), patch.object(socket.socket, "connect", blocked), \
            patch.object(socket.socket, "connect_ex", blocked):
        result = TextTestRunner(stream=stream, verbosity=2).run(TestLoader().loadTestsFromNames(modules))
after = [binding(path) for path in paths]
assert before == after
record = {"modules": modules, "tested_files": before, "unchanged_after_tests": True,
    "tests_run": result.testsRun, "success": result.wasSuccessful(), "network_calls": len(network_calls)}
with (BASE / "associated-test-bindings.json").open("x") as stream:
    json.dump(record, stream, ensure_ascii=False, indent=2)
print(json.dumps({k: record[k] for k in ("tests_run", "success", "network_calls", "unchanged_after_tests")}))
if not result.wasSuccessful() or network_calls:
    raise SystemExit(1)
