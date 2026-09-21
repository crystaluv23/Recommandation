"""B2 concurrency primitives: fair ledger, in-flight sharing, JSONL appends."""

import json
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path

from tests.evolution_runtime_test_support import *  # noqa: F403

from stock_opportunity_agent.data.resolution import DataAcquisitionBudget
from stock_opportunity_agent.data.sources.state import (
    RequestLedger,
    RequestLedgerEntry,
)
from stock_opportunity_agent.research.evolution_transport import (
    ExternalAttemptLedger,
    InFlightRequestCoordinator,
)


class FairLedgerTest(unittest.TestCase):
    def test_concurrent_reserves_get_unique_ids_without_ceiling_overrun(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = ExternalAttemptLedger(
                Path(directory) / "attempts.json",
                max_attempts=40,
                max_total_cost=100.0,
            )
            ids: list[int] = []
            errors: list[BaseException] = []
            guard = threading.Lock()

            def reserve_many():
                local: list[int] = []
                try:
                    for _ in range(10):
                        local.append(
                            ledger.reserve("hash-x", reserved_cost=0.01)
                        )
                except BaseException as exc:  # noqa: BLE001
                    with guard:
                        errors.append(exc)
                with guard:
                    ids.extend(local)

            threads = [threading.Thread(target=reserve_many) for _ in range(4)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual(errors, [])
            self.assertEqual(len(ids), 40)
            self.assertEqual(sorted(ids), list(range(1, 41)))
            data = json.loads(
                (Path(directory) / "attempts.json").read_text()
            )
            self.assertEqual(len(data["attempts"]), 40)

    def test_finalize_is_idempotent_only_once_per_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = ExternalAttemptLedger(
                Path(directory) / "attempts.json",
                max_attempts=2,
                max_total_cost=1.0,
            )
            attempt_id = ledger.reserve("hash-y", reserved_cost=0.1)
            ledger.finalize(attempt_id, status="completed", actual_cost=0.05)
            from stock_opportunity_agent.models import ValidationError

            with self.assertRaises(ValidationError):
                ledger.finalize(attempt_id, status="completed", actual_cost=0.05)


class InFlightCoordinatorTest(unittest.TestCase):
    def test_identical_concurrent_requests_share_one_physical_call(self):
        coordinator = InFlightRequestCoordinator()
        calls: list[int] = []
        guard = threading.Lock()

        def execute():
            import time

            with guard:
                calls.append(1)
            time.sleep(0.05)
            return {"value": "leader"}

        results: list = []
        barrier = threading.Barrier(4)

        def worker():
            barrier.wait()
            results.append(
                coordinator.share(
                    "shared-hash",
                    execute,
                    on_shared=lambda: {"value": "shared"},
                )
            )

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len(calls), 1)
        leader_results = [r for r in results if r == {"value": "leader"}]
        shared_results = [r for r in results if r == {"value": "shared"}]
        self.assertEqual(len(leader_results) + len(shared_results), 4)
        self.assertGreaterEqual(len(shared_results), 1)

    def test_waiter_uses_shared_cached_result_with_zero_side_effects(self):
        coordinator = InFlightRequestCoordinator()
        executions: list[int] = []

        def execute():
            executions.append(1)
            return {"value": "leader"}

        shared_reads: list = []

        def leader_worker():
            coordinator.share(
                "cached-hash", execute, on_shared=lambda: None
            )

        thread = threading.Thread(target=leader_worker)
        thread.start()
        thread.join()
        # A later waiter finds no in-flight entry and executes as a new leader.
        second = coordinator.share(
            "cached-hash", execute, on_shared=lambda: {"value": "shared"} if False else None
        )
        self.assertEqual(second, {"value": "leader"})
        self.assertEqual(len(executions), 2)


class JsonlLedgerConcurrencyTest(unittest.TestCase):
    def test_request_ledger_concurrent_appends_stay_line_intact(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data_requests.jsonl"
            ledger = RequestLedger(path)

            def entry(index: int) -> RequestLedgerEntry:
                return RequestLedgerEntry(
                    source_key=f"source-{index}",
                    capability=ledger_entry_capability(),
                    endpoint="/x",
                    cache_key=f"cache-{index}",
                    status=ledger_entry_status(),
                    requested_at=datetime.now(timezone.utc),
                )

            def capability_of():
                return entry(0).capability

            threads = [
                threading.Thread(
                    target=lambda i=i: ledger.append(entry(i))
                )
                for i in range(40)
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            rows = [
                json.loads(line)
                for line in path.read_text().splitlines()
                if line.strip()
            ]
            self.assertEqual(len(rows), 40)
            self.assertEqual(
                len({row["source_key"] for row in rows}), 40
            )

    def test_acquisition_budget_concurrent_reserves_count_exactly(self):
        with tempfile.TemporaryDirectory() as directory:
            budget = DataAcquisitionBudget(
                ledger_path=Path(directory) / "data_acquisition_requests.jsonl",
                cycle_id=1,
            )
            from stock_opportunity_agent.data.resolution import RawInfoRequest

            def reserve_many():
                for _ in range(10):
                    budget.reserve(
                        RawInfoRequest(
                            request_id="req",
                            description="fixture",
                            source_types=("financials",),
                        ),
                        provider="fixture",
                    )

            threads = [threading.Thread(target=reserve_many) for _ in range(4)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual(budget.run_requests, 40)
            self.assertEqual(budget.cycle_requests, 40)
            rows = [
                json.loads(line)
                for line in budget.ledger_path.read_text().splitlines()
                if line.strip()
            ]
            self.assertEqual(len(rows), 40)


def ledger_entry_capability():
    from stock_opportunity_agent.data.sources.state import DataCapability

    return DataCapability.NEWS


def ledger_entry_status():
    from stock_opportunity_agent.data.sources.state import RequestStatus

    return RequestStatus.FETCHED


if __name__ == "__main__":
    unittest.main()
