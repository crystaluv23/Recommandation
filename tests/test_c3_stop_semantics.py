"""C3 stop semantics: SIGINT cancel flag, admission boundaries, bounded waits."""

import os
import signal
import tempfile
import threading
import time
import unittest
from pathlib import Path

from tests.scheme_evolution_test_support import *  # noqa: F403

from stock_opportunity_agent.research.plan_evolution import (
    EvaluationCancelled,
    PlanEvolutionEngine,
    install_stop_handler,
)


class _CancellingEvaluator:
    """Sets the cancel flag while evaluating its first candidate."""

    def __init__(self, cancel: threading.Event) -> None:
        self.cancel = cancel
        self.calls = 0

    def evaluate(self, plan, cases, signal_registry):
        self.calls += 1
        self.cancel.set()
        return SyntheticPlanEvaluator().evaluate(plan, cases, signal_registry)


class _SleepingEvaluator:
    def __init__(self, seconds: float) -> None:
        self.seconds = seconds

    def evaluate(self, plan, cases, signal_registry):
        time.sleep(self.seconds)
        return SyntheticPlanEvaluator().evaluate(plan, cases, signal_registry)


def _engine(root, *, factory, cancel, parallel=1, wait=3600.0):
    registry = SignalRegistry(root / "signals")
    registry.install_catalog(SEED_CATALOG)
    workspace = EvolutionWorkspace(root / "workspace")
    return PlanEvolutionEngine(
        archive=workspace.restore_archive(),
        meta_memory=workspace.restore_meta(),
        signal_registry=registry,
        evaluator=SyntheticPlanEvaluator(),
        proposer=CountingProposer(),
        critic=SimpleCritic(),
        round_reflector=SimpleRoundReflector(),
        workspace=workspace,
        seed_plans=(default_information_plan(),),
        candidates_per_round=2,
        evaluator_factory=factory,
        max_parallel_plans=parallel,
        cancel_event=cancel,
        worker_wait_timeout_seconds=wait,
    )


def _run(engine, root):
    engine.run_round(
        round_id=1,
        validation_cases=make_evaluation_pool(),
        anchor_cases=make_anchor_pool(),
        signal_snapshot=SignalRegistry(root / "signals").freeze(),
    )


class StopHandlerTest(unittest.TestCase):
    def test_sigint_sets_flag_without_keyboard_interrupt(self):
        cancel = threading.Event()
        restore = install_stop_handler(cancel)
        try:
            os.kill(os.getpid(), signal.SIGINT)
            # The handler must consume the signal: no exception escapes and
            # the flag is marked.
            self.assertTrue(cancel.is_set())
        finally:
            restore()
        self.assertEqual(signal.getsignal(signal.SIGINT), signal.default_int_handler)

    def test_restore_reinstates_previous_handler(self):
        cancel = threading.Event()
        marker = signal.getsignal(signal.SIGINT)
        restore = install_stop_handler(cancel)
        restore()
        self.assertEqual(signal.getsignal(signal.SIGINT), marker)


class StopBoundaryTest(unittest.TestCase):
    def test_parallel_stop_during_candidate_one_finishes_it_and_blocks_two(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cancel = threading.Event()
            cancelling = _CancellingEvaluator(cancel)
            engine = _engine(
                root,
                factory=lambda: cancelling,
                cancel=cancel,
                parallel=2,
            )
            with self.assertRaises(EvaluationCancelled):
                _run(engine, root)
            workspace = EvolutionWorkspace(root / "workspace")
            self.assertEqual(workspace.last_completed_round, 0)
            plans_root = Path(workspace.root) / "plans"
            self.assertFalse(
                plans_root.exists() and any(plans_root.iterdir())
            )
            self.assertEqual(cancelling.calls, 1)

    def test_sequential_stop_between_candidates_blocks_next_admission(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cancel = threading.Event()
            cancelling = _CancellingEvaluator(cancel)
            registry = SignalRegistry(root / "signals")
            registry.install_catalog(SEED_CATALOG)
            workspace = EvolutionWorkspace(root / "workspace")
            engine = PlanEvolutionEngine(
                archive=workspace.restore_archive(),
                meta_memory=workspace.restore_meta(),
                signal_registry=registry,
                evaluator=cancelling,
                proposer=CountingProposer(),
                critic=SimpleCritic(),
                round_reflector=SimpleRoundReflector(),
                workspace=workspace,
                seed_plans=(default_information_plan(),),
                candidates_per_round=2,
                cancel_event=cancel,
            )
            with self.assertRaises(EvaluationCancelled):
                _run(engine, root)
            self.assertEqual(workspace.last_completed_round, 0)
            self.assertEqual(cancelling.calls, 1)


class BoundedWaitTest(unittest.TestCase):
    def test_worker_wait_timeout_fails_closed_with_staged_work(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cancel = threading.Event()
            engine = _engine(
                root,
                factory=lambda: _SleepingEvaluator(0.5),
                cancel=cancel,
                parallel=1,
                wait=0.05,
            )
            with self.assertRaisesRegex(EvaluationCancelled, "bounded wait"):
                _run(engine, root)
            workspace = EvolutionWorkspace(root / "workspace")
            self.assertEqual(workspace.last_completed_round, 0)


if __name__ == "__main__":
    unittest.main()
