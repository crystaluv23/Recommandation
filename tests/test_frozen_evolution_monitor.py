"""Recovery requires an actual fresh terminal error and unchanged controls."""

import json
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from scripts import monitor_frozen_evolution as module


class FrozenEvolutionMonitorTests(TestCase):
    def test_only_fresh_terminal_transport_failure_is_retryable(self):
        started = "2026-10-06T14:00:00+00:00"
        line = "stock_opportunity_agent.llm.openai.RetryableOpenAIClientError: temporary connection loss"
        attempt = {"status": "failed", "error_type": "RetryableOpenAIClientError",
            "finished_at": "2026-10-06T14:00:01+00:00"}
        self.assertTrue(module._fresh_transport_failure(1, line, attempt, started))
        for code, message, row in [
            (0, line, attempt), (-15, line, attempt),
            (1, "Timeout while observing the process", attempt),
            (1, line, {**attempt, "finished_at": "2026-10-06T13:59:59+00:00"}),
            (1, line, {**attempt, "status": "completed"}),
            (1, line, {**attempt, "error_type": "ExternalAuthorizationError"}),
            (1, "stock_opportunity_agent.llm.openai.PermanentOpenAIClientError: 402", attempt),
        ]:
            with self.subTest(code=code, message=message, row=row):
                self.assertFalse(module._fresh_transport_failure(code, message, row, started))

    def test_budget_keeps_original_ceilings_and_counts_inflight_reservations(self):
        contract = {"max_external_attempts": 3, "max_total_cost": 1}
        ledger = {"max_attempts": 3, "max_total_cost": 1,
            "attempts": [{"actual_cost": 0.2, "reserved_cost": 0.8}, {"actual_cost": None, "reserved_cost": 0.3}]}
        self.assertTrue(module._budget_available(contract, ledger))
        self.assertFalse(module._budget_available(contract, {**ledger, "attempts": [{"actual_cost": 1}]}))
        self.assertFalse(module._budget_available(contract, {**ledger, "attempts": [{"actual_cost": 0}] * 3}))
        with self.assertRaises(ValueError):
            module._budget_available(contract, {**ledger, "max_attempts": 4})
        for cost in (-1, float("nan"), True):
            with self.subTest(cost=cost), self.assertRaises(ValueError):
                module._budget_available(contract, {**ledger, "attempts": [{"actual_cost": cost}]})

    def test_existing_live_process_is_observed_without_overwriting_its_record(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = '{"pid": 123, "wrapper_pid": 124}'
            (root / "process.json").write_text(original)
            with patch.object(module.os, "kill", return_value=None), self.assertRaises(ValueError):
                module._assert_no_recorded_process(root)
            self.assertEqual((root / "process.json").read_text(), original)
            with patch.object(module.os, "kill", side_effect=ProcessLookupError):
                module._assert_no_recorded_process(root)

    def run_monitor(self, exits, *, drift=False, total_cost=10, interrupt=False, max_resumes=10):
        """Exercise the complete monitor with local scripted child terminations."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            control = Path(directory) / "control"
            root.mkdir()
            contract = {"max_external_attempts": 10, "max_total_cost": total_cost}
            module._write(root / "run_contract.json", {"contract": contract})
            ledger = {"max_attempts": 10, "max_total_cost": total_cost, "attempts": []}
            module._write(root / "attempts.json", ledger)
            children, handlers = [], {}

            class Child:
                def __init__(self, _command, **kwargs):
                    self.pid = 100 + len(children)
                    self.log = kwargs["stdout"]
                    self.done = False
                    self.terminated = False
                    children.append(self)

                def poll(self):
                    return 1 if self.done else None

                def terminate(self):
                    self.terminated = True

                def wait(self):
                    code, error_type = exits[len(children) - 1]
                    if interrupt:
                        handlers[module.signal.SIGTERM](module.signal.SIGTERM, None)
                    if error_type:
                        ledger["attempts"].append({"status": "failed", "error_type": error_type,
                            "finished_at": module._now(), "actual_cost": 1, "reserved_cost": 1})
                        module._write(root / "attempts.json", ledger)
                        self.log.write(("stock_opportunity_agent.llm.openai." + error_type + ": fixture failure\n").encode())
                    else:
                        self.log.write(b"Completed.\n")
                    self.log.flush()
                    self.done = True
                    return code

            def signal_handler(kind, handler):
                previous = handlers.get(kind)
                handlers[kind] = handler
                return previous

            identities = [("sha", "contract", "input")] * 2 + ([("sha", "drift", "input")] if drift else [])
            identity = patch.object(module, "_frozen_identity", side_effect=identities) if drift else patch.object(module, "_frozen_identity", return_value=identities[0])
            with identity, patch.object(module.subprocess, "Popen", side_effect=Child), patch.object(module.signal, "signal", side_effect=signal_handler), patch.object(module.time, "sleep") as sleep:
                if drift:
                    with self.assertRaises(ValueError):
                        module.monitor(root, root, control, retry_seconds=0)
                    code = 1
                else:
                    code = module.monitor(root, root, control, retry_seconds=0, max_resumes=max_resumes)
                return {"code": code, "child_count": len(children), "slept": sleep.call_count,
                    "terminated": any(child.terminated for child in children),
                    "exit": module._read(control / "exit.json"),
                    "process": module._read(control / "process.json"),
                    "archives": [module._read(path) for path in sorted((control / "monitor_exits").glob("*.json"))]}

    def test_fresh_network_exit_recovers_once_and_archives_both_outcomes(self):
        result = self.run_monitor([(1, "RetryableOpenAIClientError"), (0, None)])
        self.assertEqual(result["code"], 0)
        self.assertEqual(result["child_count"], 2)
        self.assertEqual(result["slept"], 1)
        self.assertEqual([row["exit_code"] for row in result["archives"]], [1, 0])
        self.assertEqual(result["process"]["status"], "stopped")

    def test_payment_budget_or_recovery_limit_never_restart(self):
        for arguments, reason in [
            ({"exits": [(1, "PermanentOpenAIClientError")]}, "child_terminal"),
            ({"exits": [(1, "RetryableOpenAIClientError")], "total_cost": 1}, "budget_exhausted"),
            ({"exits": [(1, "RetryableOpenAIClientError")], "max_resumes": 0}, "transient_recovery_limit"),
        ]:
            with self.subTest(arguments=arguments):
                result = self.run_monitor(**arguments)
                self.assertEqual(result["child_count"], 1)
                self.assertEqual(result["slept"], 0)
                self.assertEqual(result["exit"]["reason"], reason)

    def test_contract_drift_after_a_network_exit_stops_before_another_launch(self):
        result = self.run_monitor([(1, "RetryableOpenAIClientError")], drift=True)
        self.assertEqual(result["child_count"], 1)
        self.assertEqual(result["exit"]["reason"], "monitor_control_failure")

    def test_user_interrupt_stops_child_and_disables_recovery(self):
        result = self.run_monitor([(1, "RetryableOpenAIClientError")], interrupt=True)
        self.assertTrue(result["terminated"])
        self.assertEqual(result["child_count"], 1)
        self.assertEqual(result["code"], 130)
        self.assertEqual(result["exit"]["reason"], "interrupted")
